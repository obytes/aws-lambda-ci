"""
__author__     = "Hamza Adami"
__maintainer__ = "Hamza Adami"
__email__      = "me@adamihamza.com"
"""
import hashlib
import os
import filecmp
import subprocess
import argparse
import uuid
from base64 import b64encode
from functools import wraps
from tempfile import mkdtemp
from shutil import make_archive, move, copy2
import time
import boto3
import botocore

# Arguments
# ---------
parser = argparse.ArgumentParser(description='AWS Lambda CI Pipeline.')

parser.add_argument('--app-s3-bucket', dest='app_s3_bucket', required=True,
                    help="The s3 bucket name that will hold the the application code and dependencies")

parser.add_argument('--function-name', dest='function_name', required=True, help="AWS lambda function name")
parser.add_argument('--function-runtime', dest='function_runtime', required=False, default="python3.9",
                    help="AWS lambda function runtime (eg: python3.9)")
parser.add_argument('--function-alias-name', dest='function_alias_name', required=False, default="latest",
                    help="AWS Lambda alias name (eg: latest)")
parser.add_argument('--function-layer-name', dest='function_layer_name', required=False,
                    help="AWS Lambda layer name (eg: demo-lambda-dependencies)")

parser.add_argument('--app-src-path', dest='app_src_path', required=False, default=".",
                    help="Lambda function sources directory that will be archived (eg: demo-lambda/src)")
parser.add_argument('--app-packages-descriptor-path', dest='app_packages_descriptor_path', required=False,
                    default="requirements.txt",
                    help="Packages descriptor path (eg: demo-lambda/requirements.txt)")

parser.add_argument('--source-version', dest='source_version', required=False, default=uuid.uuid4().hex.upper(),
                    help="The unique revision id (eg: github commit sha, or SemVer tag)")
parser.add_argument('--aws-profile-name', dest='aws_profile_name', required=False,
                    help="AWS profile name (if not provided, will use default aws env variables)")
parser.add_argument('--watch-log-stream', dest='watch_log_stream', required=False, default=False, action='store_true',
                    help="AWS profile name (if not provided, will use default aws env variables)")

args = parser.parse_args()

# Validation
# ----------
if args.aws_profile_name:
    boto3.setup_default_session(profile_name=args.aws_profile_name)

if not args.function_layer_name:
    args.function_layer_name = f"{args.function_name}-deps"

function_runtime = args.function_runtime
if function_runtime.startswith("python"):
    LANGUAGE = "python"
elif function_runtime.startswith("nodejs"):
    LANGUAGE = "nodejs"
else:
    raise Exception("Unsupported lambda runtime, only python and nodejs are supported for now!")


