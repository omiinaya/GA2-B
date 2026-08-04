"""gr2_api — REST helpers for the GrimeAge2 API."""
import json
import urllib.request
from gr2_config import API_BASE

def api_post(path, data, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(
        f'{API_BASE}{path}',
        data=json.dumps(data).encode() if data else None,
        headers=headers,
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def api_get(path, token):
    req = urllib.request.Request(
        f'{API_BASE}{path}',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def api_put(path, data, token):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(
        f'{API_BASE}{path}',
        data=json.dumps(data).encode(),
        headers=headers,
        method='PUT',
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        return json.loads(raw) if raw.strip() else {}



