#!/usr/bin/env python3
"""gr2-autofarm-supervisor.py — Persistent 3-char auto-farm supervisor.

The server allows only ONE concurrent WebSocket per account (2026-08-04
discovery). Auto-farm persists server-side after WS disconnect — so the
winning strategy is: all 3 chars auto-farm SIMULTANEOUSLY, toggled via
sequential brief-WS connections (never 2 WS at once).

⚠️ WS-slot discipline (verified 2026-08-04): a char that needs to TRAVEL or
RESPAWN can only hold a WS while no other char is actively auto-farming.
With 2 chars AF-on, a third char's WS gets evicted within ~3s (the proven
baseline harness fails identically). Sequence therefore is:
  1. stop AF on ALL chars          (free the slot)
  2. travel/respawn the target     (one char at a time)
  3. re-enable AF on all chars     (fast toggles — these work while others farm)

Uses CharacterAgent.connect() (its _message_loop keeps the WS alive and
processes game_state) + agent.disconnect() for clean task cancellation —
the exact pattern proven by gr2-auto-baseline.py. A raw websockets client
gets closed by the server because nothing processes game_state.

Supervised by gr2-brain.py (auto-restarts like the old combat daemon).

Usage: python3 gr2-autofarm-supervisor.py   (foreground, or via brain/systemd)
"""
import sys
sys.stdout.reconfigure(line_buffering=True)
import asyncio
import json
import os
import signal
import time
from collections import deque

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (_SCRIPT_DIR, '/home/hindsight', os.path.expanduser('~/.hermes/scripts')):
    if _p not in sys.path and os.path.isdir(_p):
        sys.path.insert(0, _p)

from grimeage_agent import (RestClient, Analytics, ACCOUNT_EMAIL, ACCOUNT_PASSWORD,
                            CHARACTERS, CharacterAgent, init_db)

PID_FILE = os.path.expanduser('~/.hermes/gr2-autofarm-supervisor.pid')
LOG_FILE = os.path.expanduser('~/.hermes/gr2-autofarm-supervisor.log')
STATE_FILE = os.path.expanduser('~/.hermes/gr2-autofarm-state.json')

PARTY_ZONE = 64188      # Windy Meadow Gates (Lv21-24) — direct from Gludios 149
CYCLE_S = int(os.environ.get('GR2_CYCLE', '90'))       # main loop cadence
RATE_WINDOW_S = int(os.environ.get('GR2_RATE_WINDOW', '600'))  # gold-rate window

# Per-char hunting zone. 64188 (Windy Meadow Gates, Lv21-24) is the shared
# party zone — but Lv21 BuffBot keeps DYING there (baseline-verified, died on
# every attempt). He's routed to Windmill Plains South (53, Lv20-22): the only
# 1-hop safe zone from Gludios, AND a Trial of Ascendancy target zone (Bandit
# Scouts), so his quest progresses while farming. HermesHeal/ShieldBot (Lv23)
# handle 64188. (53 has a Wind Strike immunity quirk for spellcasters — auto-
# attack still farms; a dagger/bow later re-rolls him to a melee layout.)
CHAR_ZONE = {
    1069: 53,     # BuffBot  — Windmill Plains South (Lv20-22, 1-hop safe + quest)
    1070: 64188,  # HermesHeal — Windy Meadow Gates (Lv21-24)
    1071: 64188,  # ShieldBot  — Windy Meadow Gates (Lv21-24)
}

# Toggle priority — the server caps ~2 active sessions, and the LAST char
# toggled is the one that loses the slot race. Order matters: the strongest
# farmers must claim slots FIRST so they're never dropped. ShieldBot
# (p_atk 82 Mithril Warhammer, 1416 HP, full Steel) + HermesHeal (44k/hr
# baseline) are the money-makers; BuffBot (Lv21, weakest) is the expendable
# third who gets capped when the server limits us to 2.
PRIORITY = [1071, 1070, 1069]   # ShieldBot, HermesHeal, BuffBot

