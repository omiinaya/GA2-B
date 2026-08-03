#!/usr/bin/env python3
"""Daemonize full5_postprocess.sh so it runs independent of the gateway.

The current full5 benchmark was restarted as a raw `timeout` command (resume),
so the launcher script's post-processing (repair + verdict extraction) will
NEVER fire when it exits. This daemonizer orphans the standalone postprocessor
to init (double-fork + setsid), immune to the stuck cron lock and the gateway's
1800s process killer. The postprocessor waits for benchmark exit, repairs
contamination-damaged questions, extracts the verdict to
/tmp/mem0bench_full5.out, and the existing verdict watcher delivers it.

Usage: python3 /home/hindsight/.hermes/scripts/daemonize_full5_postprocess.py
"""
import os
import sys

SCRIPT = "/home/hindsight/.hermes/scripts/full5_postprocess.sh"
PIDFILE = "/tmp/full5_postprocess_daemon.pid"
LOG = "/tmp/full5_postprocess_daemon.out"


def daemonize(cmd, logpath):
    if os.fork() > 0:
        return
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    logfd = os.open(logpath, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(logfd, 1)
    os.dup2(logfd, 2)
    os.close(devnull)
    os.close(logfd)
    os.chdir("/")
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    try:
        os.execv("/bin/bash", ["/bin/bash", SCRIPT])
    except Exception as e:  # noqa: BLE001
        with open(logpath, "a") as f:
            f.write(f"exec failed: {e}\n")
        os._exit(1)


if __name__ == "__main__":
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE) as f:
                old = int(f.read().strip())
            os.kill(old, 0)
            print(f"Daemon already running (pid {old}). Exiting.")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass
    daemonize(SCRIPT, LOG)
    print("Postprocess daemon forked. It orphans and runs independent of the gateway.")
