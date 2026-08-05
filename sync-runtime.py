#!/usr/bin/env python3
"""Sync GA2-B source files to the runtime directory (~/.hermes/scripts).

The supervisor runs from ~/.hermes/scripts (systemd service), while the repo
is the source of truth at /home/hindsight/GA2-B. This script copies every
module + script to the runtime dir using shutil.copyfile — plain `cp` through
a timed-out shell can TRUNCATE the destination to 0 bytes (observed twice
2026-08-05), so Python's copyfile is the reliable path.

Usage:
    python3 sync-runtime.py            # sync repo -> ~/.hermes/scripts
    python3 sync-runtime.py --verify   # also diff every file back
After syncing, restart the supervisor:
    su-run 'systemctl restart gr2-autofarm-supervisor.service'
"""
import os
import shutil
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
RUNTIME = '/home/hindsight/.hermes/scripts'

FILES = [
    'ga_analytics.py', 'ga_catalog.py', 'ga_character.py', 'ga_config.py',
    'ga_coordinator.py', 'ga_db.py', 'ga_gear.py', 'ga_rest.py', 'ga_world.py',
    'gr2-autofarm-supervisor.py', 'gr2-brain.py', 'gr2-combat-daemon.py',
    'gr2-pool-gear.py', 'gr2-watchdog.py', 'gr2_api.py', 'gr2_config.py',
    'gr2_data.py', 'gr2_state.py', 'gr2_ws.py', 'grimeage_agent.py',
]


def main():
    verify = '--verify' in sys.argv
    copied = 0
    for f in FILES:
        src = os.path.join(REPO, f)
        dst = os.path.join(RUNTIME, f)
        if not os.path.exists(src):
            continue
        shutil.copyfile(src, dst)
        copied += 1
    print(f'synced {copied} files -> {RUNTIME}')
    if verify:
        bad = 0
        for f in FILES:
            src = os.path.join(REPO, f)
            dst = os.path.join(RUNTIME, f)
            if not os.path.exists(src):
                continue
            try:
                with open(src, 'rb') as a, open(dst, 'rb') as b:
                    if a.read() != b.read():
                        bad += 1
                        print(f'  MISMATCH: {f}')
            except OSError as e:
                bad += 1
                print(f'  READ ERR: {f}: {e}')
        print(f'verify: {"OK (all match)" if bad == 0 else f"{bad} MISMATCHES"}')
        return 1 if bad else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