# Clients
# -------
def retry_decorator(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        max_retries = 10
        for t in range(max_retries):
            try:
                return f(*args, **kwargs)
            except lam.exceptions.ResourceConflictException:
                print("⌛\tLambda update is still in progress, retry in 3 seconds!")
                time.sleep(3)
                continue
        else:
            raise Exception("Max retries exceeded when trying to update lambda!")

    return wrapper


s3 = boto3.resource("s3")
lam = boto3.client("lambda")
setattr(lam, 'update_function_code', retry_decorator(lam.update_function_code))
setattr(lam, 'publish_version', retry_decorator(lam.publish_version))

# Utils
# -----
DESCRIPTORS = {
    "python": "requirements.txt",
    "nodejs": "package.json"
}

# Function
FUNCTION_NAME = args.function_name
FUNCTION_RUNTIME = args.function_runtime
FUNCTION_ALIAS_NAME = args.function_alias_name
FUNCTION_LAYER_NAME = args.function_layer_name
FUNCTION_LATEST_CONFIG = lam.get_function(FunctionName=FUNCTION_NAME, Qualifier=FUNCTION_ALIAS_NAME)["Configuration"]
FUNCTION_REGION = FUNCTION_LATEST_CONFIG["FunctionArn"].split(":")[3]
FUNCTION_LATEST_VERSION = FUNCTION_LATEST_CONFIG["Version"]
FUNCTION_LATEST_CODE_SHA = FUNCTION_LATEST_CONFIG["CodeSha256"]
FUNCTION_CURRENT_GIT_VERSION = FUNCTION_LATEST_CONFIG["Description"] if FUNCTION_LATEST_CONFIG else "Virgin"
FUNCTION_LATEST_LAYER_CONFIG = lam.list_layer_versions(LayerName=FUNCTION_LAYER_NAME, MaxItems=1)["LayerVersions"]
FUNCTION_LATEST_LAYER_VERSION = FUNCTION_LATEST_LAYER_CONFIG[0]["Version"] if FUNCTION_LATEST_LAYER_CONFIG else 0
FUNCTION_LAYER_CURRENT_GIT_VERSION = FUNCTION_LATEST_LAYER_CONFIG[0][
    "Description"] if FUNCTION_LATEST_LAYER_CONFIG else "Virgin"

# Bucket
APP_BUCKET = args.app_s3_bucket
APP_S3_KEY_PREFIX = f"lambda-ci/{FUNCTION_NAME}"

# Paths
os.makedirs("/tmp/lambda-ci/", exist_ok=True)
WORKING_DIR = mkdtemp(prefix="/tmp/lambda-ci/")
PACKAGES_DESCRIPTOR_S3_KEY = f"{APP_S3_KEY_PREFIX}/latest/{DESCRIPTORS[LANGUAGE]}"
CURRENT_PACKAGES_DESCRIPTOR_PATH = args.app_packages_descriptor_path
PREVIOUS_PACKAGES_DESCRIPTOR_PATH = f"{WORKING_DIR}/prev-{DESCRIPTORS[LANGUAGE]}"
APP_SRC_PATH = args.app_src_path

# Lambda Version
SOURCE_VERSION = args.source_version
VERSION_S3_KEY = f"{APP_S3_KEY_PREFIX}/{SOURCE_VERSION}"
APP_VERSION_S3_KEY = f"{VERSION_S3_KEY}/app.zip"
DEP_VERSION_S3_KEY = f"{VERSION_S3_KEY}/deps.zip"
APP_LATEST_S3_KEY = f"{APP_S3_KEY_PREFIX}/latest/app.zip"
DEP_LATEST_S3_KEY = f"{APP_S3_KEY_PREFIX}/latest/deps.zip"
APP_CURRENT_S3_KEY = f"{APP_S3_KEY_PREFIX}/{FUNCTION_CURRENT_GIT_VERSION}/app.zip"
DEP_CURRENT_S3_KEY = f"{APP_S3_KEY_PREFIX}/{FUNCTION_LAYER_CURRENT_GIT_VERSION}/deps.zip"

# Internals
APP_ZIP_FILENAME = f"{WORKING_DIR}/app"
DEP_ZIP_FILENAME = f"{WORKING_DIR}/deps"

COL_BLU = "\033[94m"
COL_GRN = "\033[92m"
COL_YEL = "\033[93m"
COL_MAG = "\033[95m"
COL_CYN = "\033[96m"
COL_WHT = "\033[97m"
COL_END = "\033[0m"


#####################################################
# CI/CD PIPELINE: BUILD -> PUSH -> DEPLOY -> PUBLISH
#####################################################

def build():
    """
    Prepare dependencies and application distributions
    :return: True if dependencies changed
    """
    deps_changed = True

    # CHECK IF FIRST BUILD OR DEPENDENCIES HAVE BEEN CHANGED
    found_cache = get_cached_package_descriptor()
    if found_cache:
        deps_changed = application_dependencies_changed()

    if deps_changed:
        # FETCH/PACKAGE DEPENDENCIES
        fetch_dependencies()
        package_dependencies_dist()

    # FETCH/PACKAGE APP
    package_app_dist()
    code_changed = application_code_changed()

    return deps_changed, code_changed


def push(deps_changed, code_changed):
    """
    Push new dependencies distribution and application distribution to S3
    :param deps_changed: if True push dependencies distribution
    :param code_changed: if True push code distribution
    """
    if deps_changed:
        push_dependencies()
    if code_changed:
        push_application()


def deploy(deps_changed, code_changed):
    """
    Deploy new dependencies to a new layer version and update lambda code
    :param deps_changed: if True deploy dependencies distribution
    :param code_changed: if True deploy code distribution
    """
    layer_version = None
    if deps_changed:
        # DEPLOY NEW DEPENDENCIES
        print(f"🏗️\t{COL_MAG}Deploying{COL_END} dependencies...")
        resp = lam.publish_layer_version(
            LayerName=FUNCTION_LAYER_NAME,
            Description=SOURCE_VERSION,
            Content={
                'S3Bucket': APP_BUCKET,
                'S3Key': DEP_VERSION_S3_KEY,
            },
            CompatibleRuntimes=[FUNCTION_RUNTIME],
        )
        layer_version = resp["Version"]
        layer_version_arn = resp["LayerVersionArn"]
        lam.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Layers=[
                layer_version_arn,
            ],
        )
        print("✅\tDependencies deployed!")

        print(f"🧷\t{COL_CYN}Caching{COL_END} package descriptor...")
        s3.meta.client.upload_file(CURRENT_PACKAGES_DESCRIPTOR_PATH, APP_BUCKET, PACKAGES_DESCRIPTOR_S3_KEY)
        print("✅\tPackage descriptor cached!")

    if code_changed:
        # DEPLOY NEW APPLICATION
        print(f"🏗️\t{COL_MAG}Deploying{COL_END} application...")
        lam.update_function_code(
            FunctionName=FUNCTION_NAME,
            S3Bucket=APP_BUCKET,
            S3Key=APP_VERSION_S3_KEY,
        )
        print("✅\tApplication deployed!")
    return layer_version