PARTY_ZONE = 64188      # default/shared hunting zone

_gold_history = {}      # char_id -> deque[(t, gold)]
_running = True
# Consecutive AF-toggle failures per char → exponential backoff. The server
# allows only ~2 active sessions per account (verified 2026-08-04: the 3rd
# char's WS gets evicted within ~2s while 2 others farm). Retrying the capped
# char every cycle wastes connects and hammers the server — back off instead.
_af_fail = {cid: 0 for cid in CHARACTERS}
_last_af_attempt = {cid: 0.0 for cid in CHARACTERS}


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
    except OSError:
        pass


def snapshot(rest):
    chars = rest.get('/api/characters')
    if not isinstance(chars, list):
        return {}
    return {c['id']: {
        'name': c.get('name'), 'gold': c.get('gold'), 'hp': c.get('hp'),
        'maxHp': c.get('maxHp'), 'level': c.get('level'),
        'zone': c.get('currentZoneId'), 'state': c.get('state'),
        'af': c.get('isAutoFarming')} for c in chars}


def rest_af(rest, cid):
    chars = rest.get('/api/characters')
    if isinstance(chars, list):
        for c in chars:
            if c.get('id') == cid:
                return c.get('isAutoFarming')
    return None


async def agent_for(rest, cid, cfg, wait_zone=False, max_wait=20):
    """Connect a CharacterAgent, wait for game_state (+ optional zone).
    Returns (agent, zone) or (None, None). Caller MUST disconnect()."""
    an = Analytics(init_db())
    a = CharacterAgent(cid, cfg, rest, an)
    a._keep_running = True
    ok = await a.connect()
    if not ok:
        try:
            await a.disconnect()
        except Exception:
            pass
        return None, None
    t0 = time.time()
    while time.time() - t0 < max_wait:
        await asyncio.sleep(0.5)
        if a.connected and a.current_zone_id is not None:
            if not wait_zone or a.current_zone_id == wait_zone:
                return a, a.current_zone_id
            return a, a.current_zone_id
    return a, a.current_zone_id


async def respawn_char(rest, cid, cfg):
    chars = rest.get('/api/characters')
    cur = next((c for c in chars if c.get('id') == cid), None)
    if not cur:
        return False, 'char-not-found'
    if (cur.get('hp') or 0) > 0:
        return True, 'already-alive'
    a, _ = await agent_for(rest, cid, cfg, max_wait=15)
    if a is None:
        return False, 'connect-failed'
    try:
        await a.ws_send('respawn', {})
        for _ in range(25):  # up to 12.5s
            await asyncio.sleep(0.5)
            chars = rest.get('/api/characters')
            cur = next((c for c in chars if c.get('id') == cid), None)
            if cur and (cur.get('hp') or 0) > 0:
                return True, f'respawned hp={cur["hp"]}'
        return False, 'respawn-timeout'
    finally:
        await a.disconnect()


async def travel_to_zone(rest, cid, cfg, target=PARTY_ZONE):
    chars = rest.get('/api/characters')
    cur = next((c for c in chars if c.get('id') == cid), None)
    if not cur:
        return False, 'char-not-found'
    if cur.get('currentZoneId') == target:
        return True, f'already-in-{target}'
    a, zone = await agent_for(rest, cid, cfg, max_wait=15)
    if a is None:
        return False, 'connect-failed'
    try:
        if a.current_zone_id == target:
            return True, f'already-in-{target}'
        # force-exit combat + rest-toggle before travel (server rejects travel
        # in combat/resting — pitfalls #45/#75)
        try:
            await a.ws_send('combat:stop_attack', {})
        except Exception:
            pass
        await asyncio.sleep(0.5)
        try:
            await a.ws_send('combat:rest', {})
            await asyncio.sleep(0.3)
            await a.ws_send('combat:cancel_rest', {})
            await asyncio.sleep(0.3)
        except Exception:
            pass
        await a.ws_send('start_travel', {'path': [target]})
        a.combat_state = 'TRAVELING'
        for _ in range(40):  # up to 20s
            await asyncio.sleep(0.5)
            if a.current_zone_id == target:
                return True, f'arrived-{target}'
        chars = rest.get('/api/characters')
        cur = next((c for c in chars if c.get('id') == cid), None)
        if cur and cur.get('currentZoneId') == target:
            return True, f'arrived-{target}-rest'
        return False, f'travel-timeout-still-{a.current_zone_id}'
    finally:
        await a.disconnect()


