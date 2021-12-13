# END OF LIFE
This project is not being maintained anymore.

This application allows you to generate and renew Let's Encrypt certificates for Marathon-lb automatically. It must be run as a Marathon app. The application generates or renews the certificates upon startup and checks every 24h if certificates need to be renewed. If you need certificates for new / additional domains, you have to change the configuration and restart the application.

The application is inspired heavily by the work done by Brenden Matthews (https://github.com/mesosphere/letsencrypt-dcos). In contrary to Brenden's tool, this application also supports DC/OS strict security mode. We decided to do a complete reimplementation because the rewrite was simpler than extending the existing solution. Code in auth.py is taken from https://github.com/mesosphere/marathon-lb/blob/master/common.py



## Getting started
* Prepare service account in you DC/OS cluster (only needed for clusters with strict security mode, optional for clusters in permissive security mode)
  * Create service account with necessary permissions for marathon api access
  * Create secret with private key of service account
  * You can use the script create_serviceaccount.sh (included in this git repo) to create both using the dcos-cli
* Deploy as marathon app (using the definition file letsencrypt-marathon-lb.json)
  * Change environment variables in marathon definition of this application
    * LETSENCRYPT_EMAIL: Set to your own email address (will receive expiration notifications by Let's Encrypt)
    * LETSENCRYPT_URL: Set to production url (https://acme-v02.api.letsencrypt.org/directory) only after you have confirmed it works!
    * For http verification set the following:
      * HAPROXY_0_VHOST: A comma-separated list of domains you want to include in your certificate (all of them must be reachable via marathon-lb or validation will fail, wildcards are not supported with http verification method)
      * LETSENCRYPT_VERIFICATION_METHOD to `http`
    * For dns verification set the following:
      * LETSENCRYPT_VERIFICATION_METHOD to `dns`
      * DOMAINS: A comma-separated list of domains you want to include in your certificate, can include wildcard domains
      * DNSPROVIDER: Set to your dns provider (see https://github.com/xenolf/lego/tree/master/providers/dns for a list of possible options), defaults to route53
      * Provider-specific options (for route53: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, AWS_HOSTED_ZONE_ID)
  * Set name for external persistent volume or change volume definition to a local persistent volume
  * You can use the provided docker image (maibornwolff/letsencrypt-marathon-lb) or build it yourself
  * Deploy the application using the DC/OS Admin UI or the dcos cli

Example marathon definitions are provided as `letsencrypt-marathon-lb-http.json` and `letsencrypt-marathon-lb-dns.json`.

```bash
edit letsencrypt-marathon-lb-http.json # change variables as needed
./create_serviceaccount.sh
dcos marathon app add letsencrypt-marathon-lb-http.json
```


## How does it work
* The script will get the domains from its own HAPROXY_0_VHOST label or the DOMAINS environment variable depending on verification mode and instruct lego to request a certificate for them.
* If verification method is http: Due to the HAPROXY_0_VHOST and HAPROXY_0_PATH labels marathon-lb will proxy all requests to the letsencrypt verification paths for these domains to the script where lego will receive them and do a webroot-based verification.
* If verification method is dns: Using the provided credentials for your dns provider lego will perform dns verification and add the required dns records to your zone.
* The script then uses the marathon api to update the HAPROXY_SSL_CERT variable of the marathon-lb app which will then (after a restart of the app) use the provided certificate for HTTPS connections.


## Features
* Entire workflow done in python
* Uses DC/OS service accounts and access tokens (needed when DC/OS cluster is configured with strict security mode)
* [Lego](https://github.com/xenolf/lego) instead of certbot
* Supports dns verification method and wildcard domains


## Limitations
* You may only have up to 100 domains per certificate (Let's Encrypt limitation).
* You can only generate 20 certificates per week (Let's Encrypt limitation).
* Currently, when the certificate is updated, it requires a full redeploy of Marathon-lb (which is done automatically by this application). This means there may be a few seconds of downtime as the deployment occurs. This can be mitigated by placing another LB (such as an ELB or F5) in front of Marathon-lb.


## Future Features
* Provide certificate to Marathon-lb via DC/OS secret
* DC/OS ca-certificate verification on marathon api calls
