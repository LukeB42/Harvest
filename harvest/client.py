import requests
import pprint
import json
import cmd
import os

os.environ['no_proxy'] = '127.0.0.1,localhost'
requests.packages.urllib3.disable_warnings()

class Client(object):
    def __init__(self, key, base_url, verify=True, timeout=2.500):
        self.key = key
        self.base = base_url
        pp = pprint.PrettyPrinter(indent=4)
        self.p = pp.pprint
        self.verify_https = verify
        self.timeout = timeout

        # Defining a username manually on your client objects will
        # permit you to use the .can() shortcut for determining
        # the username's access rights.
        self.username = None

        if not self.base.endswith('/'):
            self.base += '/'

    def _send_request(self, url, type='GET', body={}, headers={}):
        headers['Authorization'] = "Basic %s" % self.key
        url = self.base + url
        resp = None
        if type == 'GET':
            resp = requests.get(url, verify=self.verify_https,
                headers=headers, timeout=self.timeout)
        elif type == 'DELETE':
            resp = requests.delete(url, verify=self.verify_https,
                data=body, headers=headers, timeout=self.timeout)
        elif type == 'PUT':
            resp = requests.put(url, verify=self.verify_https,
                data=body, headers=headers, timeout=self.timeout)
        elif type == 'POST':
            resp = requests.post(url, verify=self.verify_https,
                data=body, headers=headers, timeout=self.timeout)
        try:
            return resp.json(), resp.status_code
        except:
            return {}, resp.status_code

    def get(self, url, body={}, headers={}):
        return self._send_request(url, body=body, headers=headers)

    def put(self, url, body={}, headers={}):
        return self._send_request(url, type='PUT', body=body, headers=headers)

    def post(self, url, body={}, headers={}):
        return self._send_request(url, type='POST', body=body, headers=headers)

    def delete(self, url, body={}, headers={}):
        return self._send_request(url, type='DELETE', body=body, headers=headers)

    def pp(self, url, type='GET', body={}, headers={}):
        self.p(self._send_request(url, type, body, headers))

    def keys(self, type='GET', body={}, headers={}):
        return self._send_request("keys", type, body, headers)

    def __repr__(self):
        return "<API Client for %s>" % self.base