async def toggle_af(rest, cid, cfg, on=True):
    """REST-state-aware AF toggle. Never blind-toggles (stale local flag bug).

    The baseline-proven pattern: connect → WAIT for game_state (which populates
    the agent's is_autofarming from the SERVER's truth) → start/stop_autofarm()
    only sends combat:toggle_autofarm when the local flag differs from desired.
    Forcing the local flag (as an earlier version did) makes the toggle ALWAYS
    fire — flipping an already-ON server state to OFF."""
    actual = rest_af(rest, cid)
    if actual == on:
        return True, f'already-{"ON" if on else "OFF"}'
    a, _ = await agent_for(rest, cid, cfg, max_wait=15)
    if a is None:
        return False, 'connect-failed'
    try:
        # Sync the local flag with the server before deciding to toggle. The
        # agent's game_state handler sets is_autofarming from the WS payload;
        # if it's still the init default, re-read from REST.
        chars = rest.get('/api/characters')
        cur = next((c for c in chars if c.get('id') == cid), None)
        if cur is not None:
            a.is_autofarming = bool(cur.get('isAutoFarming'))
        if on:
            await a.start_autofarm()
        else:
            await a.stop_autofarm()
        await asyncio.sleep(2)
        after = rest_af(rest, cid)
        if after != on:
            # Rejected — likely invisible server-side party state (pitfall #38)
            await a.ws_send('party:leave', {})
            a.is_in_party = False
            a.party_members = {}
            await asyncio.sleep(3)
            chars = rest.get('/api/characters')
            cur = next((c for c in chars if c.get('id') == cid), None)
            if cur is not None:
                a.is_autofarming = bool(cur.get('isAutoFarming'))
            if on:
                await a.start_autofarm()
            else:
                await a.stop_autofarm()
            await asyncio.sleep(2)
            after = rest_af(rest, cid)
        return True, f'toggled->{"ON" if after else "OFF"}'
    finally:
        await a.disconnect()


