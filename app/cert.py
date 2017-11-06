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
    response = requests.get("%(marathon_url)s/v2/apps/%(app_id)s" % dict(marathon_url=get_marathon_url(), app_id=app_id), auth=auth, verify=False)
    if not response.ok:
        raise Exception("Could not get app details from marathon")
    return response.json()

def update_marathon_app(app_id, **kwargs):
    data = dict(id=app_id)
    for key, value in kwargs.items():
        data[key] = value
    headers = {'Content-Type': 'application/json'}
    r = requests.patch("%(marathon_url)s/v2/apps/%(app_id)s" % dict(marathon_url=get_marathon_url(), app_id=app_id),
                     headers=headers,
                     data=json.dumps(data),
                     auth=auth,
                     verify=False)
    data = r.json()
    if not "deploymentId" in data:
        print(data)
        raise Exception("Could not update app.")
    deployment_id = data['deploymentId']

    # Wait for deployment to complete
    deployment_exists = True
    while deployment_exists:
        time.sleep(5)
        print("Waiting for deployment to complete")
        r = requests.get("%(marathon_url)s/v2/deployments" % dict(marathon_url=get_marathon_url()), auth=auth, verify=False)
        deployments = r.json()
        deployment_exists = False
        for deployment in deployments:
            if deployment['id'] == deployment_id:
                deployment_exists = True
                break

def get_vhosts():
    data = get_marathon_app(os.environ.get(ENV_MARATHON_APP_ID))
    return data["app"]["labels"]["HAPROXY_0_VHOST"]

def combine_certs(domain_name):
    result_path = "%(path)s/%(domain_name)s.combined.pem" % dict(path=CERTIFICATES_DIR, domain_name=domain_name)
    with open(result_path, "w") as result_file:
        with open("%(path)s/%(domain_name)s.crt" % dict(path=CERTIFICATES_DIR, domain_name=domain_name)) as f:
            data = f.read()
            result_file.write(data)
        with open("%(path)s/%(domain_name)s.key" % dict(path=CERTIFICATES_DIR, domain_name=domain_name)) as f:
            data = f.read()
            result_file.write(data)
    return result_path

def read_vhosts_from_last_time():
    if os.path.exists(VHOSTS_FILE):
        with open(VHOSTS_FILE) as f:
            return f.read()
    else:
        return ""

def write_vhosts_to_file(vhosts):
    with open(VHOSTS_FILE, "w") as f:
        f.write(vhosts)

def generate_letsencrypt_cert(vhosts):
    vhosts_changed = vhosts != read_vhosts_from_last_time()
    first_vhost = vhosts.split(",")[0]
    args = list()
    for vhost in vhosts.split(","):
        args.append("--domains")
        args.append(vhost)
    if not vhosts_changed and os.path.exists("%(path)s/%(domain_name)s.crt" % dict(path=CERTIFICATES_DIR, domain_name=first_vhost)):
        print("Renewing certificates")
        args.append("renew")
        args.append("--days")
        args.append("80")
    else:
        print("Requesting new certificates")
        args.append("run")
    result = subprocess.run(DEFAULT_LEGO_ARGS + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        print(result)
        raise Exception("Obtaining certificates failed")
    write_vhosts_to_file(vhosts)
    return first_vhost

def upload_cert_to_marathon_lb(cert_filename):
    with open(cert_filename) as cert_file:
        cert_data = cert_file.read()
    marathon_lb_id = os.environ.get(ENV_MARATHON_LB_ID)
    app_data = get_marathon_app(marathon_lb_id)
    env = app_data["app"]["env"]
    if env.get(HAPROXY_SSL_CERT, "") != cert_data:
        print("Certificate changed. Updating certificate")
        env[HAPROXY_SSL_CERT] = cert_data
        # Provide env and secrets otherwise marathon will complain about a missing secret
        update_marathon_app(marathon_lb_id, env=env, secrets=app_data["app"].get("secrets", {}))
    else:
        print("Certificate not changed. Not doing anything")

def run_client():
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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "service":
        while True:
            run_client()
            time.sleep(24*60*60)
    else:
        run_client()
