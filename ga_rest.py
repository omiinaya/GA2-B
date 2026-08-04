"""Module ga_rest — extracted from grimeage_agent.py (behavior-preserving split)."""
import json
import urllib.request as urllib
import ssl
from urllib.error import HTTPError
from ga_config import BASE


class RestClient:
    '''HTTP API wrapper with auto auth and refresh.'''
    
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.ctx = ssl.create_default_context()
        self.token = None
        self.refresh_token = None
        self._last_error = None

    
    def _request(self, method, path, data = (None,)):
        headers = {
            'Content-Type': 'application/json' }
        if self.token:
            headers['Authorization'] = f'''Bearer {self.token}'''
        body = json.dumps(data).encode() if data else None
        req = urllib.Request(f'''{BASE}{path}''', data = body, headers = headers, method = method)
        
        try:
            resp = urllib.urlopen(req, context = self.ctx, timeout = 15)
            return json.loads(resp.read())
        except HTTPError as e:
            err_body = e.read().decode()[:500]
            if e.code == 401 and self.refresh_token:
                refresh_req = urllib.Request(f'''{BASE}/api/auth/refresh''', data = json.dumps({
                    'refreshToken': self.refresh_token }).encode(), headers = {
                    'Content-Type': 'application/json' }, method = 'POST')
                refresh_resp = json.loads(urllib.urlopen(refresh_req, context = self.ctx, timeout = 15).read())
                self.token = refresh_resp.get('accessToken', self.token)
                headers['Authorization'] = f'''Bearer {self.token}'''
                req2 = urllib.Request(f'''{BASE}{path}''', data = body, headers = headers, method = method)
                return json.loads(urllib.urlopen(req2, context = self.ctx, timeout = 15).read())
            self._last_error = f'''HTTP {e.code}: {err_body}'''
            return None

    
    def login(self):
        data = self._request('POST', '/api/auth/login', {
            'email': self.email,
            'password': self.password })
        self.token = data.get('accessToken')
        self.refresh_token = data.get('refreshToken')
        return data

    
    def get(self, path):
        return self._request('GET', path)

    
    def post(self, path, data):
        return self._request('POST', path, data)

    
    def put(self, path, data):
        return self._request('PUT', path, data)

    
    def delete(self, path):
        return self._request('DELETE', path)


