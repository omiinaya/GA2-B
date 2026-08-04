#!/usr/bin/env python3
"""Daemonize the ASYNC auth+reasoning adapter on :4004 (Benchmark LLM chain).

Replaces the sync adapter (single httpx.Client serialized concurrent requests;
external calls timed out at 20s+ under the benchmark's 4-worker load). The
async version uses httpx.AsyncClient with a 64-connection pool — 10 concurrent
requests measured at 4.6s wall vs sync's saturation. Same chain:
:4004 (auth_adapter_async) -> :4002 (oc-zen-relay) -> opencode.ai/zen/v1.

Usage: python3 /home/hindsight/.hermes/scripts/daemonize_auth_adapter_async.py
"""
import os
import sys

SCRIPT = "/home/hindsight/.hermes/skills/software-development/spacetime-memory-development/scripts/auth_adapter_async.py"
VENV_PY = "/home/hindsight/spacetime-memory/.venv/bin/python3"
PIDFILE = "/tmp/auth_adapter_4004.pid"
LOG = "/tmp/auth_adapter_4004.log"
ENV = {
    "UPSTREAM": "http://localhost:4002",
    "PORT": "4004",
    "API_KEY": "public",
}


def daemonize():
    if os.fork() > 0:
        return
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    logfd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(logfd, 1)
    os.dup2(logfd, 2)
    os.close(devnull)
    os.close(logfd)
    os.chdir("/")
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    try:
        os.execve(VENV_PY, [VENV_PY, SCRIPT], {**os.environ, **ENV})
    except Exception as e:  # noqa: BLE001
        with open(LOG, "a") as f:
            f.write(f"exec failed: {e}\n")
        os._exit(1)


if __name__ == "__main__":
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE) as f:
                old = int(f.read().strip())
            os.kill(old, 0)
            print(f"Adapter already running (pid {old}). Exiting.")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass
    daemonize()
    print("Async auth adapter daemon forked on :4004. It orphans and runs independent of the gateway.")
