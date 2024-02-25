import xmltodict
import requests
from fake_useragent import UserAgent
from bs4 import BeautifulSoup
import os
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--maven-url', dest='maven_repo_url', type=str, help='Missing --maven-url')
parser.add_argument('--maven-dir', dest='offline_m2_dir', type=str, help='Missing --maven-dir')
args = parser.parse_args()

if args is None or args.maven_repo_url is None or args.offline_m2_dir is None:
    print("Missing command line arguments")
    print("Usage: python pom_parser.py --maven-url MAVEN_REPO_URL --maven-dir OFFLINE_M2_DIR")
    exit(1)

artifact_base_url = "https://mvnrepository.com/artifact"
maven_base_url = "https://repo1.maven.org/maven2"
google_maven_url = "https://maven.google.com"
google_dl_base_url = "https://dl.google.com/dl/android/maven2"
# offline_m2_dir = "C:/Users/mkhru/.m2/repository"
offline_m2_dir = args.offline_m2_dir
# maven_repo_url = "https://mvnrepository.com/artifact/com.google.dagger/dagger/2.50"
# maven_repo_url = "https://mvnrepository.com/artifact/com.google.dagger/dagger-android/2.50"
maven_repo_url = args.maven_repo_url

pom_links_processed = set()
pom_links_que = set()
download_links = set()
maven_links = set()

user_agent = UserAgent()
request_header = {
    'User-Agent': user_agent.random,
}


def get_response(url_str):
    print(f"get_response: Requesting: {url_str}")
    response = requests.get(url_str, headers=request_header)
    response_code = response.status_code
    print(f"get_response: Response code: {response_code}")
    if response_code == 200:
        return response.text
    return None


def process_artifact_url(artifact_uri):
    response = get_response(artifact_uri)
    if response is None:
        return
    soup = BeautifulSoup(response, 'html.parser')
    links = soup.find_all('a', {"class": "vbtn"})
    for link in links:
        link_str = link.get('href')
        if 'https://' in link_str:
            if google_maven_url in link_str:
                link_str = str(link_str).replace(google_maven_url, google_dl_base_url)
                if link_str.endswith(".pom"):
                    pom_links_que.add(link_str)
                download_links.add(link_str)
                print(f"process_artifact_url: {link_str}")
            elif link_str.endswith(".pom"):
                link_str = str(link_str).replace(f"/{get_base_pom_name(link_str)}", "")
                print(f"maven_url = {link_str}")
                if link_str not in maven_links:
                    process_maven_url(link_str)


def process_maven_url(maven_url):
    maven_links.add(maven_url)
    response = get_response(maven_url)
    if response is None:
        return
    soup = BeautifulSoup(response, 'html.parser')
    links = soup.select('a')
    for link in links:
        if link.get('href') is not None:
            raw_link_str = link.get('href')
            if raw_link_str in [".", "./", "..", "../"]:
                continue
            if 'https://' in raw_link_str:
                link_str = raw_link_str
            else:
                link_str = f"{maven_url}/{raw_link_str}"
            if link_str.endswith(".pom"):
                if link_str not in pom_links_processed:
                    pom_links_que.add(link_str)
                    maven_link_str = str(link_str).replace(f"/{get_base_pom_name(link_str)}", "")
                    print(f"maven_url = {maven_link_str}")
                    if maven_link_str not in maven_links:
                        process_maven_url(maven_link_str)
            download_links.add(link_str)
            # print(f"process_maven_url: {link_str}")


def dependency_to_artifact_url(dependency, base_url=""):
    artifact_uri = f"{dependency["groupId"]}/{dependency["artifactId"]}/{dependency["version"]}"
    artifact_url = f"{base_url}/{artifact_uri}"
    return artifact_url


def dependency_to_maven_url(dependency, base_url=""):
    group_id_uri = str(dependency["groupId"]).replace(".", "/")
    maven_uri = f"{group_id_uri}/{dependency["artifactId"]}/{dependency["version"]}"
    maven_url = f"{base_url}/{maven_uri}"
    return maven_url


