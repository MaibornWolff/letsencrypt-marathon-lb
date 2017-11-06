#!/bin/bash
set -e

dcos security org service-accounts keypair letsencrypt-marathon-lb-private-key.pem letsencrypt-marathon-lb-public-key.pem
dcos security org service-accounts create -p letsencrypt-marathon-lb-public-key.pem -d "letsencrypt-marathon-lb service account" letsencrypt-marathon-lb-principal
dcos security secrets create-sa-secret --strict letsencrypt-marathon-lb-private-key.pem letsencrypt-marathon-lb-principal letsencrypt-marathon-lb/marathon-secret
rm -rf *.pem
dcos security org users grant letsencrypt-marathon-lb-principal dcos:service:marathon:marathon:services:/marathon-lb full --description "Allows access for letsencrypt-marathon-lb"
dcos security org users grant letsencrypt-marathon-lb-principal dcos:service:marathon:marathon:services:/letsencrypt-marathon-lb full --description "Allows access for letsencrypt-marathon-lb"