async def ensure_all_farming(rest, cid_list):
    """Minimal-disruption sweep.

    Principle: NEVER stop a working farmer to fix another char — every stop
    costs that farmer ~15-30s of gold. A DEAD char has a free WS slot (it's
    not farming), so it can be respawned/traveled directly. A LIVE char out of
    zone needs a slot: only then stop the LOWEST-priority farmer, briefly.

    Order: fix dead chars first (free slots), then out-of-zone live chars
    (only stopping a farmer if all 2 slots are held by farmers), then toggle
    AF ON for any char that's alive, in-zone, and AF-off."""
    logmsg = []
    chars = rest.get('/api/characters')
    by_id = {c['id']: c for c in chars} if isinstance(chars, list) else {}

    dead = [cid for cid in cid_list if (by_id.get(cid, {}).get('hp') or 0) <= 0]
    out_of_zone = [cid for cid in cid_list
                   if cid not in dead and by_id.get(cid, {}).get('currentZoneId') != CHAR_ZONE.get(cid, PARTY_ZONE)]
    af_off = [cid for cid in cid_list
              if cid not in dead and cid not in out_of_zone and rest_af(rest, cid) is not True]

    # 1. Fix dead chars. Only resurrect if high-priority OR fewer than 2 farmers
    #    are active — resurrecting a disposable 3rd wheel by pausing a working
    #    farmer costs more output than the resurrection gains (the swap will
    #    just evict it again). A dead low-priority char waits until a slot frees.
    for cid in dead:
        cfg = CHARACTERS[cid]
        farmers = [x for x in cid_list if x != cid and rest_af(rest, x) is True]
        if len(farmers) >= 2:
            # 2 farmers busy — only resurrect if this char is in the top-2 slots
            if cid_list.index(cid) >= 2:
                logmsg.append(f'{cfg["name"]}:defer (2 farmers busy, low priority)')
                continue
            victim = max(farmers, key=lambda x: cid_list.index(x))
            ok, msg = await toggle_af(rest, victim, CHARACTERS[victim], on=False)
            logmsg.append(f'{CHARACTERS[victim]["name"]}:pause:{msg}')
            await asyncio.sleep(3)
        else:
            victim = None
        ok, msg = await respawn_char(rest, cid, cfg)
        logmsg.append(f'{cfg["name"]}:respawn:{msg}')
        await asyncio.sleep(3)
        # after respawn the char is usually in a city — travel it too
        ok, msg = await travel_to_zone(rest, cid, cfg, CHAR_ZONE.get(cid, PARTY_ZONE))
        logmsg.append(f'{cfg["name"]}:travel:{msg}')
        await asyncio.sleep(3)
        # toggle AF on (it'll be swapped out later if a higher-priority char waits)
        if rest_af(rest, cid) is not True:
            ok, msg = await toggle_af(rest, cid, cfg, on=True)
            logmsg.append(f'{cfg["name"]}:af:{msg}')
            await asyncio.sleep(3)
        # restore the paused farmer
        if victim is not None and rest_af(rest, victim) is not True:
            ok, msg = await toggle_af(rest, victim, CHARACTERS[victim], on=True)
            logmsg.append(f'{CHARACTERS[victim]["name"]}:resume:{msg}')
            await asyncio.sleep(3)

    # 2. Fix live chars out of zone. Count how many farmers hold slots; if all
    #    slots are busy, stop ONE low-priority farmer for the travel window.
    for cid in out_of_zone:
        cfg = CHARACTERS[cid]
        # count current farmers (excluding this char)
        farmers = [x for x in cid_list if x != cid and rest_af(rest, x) is True]
        victim = None
        if len(farmers) >= 2:
            # all slots busy — stop the lowest-priority farmer briefly
            victim = farmers[-1]  # reverse-id order = lowest priority roughly
            ok, msg = await toggle_af(rest, victim, CHARACTERS[victim], on=False)
            logmsg.append(f'{CHARACTERS[victim]["name"]}:pause:{msg}')
            await asyncio.sleep(3)
        ok, msg = await travel_to_zone(rest, cid, cfg, CHAR_ZONE.get(cid, PARTY_ZONE))
        logmsg.append(f'{cfg["name"]}:travel:{msg}')
        await asyncio.sleep(3)
        # restore the paused farmer
        if victim is not None and rest_af(rest, victim) is not True:
            ok, msg = await toggle_af(rest, victim, CHARACTERS[victim], on=True)
            logmsg.append(f'{CHARACTERS[victim]["name"]}:resume:{msg}')
            await asyncio.sleep(3)

    # 3. Toggle AF ON for alive in-zone chars that are off (respect backoff).
    for cid in af_off:
        if time.time() - _last_af_attempt[cid] < (2 ** _af_fail[cid]) * 20:
            continue
        _last_af_attempt[cid] = time.time()
        ok, msg = await toggle_af(rest, cid, CHARACTERS[cid], on=True)
        if ok and 'OFF' in msg:
            _af_fail[cid] += 1
        else:
            _af_fail[cid] = 0
            logmsg.append(f'{CHARACTERS[cid]["name"]}:af:{msg}')
        await asyncio.sleep(3)

    # 4. Priority enforcement: if a HIGHER-priority char is AF-off while a
    #    LOWER-priority one farms, swap them so the strongest pair holds the
    #    2 active slots. (Server caps ~2; this guarantees ShieldBot gets in
    #    ahead of BuffBot whenever a slot frees.)
    for cid in cid_list:
        if rest_af(rest, cid) is True:
            continue  # already farming — fine
        farmers = [x for x in cid_list if rest_af(rest, x) is True]
        if not farmers:
            break
        # evict the farmer with the LOWEST priority rank
        victim = max(farmers, key=lambda x: cid_list.index(x))
        if cid_list.index(victim) < cid_list.index(cid):
            continue  # victim is higher priority than the waiting char
        ok, msg = await toggle_af(rest, victim, CHARACTERS[victim], on=False)
        logmsg.append(f'{CHARACTERS[victim]["name"]}:evict:{msg}')
        await asyncio.sleep(3)
        ok, msg = await toggle_af(rest, cid, CHARACTERS[cid], on=True)
        logmsg.append(f'{CHARACTERS[cid]["name"]}:swap-in:{msg}')
        await asyncio.sleep(3)
        break  # one swap per sweep is enough
    return logmsg