def publish():
    """
    Publish new lambda version and shift traffic to it
    """
    # Publish
    print(f"🚢\t{COL_GRN}Publishing{COL_END} application...")
    lambda_published_version = lam.publish_version(
        FunctionName=FUNCTION_NAME,
        Description=SOURCE_VERSION,
    )["Version"]
    print("✅\tApplication published!")
    # Shift
    print(f"📌\t{COL_GRN}Shifting{COL_END} traffic to new published version...")
    lam.update_alias(
        FunctionName=FUNCTION_NAME,
        Name=FUNCTION_ALIAS_NAME,
        FunctionVersion=lambda_published_version,
        Description=SOURCE_VERSION,
    )
    print("🎉\tHallelujah! application deployed and published successfully.")
    return lambda_published_version


########
# UTILS
########

# Check
# -----
def key_exist(key):
    try:
        s3.Object(APP_BUCKET, key).load()
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            return False
        else:
            raise
    return True


def get_cached_package_descriptor():
    print(f"👀\t{COL_WHT}Checking{COL_END} if package descriptor cache exist on S3...")
    if key_exist(PACKAGES_DESCRIPTOR_S3_KEY):
        print("✅\tRemote packages descriptor found!")
        s3.Bucket(APP_BUCKET).download_file(PACKAGES_DESCRIPTOR_S3_KEY, PREVIOUS_PACKAGES_DESCRIPTOR_PATH)
        return PREVIOUS_PACKAGES_DESCRIPTOR_PATH
    else:
        print("❌\tRemote packages descriptor not found, no cache - dependencies will be updated")
        return None


def application_dependencies_changed():
    print(f"📐️\t{COL_CYN}Comparing{COL_END} cached packages descriptor with new packages descriptor...")
    not_changed = filecmp.cmp(PREVIOUS_PACKAGES_DESCRIPTOR_PATH, CURRENT_PACKAGES_DESCRIPTOR_PATH)
    if not_changed:
        print("✅\tDependencies didn't change, skipping dependencies update!")
        return False
    else:
        print("❌\tDependencies changed, dependencies will be updated!")
        return True


def application_code_changed():
    print(f"📐️\t{COL_CYN}Comparing{COL_END} latest code sha with local code sha...")
    with open(f"{APP_ZIP_FILENAME}.zip", 'rb') as f:
        local_code = f.read()
        m = hashlib.sha256()
        m.update(local_code)
        s3_digest = m.digest()
        local_code_sha = b64encode(s3_digest).decode("utf-8")
        if local_code_sha == FUNCTION_LATEST_CODE_SHA:
            print("✅\tCode hash didn't change, skipping code update!")
            return False
        else:
            print("❌\tCode hash changed, code will be updated!")
            return True


