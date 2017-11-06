This application allows you to generate and renew Let's Encrypt certificates for Marathon-lb automatically. It must be run as a Marathon app. The application generates or renews the certificates upon startup and checks every 24h if certificates need to be renewed. If you need certificates for new / additional domains, you have to change the configuration and restart the application.

The application is inspired heavily by the work done by Brenden Matthews (https://github.com/mesosphere/letsencrypt-dcos). In contrary to Brenden's tool, this application also supports DC/OS strict security mode. We decided to do a complete reimplementation because the rewrite was simpler than extending the existing solution. Code in auth.py is taken from https://github.com/mesosphere/marathon-lb/blob/master/common.py


## Getting started
* Prepare service account in you DC/OS cluster
  * Create service account with necessary permissions for marathon api access
  * Create secret with private key of service account
  * You can use the script create_serviceaccount.sh (included in this git repo) to create both using the dcos-cli
* Deploy as marathon app (using the definition file letsencrypt-marathon-lb.json)
  * Change environment variables in marathon definition of this application
    * LETSENCRYPT_EMAIL
    * LETSENCRYPT_URL: Set to production url (https://acme-v01.api.letsencrypt.org/directory) only after you have confirmed it works!
    * HAPROXY_0_VHOST: A comma-separated list of domains you want to include in your certificate (all of them must be reachable via marathon-lb or validation will fail)
  * Set name for external persistent volume or change volume definition to a local persistent volume
  * You can use the provided docker image (maibornwolff/letsencrypt-marathon-lb) or build it yourself
  * Deploy the application using the DC/OS Admin GUI or the dcos cli (dcos marathon app add letsencrypt-marathon-lb.json)


## How does it work
* The script will get the domains from its own HAPROXY_0_VHOST label and instruct lego to request a certificate for them.
* Due to the HAPROXY_0_VHOST and HAPROXY_0_PATH labels marathon-lb will proxy all requests to the letsencrypt verification paths for these domains to the script where lego will receive them and do a webroot-based verification.
* The script then uses the marathon api to update the HAPROXY_SSL_CERT variable of the marathon-lb app which will then (after a restart of the app) use the provided certificate for HTTPS connections.


## Features
* Entire workflow done in python
* Uses DC/OS service accounts and access tokens (needed when DC/OS cluster is configured with strict security mode)
* [Lego](https://github.com/xenolf/lego) instead of certbot


## Limitations
* You may only have up to 100 domains per certificate (Let's Encrypt limitation).
* You can only generate 20 certificates per week (Let's Encrypt limitation).
* Currently, when the certificate is updated, it requires a full redeploy of Marathon-lb (which is done automatically by this application). This means there may be a few seconds of downtime as the deployment occurs. This can be mitigated by placing another LB (such as an ELB or F5) in front of Marathon-lb.


## Future Features
* Support for wildcard certificates as soon as letsencrypt issues them (January 2018)
* Provide certificate to Marathon-lb via DC/OS secret
* DC/OS ca-certificate verification on marathon api calls
