import os
import sys
import subprocess
import time
import json
import requests
from auth import DCOSAuth


ENV_DCOS_SERVICE_ACCOUNT_CREDENTIAL = "DCOS_SERVICE_ACCOUNT_CREDENTIAL"
ENV_MARATHON_URL = "MARATHON_URL"
DEFAULT_MARATHON_URL = "https://marathon.mesos:8443/"
ENV_MARATHON_APP_ID = "MARATHON_APP_ID"
HAPROXY_SSL_CERT = "HAPROXY_SSL_CERT"
ENV_MARATHON_LB_ID = "MARATHON_LB_ID"
ENV_LETSENCRYPT_EMAIL = "LETSENCRYPT_EMAIL"
ENV_LETSENCRYPT_URL = "LETSENCRYPT_URL"
DEFAULT_LETSENCRYPT_URL = "https://acme-staging.api.letsencrypt.org/directory"

CERTIFICATES_DIR = ".lego/certificates/"
VHOSTS_FILE = ".lego/current_vhosts"


DEFAULT_LEGO_ARGS = ["./lego",
                     "--server", os.environ.get(ENV_LETSENCRYPT_URL, DEFAULT_LETSENCRYPT_URL),
                     "--email", os.environ.get(ENV_LETSENCRYPT_EMAIL),
                     "--accept-tos",
                     "--http", ":8080",
                     "--exclude", "tls-sni-01" # To make lego use the http-01 resolver
                    ]


def get_marathon_url():
    return os.environ.get(ENV_MARATHON_URL, DEFAULT_MARATHON_URL)


def get_authorization():
    if not ENV_DCOS_SERVICE_ACCOUNT_CREDENTIAL in os.environ:
        print("No service account provided. Not using authorization")
        return None
    return DCOSAuth(os.environ.get(ENV_DCOS_SERVICE_ACCOUNT_CREDENTIAL), None)


auth = get_authorization()


def get_marathon_app(app_id):
    """Retrieve app definition for marathon-lb app"""
    response = requests.get("%(marathon_url)s/v2/apps/%(app_id)s" % dict(marathon_url=get_marathon_url(), app_id=app_id), auth=auth, verify=False)
    if not response.ok:
        raise Exception("Could not get app details from marathon")
    return response.json()


def update_marathon_app(app_id, **kwargs):
    """Post new certificate data (as environment variable) to marathon to update the marathon-lb app definition"""
    data = dict(id=app_id)
    for key, value in kwargs.items():
        data[key] = value
    headers = {'Content-Type': 'application/json'}
    response = requests.patch("%(marathon_url)s/v2/apps/%(app_id)s" % dict(marathon_url=get_marathon_url(), app_id=app_id),
                     headers=headers,
                     data=json.dumps(data),
                     auth=auth,
                     verify=False)
    if not response.ok:
        print(response)
        print(response.text)
        raise Exception("Could not update app. See response text for error message.")
    data = response.json()
    if not "deploymentId" in data:
        print(data)
        raise Exception("Could not update app. Marathon did not return deployment id.  See response data for error message.")
    deployment_id = data['deploymentId']

    # Wait for deployment to complete
    deployment_exists = True
    sum_wait_time = 0
    while deployment_exists:
        time.sleep(5)
        sum_wait_time += 5
        print("Waiting for deployment to complete")
        # Retrivee list of running deployments
        response = requests.get("%(marathon_url)s/v2/deployments" % dict(marathon_url=get_marathon_url()), auth=auth, verify=False)
        deployments = response.json()
        deployment_exists = False
        for deployment in deployments:
            # Check if our deployment is still in the list
            if deployment['id'] == deployment_id:
                deployment_exists = True
                break
        if sum_wait_time > 60*5:
            raise Exception("Failed to update app due to timeout in deployment.")


def get_vhosts():
    """Retrieve list of vhosts from own app definition"""
    data = get_marathon_app(os.environ.get(ENV_MARATHON_APP_ID))
    return data["app"]["labels"]["HAPROXY_0_VHOST"]


