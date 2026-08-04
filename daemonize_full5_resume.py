#!/usr/bin/env python3
"""Daemonize the full5 benchmark resume so a gateway restart can't kill it.

The first resume run (PID 982889) was a gateway-tracked background process and
was killed when hermes-gateway restarted (~19:37), freezing the log at 279/1540.
This daemonizer double-forks the resume command (same args + --resume, same
output dir so scored per-question JSONs and ingestion checkpoints are reused)
to PPID=1. The auth adapter on :4004 must be healthy (daemonize_auth_adapter.py).

Usage: python3 /home/hindsight/.hermes/scripts/daemonize_full5_resume.py
"""
import os
import sys

VENV_PY = "/home/hindsight/spacetime-memory/.venv/bin/python3"
LOG = "/tmp/mem0bench_full5.log"
PIDFILE = "/tmp/full5_resume_daemon.pid"
CMD = [
    VENV_PY, "-m", "benchmarks.locomo.run",
    "--project-name", "stmem-full5-zen",
    "--backend", "stmem",
    "--stmem-db", "spacetime-memory-v2",
    "--stmem-host", "192.168.1.10", "--stmem-port", "3001",
    "--answerer-model", "deepseek-v4-flash-free",
    "--judge-model", "deepseek-v4-flash-free",
    "--conversations", "0,1,2,3,4,5,6,7,8,9",
    "--top-k", "200", "--max-workers", "4",
    "--dataset-path", "/home/hindsight/spacetime-memory/data/locomo10.json",
    "--output-dir", "/tmp/mem0bench/full5",
    "--max-questions", "1540",
    "--resume",
]
ENV = {
    "OTEL_ENABLED": "false",
    "LLM_BASE_URL": "http://localhost:4004/v1",
    "OPENAI_API_KEY": "dummy-key",
    "PYTHONUNBUFFERED": "1",
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
    os.chdir("/home/hindsight/mem0/evaluation")
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    with open(LOG, "a") as f:
        f.write(f"\n[resume daemon start {time_str()}]\n")
    try:
        os.execve(VENV_PY, CMD, {**os.environ, **ENV})
    except Exception as e:  # noqa: BLE001
        with open(LOG, "a") as f:
            f.write(f"exec failed: {e}\n")
        os._exit(1)


def time_str():
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE) as f:
                old = int(f.read().strip())
            os.kill(old, 0)
            print(f"Resume daemon already running (pid {old}). Exiting.")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass
    daemonize()
    print("Full5 resume daemon forked (PPID=1). It survives gateway restarts.")