def process_dependency(dependency, project_version):
    print(f"process_dependency: dependency = {dependency}")
    dependency_version = dependency["version"]
    if str(dependency_version) == "${project.version}":
        dependency["version"] = project_version
    group_id = dependency["groupId"]
    if "androidx" in group_id:
        artifact_url = dependency_to_artifact_url(dependency, artifact_base_url)
        process_artifact_url(artifact_url)
    else:
        maven_url = dependency_to_maven_url(dependency, maven_base_url)
        process_maven_url(maven_url)


def process_pom(pom_file):
    if pom_file in pom_links_processed:
        print(f"process_pom: Already processed: {pom_file}")
        return
    pom_links_processed.add(pom_file)
    pom_file_content = get_pom_content(pom_file)
    pom_data = xmltodict.parse(pom_file_content)
    project = pom_data["project"]
    print(f"process_pom: project = {project}")
    if project is not None:
        project_version = project["version"]
        print(f"process_pom: project_version = {project_version}")
        dependencies_key = "dependencies"
        if dependencies_key in project:
            dependencies_obj = project[dependencies_key]
            if dependencies_obj is None:
                return
            dependency = dependencies_obj["dependency"]
            if type(dependency) is list:
                for dependency_item in dependency:
                    process_dependency(dependency_item, project_version)
            else:
                process_dependency(dependency, project_version)


def get_pom_content(pom_file):
    if 'https://' in pom_file:
        file_content = get_response(pom_file)
    else:
        with open(pom_file, 'r') as fs:
            file_content = fs.read()
    return file_content


def get_base_pom_name(pom_link):
    return pom_link.split("/")[-1:][0]


def process_maven_repo_url(mvn_url):
    if not mvn_url.startswith(artifact_base_url):
        print("process_maven_repo_url: Error processing the URL")
    process_artifact_url(mvn_url)


def get_download_location(file_url):
    file_uri = ""
    if file_url.startswith(maven_base_url):
        file_uri = file_url.replace(maven_base_url, "")
    elif file_url.startswith(google_maven_url):
        file_uri = file_url.replace(google_maven_url, "")
    elif file_url.startswith(google_dl_base_url):
        file_uri = file_url.replace(google_dl_base_url, "")
    if file_uri != "":
        offline_m2_file_path = f"{offline_m2_dir}{file_uri}"
        offline_m2_dl_dir = offline_m2_file_path[:offline_m2_file_path.rfind("/")]
        # print(f"get_download_location: offline_m2_file_path = {offline_m2_file_path}")
        if not os.path.exists(offline_m2_dl_dir):
            os.makedirs(offline_m2_dl_dir)
        return offline_m2_file_path
    return None


def download_file_stream(file_url):
    offline_m2_file_path = get_download_location(file_url)

    file_header = requests.head(file_url, allow_redirects=True, headers=request_header)
    total_size = int(file_header.headers.get('content-length'))
    print(f"File size: {total_size}")
    response = requests.get(file_url, stream=True, headers=request_header)

    local_file = open(offline_m2_file_path, "wb")
    chunks = 0
    for chunk in response.iter_content(chunk_size=512):
        if chunk:
            chunks += 1
            print("#", end="")
            local_file.write(chunk)
    print()
    local_file.flush()
    print("Done")


process_maven_repo_url(maven_repo_url)
while len(pom_links_que) > 0:
    pom = pom_links_que.pop()
    print(f"Start processing: {pom}")
    process_pom(pom)

print(f"pom_links_processed = {pom_links_processed}")
print(f"pom_links_que = {pom_links_que}")
print(f"download_links = {download_links}")

if len(download_links) > 0:
    for dl_link in download_links:
        print(f"Downloading: {dl_link}")
        download_file_stream(dl_link)
else:
    print("Nothing to download")
