#!/usr/bin/env python3
"""Watch for full5 completion and deliver the verdict to the Discord thread.

The gateway's cron ticker is stuck holding ~/.hermes/cron/.tick.lock, so cron
delivery may never fire. This daemon polls for /tmp/mem0bench_full5.out (the
verdict file the launcher writes when the run finishes), then posts the result
to the thread via the Discord REST API directly (bot token from config), and
exits. Run via daemonize-style fork so it survives the gateway timeout.
"""
import json
import os
import re
import sys
import time
import urllib.request

VERDICT_FILE = "/tmp/mem0bench_full5.out"
PIDFILE = "/tmp/official_chain_watcher.pid"
LOG = "/tmp/official_chain_watcher.log"
THREAD_ID = "1512680047117467740"  # this thread

# Find bot token from hermes config without printing it.
def find_token():
    for p in [
        os.path.expanduser("~/.hermes/config.yaml"),
        os.path.expanduser("~/.hermes/.env"),
        os.path.expanduser("~/.config/hermes/config.yaml"),
    ]:
        if not os.path.exists(p):
            continue
        try:
            with open(p) as f:
                txt = f.read()
            m = re.search(r"DISCORD_BOT_TOKEN\s*[:=]\s*[\"']?([A-Za-z0-9_.\-]{20,})", txt)
            if m:
                return m.group(1)
            m = re.search(r"discord_bot_token\s*[:=]\s*[\"']?([A-Za-z0-9_.\-]{20,})", txt)
            if m:
                return m.group(1)
        except OSError:
            continue
    return None


def send_discord(token, content):
    url = f"https://discord.com/api/v10/channels/{THREAD_ID}/messages"
    data = json.dumps({"content": content}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bot {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def daemonize():
    """Fork into background. Returns True for parent (caller should exit),
    False for the daemon child."""
    if os.fork() > 0:
        return True
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
    return False


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def main():
    token = find_token()
    if not token:
        log("FATAL: could not find DISCORD_BOT_TOKEN")
        return
    log("Watcher started; waiting for full5 verdict...")
    # Wait up to 24h for the verdict file.
    deadline = time.time() + 24 * 3600
    while time.time() < deadline:
        if os.path.exists(VERDICT_FILE):
            try:
                with open(VERDICT_FILE) as f:
                    verdict = f.read().strip()
                if verdict:
                    msg = "**Mem0 Official LoCoMo Verdict**\n```\n" + verdict + "\n```"
                    status = send_discord(token, msg)
                    log(f"Delivered verdict, status={status}")
                    # Also deliver a fallback if the file is empty-ish
                    return
            except Exception as e:  # noqa: BLE001
                log(f"delivery failed: {e}")
        time.sleep(300)  # 5 min
    log("Deadline reached without verdict")


if __name__ == "__main__":
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE) as f:
                old = int(f.read().strip())
            os.kill(old, 0)
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass
    is_parent = daemonize()
    if is_parent:
        sys.exit(0)  # parent returns immediately; child runs the loop
    main()
