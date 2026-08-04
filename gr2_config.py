"""gr2_config — credentials, API endpoints, paths, and shared imports."""
import os
import sys
# === CONFIG ===
# Credentials loaded in priority order:
# 1. GR2_EMAIL / GR2_PASSWORD environment variables
# 2. .env file in the same directory (KEY=VALUE format, not committed)
CREDENTIALS = {}
email = os.environ.get('GR2_EMAIL')
password = os.environ.get('GR2_PASSWORD')
if email and password:
    CREDENTIALS = {"email": email, "password": password}
else:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        k, v = line.split('=', 1)
                        if k == 'GR2_EMAIL':
                            email = v
                        elif k == 'GR2_PASSWORD':
                            password = v
    if email and password:
        CREDENTIALS = {"email": email, "password": password}
    # (missing creds: CREDENTIALS stays {} — orchestrator checks & exits)
API_BASE = "https://grimeage2.com"
WS_BASE = "wss://grimeage2.com"
PID_FILE = os.path.expanduser('~/.hermes/gr2-combat-daemon.pid')
LOG_FILE = os.path.expanduser('~/.hermes/gr2-combat-daemon.log')


