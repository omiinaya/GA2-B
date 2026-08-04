#!/usr/bin/env python3
"""
GrimeAge2 Party Combat Daemon — Headless wrapper around AgentCoordinator.
Connects all chars, forms party, enables manual combat AI, manages reseeds.
Supervised by gr2-brain.py.
"""
import sys
sys.stdout.reconfigure(line_buffering=True)
import asyncio
import os
import time
import signal

# Portable import: try the daemon's own directory first, then canonical
# deployment paths (repo layout = same dir; live box = /home/hindsight).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (_SCRIPT_DIR, '/home/hindsight', os.path.expanduser('~/.hermes/scripts')):
    if _p not in sys.path and os.path.isdir(_p):
        sys.path.insert(0, _p)
from grimeage_agent import AgentCoordinator

PID_FILE = os.path.expanduser('~/.hermes/gr2-combat-daemon.pid')
LOG_FILE = os.path.expanduser('~/.hermes/gr2-combat-daemon.log')


def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)


async def main():
    coord = AgentCoordinator()

    def shutdown():
        coord._running = False
        log('🛑 Shutting down...')

    signal.signal(signal.SIGTERM, lambda *a: shutdown())
    signal.signal(signal.SIGINT, lambda *a: shutdown())

    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    try:
        # Redirect stdout to log file for daemon mode
        orig_stdout = sys.stdout
        try:
            log_fh = open(LOG_FILE, 'a')
            log_fh.reconfigure(line_buffering=True)  # flush every line — block buffering hides logs until 8KB
            sys.stdout = log_fh
        except OSError:
            log_fh = None

        try:
            await coord.start()
            # Headless: ignore CLI input, just let the main loop run
            while coord._running:
                await asyncio.sleep(5)
        except KeyboardInterrupt:
            pass
        finally:
            if log_fh:
                log_fh.close()
                sys.stdout = orig_stdout
            await coord.stop()
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


if __name__ == '__main__':
    asyncio.run(main())