def combine_certs(domain_name):
    """Combine certificate and key into one file"""
    result_path = "%(path)s/%(domain_name)s.combined.pem" % dict(path=CERTIFICATES_DIR, domain_name=domain_name)
    with open(result_path, "w") as result_file:
        with open("%(path)s/%(domain_name)s.crt" % dict(path=CERTIFICATES_DIR, domain_name=domain_name)) as cert_file:
            data = cert_file.read()
            result_file.write(data)
        with open("%(path)s/%(domain_name)s.key" % dict(path=CERTIFICATES_DIR, domain_name=domain_name)) as key_file:
            data = key_file.read()
            result_file.write(data)
    return result_path


def read_vhosts_from_last_time():
    """Return list of vhosts used last time from file or empty sttring if file does not exist"""
    if os.path.exists(VHOSTS_FILE):
        with open(VHOSTS_FILE) as vhosts_file:
            return vhosts_file.read()
    else:
        return ""


def write_vhosts_to_file(vhosts):
    """Store list of vhosts in file to retrieve on next run"""
    with open(VHOSTS_FILE, "w") as vhosts_file:
        vhosts_file.write(vhosts)


def generate_letsencrypt_cert(vhosts):
    """Use lego to validate domains and retrieve letsencrypt certificates"""
    vhosts_changed = vhosts != read_vhosts_from_last_time()
    first_vhost = vhosts.split(",")[0]
    args = list()
    for vhost in vhosts.split(","):
        args.append("--domains")
        args.append(vhost)
    # Check if certificate already exists
    if not vhosts_changed and os.path.exists("%(path)s/%(domain_name)s.crt" % dict(path=CERTIFICATES_DIR, domain_name=first_vhost)):
        print("Renewing certificates")
        args.append("renew")
        args.append("--days")
        args.append("80")
    else:
        print("Requesting new certificates")
        args.append("run")
    # Start lego
    result = subprocess.run(DEFAULT_LEGO_ARGS + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        print(result)
        raise Exception("Obtaining certificates failed. Check lego output for error messages.")
    write_vhosts_to_file(vhosts)
    return first_vhost


def upload_cert_to_marathon_lb(cert_filename):
    """Update the marathon-lb app definition and set the the generated certificate as environment variable HAPROXY_SSL_CERT"""
    with open(cert_filename) as cert_file:
        cert_data = cert_file.read()
    # Retrieve current app definition of marathon-lb
    marathon_lb_id = os.environ.get(ENV_MARATHON_LB_ID)
    app_data = get_marathon_app(marathon_lb_id)
    env = app_data["app"]["env"]
    # Compare old and new certs
    if env.get(HAPROXY_SSL_CERT, "") != cert_data:
        print("Certificate changed. Updating certificate")
        env[HAPROXY_SSL_CERT] = cert_data
        # Provide env and secrets otherwise marathon will complain about a missing secret
        update_marathon_app(marathon_lb_id, env=env, secrets=app_data["app"].get("secrets", {}))
    else:
        print("Certificate not changed. Not doing anything")


def run_client():
    """Generate certificates if necessary and update marathon-lb"""
    vhosts = get_vhosts()
    print("Requesting certificates for " + vhosts)
    sys.stdout.flush()
    domain_name = generate_letsencrypt_cert(vhosts)
    sys.stdout.flush()
    cert_file = combine_certs(domain_name)
    print("Uploading certificates")
    sys.stdout.flush()
    upload_cert_to_marathon_lb(cert_file)
    sys.stdout.flush()


def run_client_with_backoff():
    """Calls run_client but catches exceptions and tries again for up to one hour.
        Use this variant if you don't want this app to fail (and redeploy) because of intermittent errors.
    """
    backoff_seconds = 30
    sum_wait_time = 0
    while True:
        try:
            run_client()
            return
        except Exception as ex:
            print(ex)
            if sum_wait_time >= 60*60:
                # Reraise exception after 1 hour backoff, will lead to task failure in marathon
                raise ex
            sum_wait_time += backoff_seconds
            time.sleep(backoff_seconds)
            backoff_seconds *= 2


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "service":
        while True:
            run_client()
            time.sleep(24*60*60) # Sleep for 24 hours
    elif len(sys.argv) > 1 and sys.argv[1] == "service_with_backoff":
        while True:
            run_client_with_backoff()
            time.sleep(24*60*60) # Sleep for 24 hours
    else:
        run_client()