# Install
# -------
def fetch_dependencies():
    print(f"🧲\t{COL_YEL}Fetching{COL_END} dependencies...")
    descriptor = copy2(CURRENT_PACKAGES_DESCRIPTOR_PATH, f"{WORKING_DIR}/current-{DESCRIPTORS[LANGUAGE]}")
    descriptor = os.path.basename(descriptor)
    if LANGUAGE == "python":
        pip(descriptor)
    elif LANGUAGE == "nodejs":
        npm()
        move(f"{WORKING_DIR}/node_modules", f"{WORKING_DIR}/nodejs/node_modules")
    print("✅\tDependencies installed!")


def pip(descriptor):
    install_cmd = f"pip3 install -r {descriptor} -t python/lib/{FUNCTION_RUNTIME}/site-packages"
    docker_run(install_cmd)


def npm():
    install_cmd = f"npm install"
    docker_run(install_cmd)


def docker_run(install_cmd):
    docker_cmd = (
        "docker", "run", f'-v "{WORKING_DIR}":/var/task',
        f"--rm lambci/lambda:build-{FUNCTION_RUNTIME}",
        f'/bin/sh -c "{install_cmd}"'
    )
    try:
        with open(f"/tmp/{SOURCE_VERSION}-deps.log", 'w') as output:
            subprocess.check_call(
                " ".join(docker_cmd),
                shell=True,
                stdout=output,
                stderr=subprocess.STDOUT
            )
    except subprocess.CalledProcessError:
        print(open(f"/tmp/{SOURCE_VERSION}-deps.log", 'r').read())
        exit(1)


# Package
# -------
def package_dependencies_dist():
    print(f"📦\t{COL_YEL}Packaging{COL_END} dependencies...")
    make_archive(DEP_ZIP_FILENAME, "zip", WORKING_DIR, LANGUAGE)
    print("✅\tDependencies distribution ready!")


def package_app_dist():
    print(f"📦\t{COL_YEL}Packaging{COL_END} app...")
    make_archive(APP_ZIP_FILENAME, "zip", APP_SRC_PATH)
    print("✅\tApp distribution ready!")


# Push
# ----
def push_dependencies():
    print(f"🚀\t{COL_BLU}Pushing{COL_END} dependencies distribution to S3...")
    s3.meta.client.upload_file(f"{DEP_ZIP_FILENAME}.zip", APP_BUCKET, DEP_LATEST_S3_KEY)
    s3.meta.client.upload_file(f"{DEP_ZIP_FILENAME}.zip", APP_BUCKET, DEP_VERSION_S3_KEY)
    print("✅\tDependencies distribution pushed!")


def push_application():
    print(f"🚀\t{COL_BLU}Pushing{COL_END} application distribution to S3...")
    s3.meta.client.upload_file(f"{APP_ZIP_FILENAME}.zip", APP_BUCKET, APP_LATEST_S3_KEY)
    s3.meta.client.upload_file(f"{APP_ZIP_FILENAME}.zip", APP_BUCKET, APP_VERSION_S3_KEY)
    print("✅\tApplication distribution pushed!")


