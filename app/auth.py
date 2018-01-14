#!/usr/bin/env python3

import json
import os
import sys
import time
import jwt
import requests
from requests.auth import AuthBase


class DCOSAuth(AuthBase):
    def __init__(self, credentials, ca_cert):
        # Read credential data from environment secret
        creds = cleanup_json(json.loads(credentials))
        self.uid = creds['uid']
        self.private_key = creds['private_key']
        self.login_endpoint = creds['login_endpoint']
        # Initialize state
        self.verify = False
        self.auth_header = None
        self.expiry = 0
        if ca_cert:
            self.verify = ca_cert

    def __call__(self, auth_request):
        self.refresh_auth_header()
        auth_request.headers['Authorization'] = self.auth_header
        return auth_request

    def refresh_auth_header(self):
        now = int(time.time())
        # Renew token if no token available or expiry time reached
        if not self.auth_header or now >= self.expiry - 10:
            self.expiry = now + 3600 # Assume token expires after one hour
            payload = {
                'uid': self.uid,
                # This is the expiry of the auth request params
                'exp': now + 60,
            }
            token = jwt.encode(payload, self.private_key, 'RS256')

            data = {
                'uid': self.uid,
                'token': token.decode('ascii'),
                # This is the expiry for the token itself
                'exp': self.expiry,
            }
            r = requests.post(self.login_endpoint,
                              json=data,
                              timeout=(3.05, 46),
                              verify=self.verify)
            r.raise_for_status()

            self.auth_header = 'token=' + r.cookies['dcos-acs-auth-cookie']


def cleanup_json(data):
    if isinstance(data, dict):
        return {k: cleanup_json(v) for k, v in data.items() if v is not None}
    if isinstance(data, list):
        return [cleanup_json(e) for e in data]
    return data
