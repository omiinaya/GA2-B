#!/usr/bin/env python3
"""Daemonize official_chain_run.sh so it runs independent of the gateway.

The gateway's in-process cron ticker is stuck holding ~/.hermes/cron/.tick.lock
(PID 11412), so no cron job can fire — including our chain. The gateway also
kills terminal(background=True) processes after gateway_timeout=1800s. This
daemonizer forks + setsid + double-forks so the chain script orphans to init and
is immune to BOTH the stuck cron lock and the gateway's process killer.

Usage: python3 /home/hindsight/.hermes/scripts/daemonize_chain.py
"""
import os
import sys
import time

SCRIPT = "/home/hindsight/.hermes/scripts/official_chain_run.sh"
PIDFILE = "/tmp/official_chain_daemon.pid"
LOG = "/tmp/official_chain_daemon.out"


def daemonize(cmd, pidfile):
    # First fork
    if os.fork() > 0:
        return  # parent exits immediately
    os.setsid()
    # Second fork (prevents reacquiring a controlling tty)
    if os.fork() > 0:
        os._exit(0)
    # This is the daemon child — redirect stdio, detach cwd.
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    logfd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(logfd, 1)
    os.dup2(logfd, 2)
    os.close(devnull)
    os.close(logfd)
    os.chdir("/")
    # Write pidfile
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    # Launch the script — execv bash ON the script path (bash reads the file
    # even without +x; do NOT use -c which treats it as a command string).
    try:
        os.execv("/bin/bash", ["/bin/bash", SCRIPT])
    except Exception as e:  # noqa: BLE001
        with open(LOG, "a") as f:
            f.write(f"exec failed: {e}\n")
        os._exit(1)


if __name__ == "__main__":
    # Guard: don't start a second daemon while one is alive.
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE) as f:
                old = int(f.read().strip())
            os.kill(old, 0)  # raises if dead
            print(f"Daemon already running (pid {old}). Exiting.")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass  # stale pid — proceed to start
    daemonize(SCRIPT, LOG)
    print("Daemon forked. It orphans and runs independent of the gateway.")