def record_gold(snap):
    now = time.time()
    for cid, info in snap.items():
        _gold_history.setdefault(cid, deque(maxlen=400)).append((now, info.get('gold') or 0))


def report_rates(snap):
    now = time.time()
    out = {}
    for cid, info in snap.items():
        hist = _gold_history.get(cid, [])
        if len(hist) < 2:
            out[cid] = None
            continue
        t0, g0 = hist[0]
        dt = now - t0
        if dt < 60:
            out[cid] = None
            continue
        g1 = info.get('gold') or 0
        out[cid] = {'gained': g1 - g0, 'hr': (g1 - g0) * 3600 / dt,
                    'hp': info.get('hp'), 'zone': info.get('zone'),
                    'af': info.get('af'), 'state': info.get('state')}
    return out


async def main():
    r = RestClient(ACCOUNT_EMAIL, ACCOUNT_PASSWORD)
    r.login()
    if not getattr(r, 'token', None):
        log('LOGIN FAILED — exiting')
        return 1

    snap = snapshot(r)
    log(f'start {json.dumps(snap)}')
    record_gold(snap)

    cid_list = list(PRIORITY)
    logmsg = await ensure_all_farming(r, cid_list)
    for m in logmsg:
        log(m)

    # Verify + retry pattern (stale party state can reject the first attempt).
    # Uses exponential backoff so a char that can't hold a session (2-active
    # cap) isn't hammered.
    for attempt in range(3):
        off = [cid for cid in cid_list if rest_af(r, cid) is not True]
        if not off:
            break
        waited = False
        for cid in off:
            if time.time() - _last_af_attempt[cid] < (2 ** _af_fail[cid]) * 15:
                waited = True
                continue
            _last_af_attempt[cid] = time.time()
            ok, msg = await toggle_af(r, cid, CHARACTERS[cid], on=True)
            if ok and 'OFF' in msg:
                _af_fail[cid] += 1
            else:
                _af_fail[cid] = 0
            log(f"retry ON {CHARACTERS[cid]['name']}: {msg}")
            await asyncio.sleep(4)
        if waited and not any(time.time() - _last_af_attempt[c] >= (2 ** _af_fail[c]) * 15 for c in off):
            # everyone in backoff — give the loop a chance to settle
            await asyncio.sleep(30)

    log(f'AF sweep complete: {json.dumps({CHARACTERS[cid]["name"]: rest_af(r, cid) for cid in cid_list})}')

    # Persistent loop — light maintenance: re-toggle AF if a char dropped off,
    # respawn if dead. Travel only when a char is out of zone (rare after the
    # initial sweep; slot-discipline applies automatically). Chars in backoff
    # (capped by the 2-active session limit) are skipped until their timer
    # lapses, so we don't waste connects on a char the server won't accept.
    last_rate_log = time.time()
    while _running:
        try:
            await asyncio.sleep(CYCLE_S)
            # Re-write PID each cycle so the brain's supervision always finds
            # us (startup write can race with an old instance's cleanup).
            try:
                with open(PID_FILE, 'w') as f:
                    f.write(str(os.getpid()))
            except OSError:
                pass
            snap = snapshot(r)
            record_gold(snap)
            changed = []
            # quick pass: dead chars need respawn (slot discipline: stop others)
            dead = [cid for cid in cid_list if (snap.get(cid, {}).get('hp') or 0) <= 0]
            out_of_zone = [cid for cid in cid_list if snap.get(cid, {}).get('zone') != CHAR_ZONE.get(cid, PARTY_ZONE)]
            if dead or out_of_zone:
                logmsg = await ensure_all_farming(r, cid_list)
                changed.extend(logmsg)
                # 'ensure_all_farming' re-toggles everyone; reset backoff on success
                for cid in cid_list:
                    if rest_af(r, cid) is True:
                        _af_fail[cid] = 0
            else:
                # light pass: just re-toggle dropped AF (fast, works while farming)
                for cid in cid_list:
                    if rest_af(r, cid) is not True:
                        if time.time() - _last_af_attempt[cid] < (2 ** _af_fail[cid]) * 20:
                            continue  # in backoff — skip
                        _last_af_attempt[cid] = time.time()
                        ok, msg = await toggle_af(r, cid, CHARACTERS[cid], on=True)
                        if ok and 'OFF' in msg:
                            _af_fail[cid] += 1
                        else:
                            _af_fail[cid] = 0
                            changed.append(f'{CHARACTERS[cid]["name"]}:af:{msg}')
                        await asyncio.sleep(2)
                # Priority enforcement: if a HIGHER-priority char is AF-off while
                # a LOWER-priority one farms, swap them so the strongest pair
                # holds the slots. The server caps ~2 active; this guarantees
                # e.g. ShieldBot gets in ahead of BuffBot when a slot frees.
                for cid in cid_list:
                    if rest_af(r, cid) is True:
                        continue  # already farming — fine
                    # find the lowest-priority char currently farming to evict
                    farmers = [x for x in cid_list if rest_af(r, x) is True]
                    if not farmers:
                        break
                    # evict the farmer with the LOWEST priority rank
                    victim = max(farmers, key=lambda x: cid_list.index(x))
                    if cid_list.index(victim) < cid_list.index(cid):
                        continue  # victim is higher priority than the wait — no swap
                    ok, msg = await toggle_af(r, victim, CHARACTERS[victim], on=False)
                    changed.append(f'{CHARACTERS[victim]["name"]}:evict:{msg}')
                    await asyncio.sleep(3)
                    ok, msg = await toggle_af(r, cid, CHARACTERS[cid], on=True)
                    changed.append(f'{CHARACTERS[cid]["name"]}:swap-in:{msg}')
                    await asyncio.sleep(3)
                    break  # one swap per cycle is enough
            if changed:
                log('cycle ' + ' | '.join(changed))
            if time.time() - last_rate_log >= RATE_WINDOW_S:
                rates = report_rates(snap)
                log(f'rates {json.dumps(rates)}')
                try:
                    with open(STATE_FILE, 'w') as f:
                        json.dump({'ts': time.time(), 'chars': rates}, f, indent=1, default=str)
                except OSError:
                    pass
                last_rate_log = time.time()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f'cycle error: {e}')
            await asyncio.sleep(5)
    return 0


def shutdown(*_):
    global _running
    _running = False
    log('🛑 shutting down')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    try:
        code = asyncio.run(main())
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    sys.exit(code)