def summary(lambda_version, layer_version,
            code_changed=False, deps_changed=False):
    lam_url = f"https://console.aws.amazon.com/lambda/home?region={FUNCTION_REGION}#"
    artifacts_location = f"https://s3.console.aws.amazon.com/s3/buckets/{args.app_s3_bucket}?prefix="
    link = f"\u001b]8;;%s\u001b\\See on aws console\u001b]8;;\u001b\\"

    function_version_url = link % f"{lam_url}/functions/{FUNCTION_NAME}/versions/{lambda_version}?tab=code"
    function_layer_url = link % f"{lam_url}/layers/{FUNCTION_LAYER_NAME}/versions/{layer_version}"

    version = f"{COL_WHT}Version={COL_END}"
    state = f"{COL_WHT}State={COL_END}"
    intact = f"{COL_BLU}INTACT{COL_END}"
    changed = f"{COL_GRN}CHANGED{COL_END}"
    published = f"{COL_GRN}PUBLISHED{COL_END}"
    lambda_state = published if code_changed or deps_changed else intact
    layer_state = published if deps_changed else intact
    code_state = changed if code_changed else intact
    deps_state = changed if deps_changed else intact

    if deps_changed:
        current_deps_s3_key = f"{DEP_VERSION_S3_KEY}"
        current_deps_version = SOURCE_VERSION
    else:
        current_deps_s3_key = f"{DEP_CURRENT_S3_KEY}"
        current_deps_version = FUNCTION_LAYER_CURRENT_GIT_VERSION
    if code_changed:
        current_code_s3_key = f"{APP_VERSION_S3_KEY}"
        current_code_version = SOURCE_VERSION
    else:
        current_code_s3_key = f"{APP_CURRENT_S3_KEY}"
        current_code_version = FUNCTION_CURRENT_GIT_VERSION
    code_s3_url = link % f"{artifacts_location}{current_code_s3_key.replace('/', '%2F')}"
    deps_s3_url = link % f"{artifacts_location}{current_deps_s3_key.replace('/', '%2F')}"

    print("\nCurrently published:")
    print("====================")
    print(
        f"{COL_YEL}Lambda:{COL_END} {function_version_url} [{state}{lambda_state}, {version}{COL_MAG}{lambda_version}{COL_END}]")
    print(
        f"{COL_YEL}Layer:{COL_END}  {function_layer_url} [{state}{layer_state}, {version}{COL_MAG}{layer_version}{COL_END}]")
    print("\nArtifacts:")
    print("===========")
    print(
        f"{COL_YEL}Source code:{COL_END}  {code_s3_url} [{state}{code_state}, {version}{COL_MAG}{current_code_version}{COL_END}]")
    print(
        f"{COL_YEL}Dependencies:{COL_END} {deps_s3_url} [{state}{deps_state}, {version}{COL_MAG}{current_deps_version}{COL_END}]")

    if args.watch_log_stream:
        print("\nWatching lambda cloudwatch log stream...")
        try:
            try:
                with open(f"/tmp/{SOURCE_VERSION}-awslogs.log", 'w') as output:
                    subprocess.call(["awslogs", "get", f"/aws/lambda/{FUNCTION_NAME}",
                                     f"\\d{{4}}\\/\\d{{2}}\\/\\d{{2}}\\/\\[{lambda_version}\\].*",
                                     "--watch", "--profile", F"{args.aws_profile_name}", ],
                                    stderr=output)
            except subprocess.CalledProcessError:
                pass
        except KeyboardInterrupt:
            print("End stream!")


def ci():
    logo = f"""{COL_YEL}
                __    ___    __  _______  ____  ___       __________
               / /   /   |  /  |/  / __ )/ __ \/   |     / ____/  _/
              / /   / /| | / /|_/ / __  / / / / /| |    / /    / /  
             / /___/ ___ |/ /  / / /_/ / /_/ / ___ |   / /____/ /   
            /_____/_/  |_/_/  /_/_____/_____/_/  |_|   \____/___/
    {COL_END}
    """
    print(logo)
    print(f"📁\tWorking directory: {COL_MAG}{WORKING_DIR}{COL_END}")
    print(f"📁\tLast version: {COL_YEL}{FUNCTION_CURRENT_GIT_VERSION}{COL_END}")
    print(f"📁\tNext version: {COL_GRN}{SOURCE_VERSION}{COL_END}")
    deps_changed, code_changed = build()
    if not deps_changed and not code_changed:
        print("🎉\tCode and dependencies not changed, nothing to be done!")
        summary(FUNCTION_LATEST_VERSION, FUNCTION_LATEST_LAYER_VERSION, )
    else:
        push(deps_changed, code_changed)
        layer_published_version = deploy(deps_changed, code_changed)
        lambda_published_version = publish()
        summary(
            lambda_published_version, layer_published_version or FUNCTION_LATEST_LAYER_VERSION,
            code_changed=code_changed, deps_changed=deps_changed,
        )


# EntryPoint
if __name__ == "__main__":
    ci()
