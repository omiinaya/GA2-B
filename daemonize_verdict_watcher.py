#!/usr/bin/env python3
"""Watch for full5 completion and deliver the verdict to the Discord thread.

The gateway's cron ticker is stuck holding ~/.hermes/cron/.tick.lock, so cron
delivery may never fire. This daemon polls for /tmp/mem0bench_full5.out (the
verdict file the launcher writes when the run finishes), then posts the result
to the thread via the Discord REST API directly (bot token from config), and
exits. Run via daemonize-style fork so it survives the gateway timeout.

RACE-CONDITION HARDENING:
  The launcher writes `exit=$rc` to the verdict file FIRST, then overwrites it
  with the real extracted metrics a few seconds later. Delivering on the first
  non-empty read would post just "exit=0" and exit forever, losing the verdict.
  So we require BOTH:
    (a) the content contains the real verdict marker (FULL OFFICIAL /
        MEM0_PUBLISHED / "accuracy" with a percent), AND
    (b) the file mtime has been stable for STABLE_FOR seconds (writes done).
  If the file exists but fails either check, keep polling instead of exiting.
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
STABLE_FOR = 90  # seconds the file must be untouched before we trust it
WAIT_DEADLINE = 30 * 3600  # up to 30h for the verdict


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


def looks_like_real_verdict(text):
    """True only for the final extraction block, not the 'exit=0' placeholder."""
    if "FULL OFFICIAL" in text or "MEM0_PUBLISHED" in text:
        return True
    # LoCoMo results lines look like: "7d: 87.50% (42/48)" or similar
    if "accuracy" in text.lower() and "%" in text:
        return True
    return False


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
    log("Watcher started (hardened); waiting for full5 verdict...")
    deadline = time.time() + WAIT_DEADLINE
    while time.time() < deadline:
        if os.path.exists(VERDICT_FILE):
            try:
                with open(VERDICT_FILE) as f:
                    verdict = f.read().strip()
                mtime = os.path.getmtime(VERDICT_FILE)
                age = time.time() - mtime
                if not verdict:
                    log("verdict file empty, still writing")
                elif age < STABLE_FOR:
                    log(f"verdict file still being written (age {age:.0f}s < {STABLE_FOR}s)")
                elif not looks_like_real_verdict(verdict):
                    log(f"verdict file present but placeholder-only ({verdict[:60]!r}), waiting for extraction")
                else:
                    msg = "**Mem0 Official LoCoMo Verdict**\n```\n" + verdict + "\n```"
                    status = send_discord(token, msg)
                    log(f"Delivered verdict, status={status}")
                    return
            except Exception as e:  # noqa: BLE001
                log(f"check failed (retrying): {e}")
        time.sleep(60)  # 1 min poll
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
