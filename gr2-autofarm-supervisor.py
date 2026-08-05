#!/usr/bin/env python3
"""gr2-autofarm-supervisor.py — Persistent 3-char auto-farm supervisor.

ALL THREE characters farm simultaneously, and NO character is ever left dead
or called "disposable."

The server limits CONCURRENT WebSocket connections (~2 per account), NOT the
number of simultaneous auto-farmers. Auto-farm PERSISTS server-side after the
WS disconnects, so all 3 chars can auto-farm at the same time via sequential
brief-WS toggles. The only constraint: to issue a command (respawn/travel/
toggle) to a char, its WS must be able to connect — which requires a free
slot. So the golden rule:

    When a char needs a WS (respawn/travel), briefly PAUSE one other farmer
    to free a slot, do the work, then RESUME it. Never just abandon the char.

The WS toggle is a flip command, so we ALWAYS REST-sync the local flag before
toggling and POLL the server until the desired state is CONFIRMED — a stale
local flag otherwise causes a direction-inverted toggle (proven in tests).

Safe-zone shelter (2026-08-05): a char rotated out of a farm slot travels to
SAFE_ZONE (Gludios 149) BEFORE its AF is paused and is marked _sheltered, so
it rests at full HP instead of standing idle in the hunting zone (the old
behavior killed HermesHeal repeatedly). Rotation-idle chars are sheltered
immediately; startup recovers _sheltered from live state.

Runs as a systemd service (systemd/gr2-autofarm-supervisor.service,
Restart=always). Restart: su-run 'systemctl restart gr2-autofarm-supervisor.service'
Logs: journalctl -u gr2-autofarm-supervisor + ~/.hermes/gr2-autofarm-supervisor.log
Gold telemetry: ~/.hermes/grimeage_data.db gold_history (1 row/char/cycle).
Watchdog: gr2-watchdog.py (15-min cron, silent unless degraded).
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
SAFE_ZONE = 149          # Gludios city — safe resting spot for rotated-out chars
                         # (a char left standing in a hunting zone with AF off is
                         # monster bait — HermesHeal was killed this way 2026-08-05)
CYCLE_S = int(os.environ.get('GR2_CYCLE', '60'))        # main loop cadence
RATE_WINDOW_S = int(os.environ.get('GR2_RATE_WINDOW', '600'))  # gold-rate window

# Per-char hunting zone. The server caps 2 simultaneous farmers, so slots
# ROTATE (rotate_slots) — every char must be able to survive in its own zone.
# BuffBot is Lv21/967HP and gets overwhelmed in 64188 (Lv21-24); zone 53
# (Windmill Plains South, Lv20-22) is his survivable zone AND a Trial of
# Ascendancy quest zone (Bandit Scouts) — he survives + produces there (measured
# ~16-56k/hr, HP stable, no deaths). The Lv23 pair handle 64188.
# 2026-08-05: HermesHeal (bishop, Lv24) kept dying in 64188 (Lv24 Dire Wolves)
# despite heal-first rotation — moved her to zone 53 with BuffBot so the
# healer survives (user rule: nobody dies). ShieldBot (warlord, full Steel)
# holds 64188 alone.
CHAR_ZONE = {
    1069: 53,     # BuffBot    — Windmill Plains South (Lv20-22, safe + quest)
    1070: 53,     # HermesHeal — Windmill Plains South (Lv20-22, safe for caster)
    1071: 64188,  # ShieldBot  — Windy Meadow Gates (Lv21-24)
}

# All three are equal citizens. Order only affects WHO gets paused as the
# temporary slot-holder when a dead/out-of-zone char needs a WS. No char is
# ever "disposable" — the pause is always brief and always resumed.
ORDER = [1069, 1070, 1071]

# FAIR ROTATION — the server hard-caps 2 simultaneous farmers (a 3rd toggle is
# evicted; verified cleanly 2026-08-04). To keep every character "doing work"
# and leveling (BuffBot was stuck at Lv21 while the others hit 23), rotate the
# 2 active slots through all 3 chars: the idle char is swapped in on a timer,
# pausing whichever farmer has farmed the longest. Nobody is permanently
# sidelined; everyone contributes and levels.
ROTATE_S = int(os.environ.get('GR2_ROTATE', '300'))  # rotate every 5 min default
POOL_S = int(os.environ.get('GR2_POOL', '300'))     # gold-pool cycle cadence (5 min)
_last_rotation = 0.0
_farmer_started = {}   # cid -> timestamp when it started farming (for rotation fairness)

_gold_history = {}      # char_id -> deque[(t, gold)]
_running = True
# Consecutive WS/toggle failures per char -> exponential backoff. This is for
# TRANSIENT server errors, NOT for "the char is disposable."
_fail = {cid: 0 for cid in CHARACTERS}
_last_attempt = {cid: 0.0 for cid in CHARACTERS}
# Char currently resting in the SAFE_ZONE after being rotated OUT of a farm
# slot (2026-08-05 HermesHeal death fix). While sheltered, the ensure pass
# MUST NOT drag it back to its zone — it's safely idle by design. rotate_slots
# clears the flag when the char's turn comes up again.
_sheltered = {}  # cid -> sheltered_since (ts)


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


def rest_state(rest, cid):
    chars = rest.get('/api/characters')
    if isinstance(chars, list):
        for c in chars:
            if c.get('id') == cid:
                return {
                    'af': c.get('isAutoFarming'),
                    'hp': c.get('hp') or 0,
                    'zone': c.get('currentZoneId'),
                    'state': c.get('state'),
                }
    return None


def rest_af(rest, cid):
    st = rest_state(rest, cid)
    return st['af'] if st else None


def _detail(rest, cid):
    """Get a char's server state from the LIST endpoint — the ONLY endpoint
    whose isAutoFarming is authoritative. The DETAIL endpoint
    (/api/characters/{id}) does NOT include isAutoFarming (returns None),
    which caused direction-inverted toggles (verified 2026-08-04)."""
    st = rest_state(rest, cid)
    if st:
        return {'hp': st.get('hp'), 'maxHp': st.get('maxHp'),
                'zone': st.get('zone'), 'state': st.get('state'),
                'af': st.get('af')}
    # fallback to detail (missing af is acceptable — callers use list truth)
    d = rest.get(f'/api/characters/{cid}')
    if isinstance(d, dict):
        return {'hp': d.get('hp'), 'maxHp': d.get('maxHp'),
                'zone': d.get('currentZoneId'), 'state': d.get('state'),
                'af': None}
    return None


async def _agent_for(rest, cid, cfg):
    """Acquire a CharacterAgent whose local flags are REST-synced.
    Returns the connected agent (caller MUST disconnect) or None."""
    a = CharacterAgent(cid, cfg, rest, Analytics(init_db()))
    a._keep_running = True
    st = _detail(rest, cid) or {}
    a.hp = st.get('hp', a.hp)
    a.max_hp = st.get('maxHp', a.max_hp)
    a.is_dead = (st.get('hp') or 0) <= 0
    a.current_zone_id = st.get('zone')
    a.is_autofarming = bool(st.get('af'))  # CRITICAL: sync from LIST truth
    ok = await a.connect()
    if not ok:
        try:
            await a.disconnect()
        except Exception:
            pass
        return None
    return a


async def toggle_af(rest, cid, cfg, on=True, confirm_s=10):
    """REST-sync-aware AF toggle, POLLS until the server confirms the state.
    Returns (ok, msg)."""
    a = await _agent_for(rest, cid, cfg)
    if a is None:
        return False, 'connect-failed'
    try:
        for attempt in range(3):
            st = _detail(a.rest, cid) or {}
            a.is_autofarming = bool(st.get('af'))  # LIST truth, not detail None
            if a.is_autofarming == on:
                return True, f'already-{"ON" if on else "OFF"}'
            if on:
                await a.start_autofarm()
            else:
                await a.stop_autofarm()
            # Poll until confirmed (server lag ~1-3s on the flip)
            t0 = time.time()
            while time.time() - t0 < confirm_s:
                await asyncio.sleep(1)
                if rest_af(a.rest, cid) == on:
                    return True, f'toggled->{"ON" if on else "OFF"} (t={int(time.time()-t0)}s)'
            # Not confirmed — likely stale party/combat state rejecting the flip.
            # Leave the party (clears invisible server-side party state) and retry.
            await a.ws_send('party:leave', {})
            a.is_in_party = False
            a.party_members = {}
            await asyncio.sleep(2)
        after = rest_af(a.rest, cid)
        return False, f'still-{"ON" if after else "OFF"}'
    finally:
        await a.disconnect()


async def respawn_char(rest, cid, cfg, max_s=30):
    """Respawn a dead char. Assumes a WS slot is free (caller paused a farmer).
    Returns (ok, msg)."""
    st = rest_state(rest, cid)
    if not st:
        return False, 'char-not-found'
    if (st.get('hp') or 0) > 0:
        return True, 'already-alive'
    a = await _agent_for(rest, cid, cfg)
    if a is None:
        return False, 'connect-failed'
    try:
        if a.is_dead:
            await a.ws_send('respawn', {})
        t0 = time.time()
        while time.time() - t0 < max_s:
            await asyncio.sleep(1)
            c = rest_state(a.rest, cid)
            if c and (c.get('hp') or 0) > 0:
                return True, f"respawned hp={c['hp']} zone={c.get('zone')}"
            # if we got disconnected and reconnected, resend respawn
            if not a.connected and a.is_dead:
                try:
                    await a.connect()
                except Exception:
                    pass
        return False, 'respawn-timeout'
    finally:
        await a.disconnect()


async def travel_to_zone(rest, cid, cfg, target=PARTY_ZONE, max_s=25):
    """Travel a LIVE char to a zone. Assumes a WS slot is free.

    2026-08-05 fix: the server only accepts ADJACENT hops. Single-hop
    {'path':[target]} fails for non-adjacent zones (e.g. 64188->53 is
    64188->52817->53) — the char stayed put and kept dying in the lethal
    zone. Build a multi-hop path from the world map and travel hop-by-hop,
    waiting for each hop to land (coordinator pattern).
    Returns (ok, msg)."""
    st = rest_state(rest, cid)
    if not st:
        return False, 'char-not-found'
    if (st.get('hp') or 0) <= 0:
        return False, 'dead-first'
    if st.get('zone') == target:
        return True, f'already-in-{target}'
    a = await _agent_for(rest, cid, cfg)
    if a is None:
        return False, 'connect-failed'
    try:
        if a.current_zone_id == target:
            return True, f'already-in-{target}'
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
        # Build the hop list (adjacent-only). Fall back to direct if unknown.
        path = None
        try:
            if a.world is None:
                from grimeage_agent import WorldData
                a.world = WorldData(a.rest)
                a.world.load()
            if a.world and a.world._loaded and a.world.adjacency:
                path = a.world.find_path(a.current_zone_id, target)
        except Exception:
            path = None
        if not (path and len(path) >= 2):
            path = [a.current_zone_id, target]
        # Travel hop-by-hop; the server rejects non-adjacent single hops.
        a.combat_state = 'TRAVELING'
        for hop_idx in range(1, len(path)):
            hop = path[hop_idx]
            a.travel_complete.clear()
            await a.ws_send('start_travel', {'path': [hop]})
            t0 = time.time()
            while time.time() - t0 < max_s:
                await asyncio.sleep(0.5)
                c = rest_state(a.rest, cid)
                if c and c.get('zone') == hop:
                    break
            c = rest_state(a.rest, cid)
            if not c or c.get('zone') != hop:
                return False, f'travel-timeout-still-{c.get("zone") if c else "?"}'
        c = rest_state(a.rest, cid)
        if c and c.get('zone') == target:
            return True, f'arrived-{target}'
        return False, f'travel-failed-{c.get("zone") if c else "?"}'
    finally:
        await a.disconnect()


def _free_slot_candidate(rest, cid_list, except_cid):
    """Pick a farmer to briefly pause to free a WS slot for `except_cid`.
    Prefers a char that is actually farming. Returns cid or None."""
    farmers = [c for c in cid_list if c != except_cid and rest_af(rest, c) is True]
    if not farmers:
        return None
    # Prefer the lowest-priority (last in ORDER) farmer — but any works.
    return max(farmers, key=lambda x: cid_list.index(x))


async def ensure_char_working(rest, cid, cid_list, target_zone):
    """Ensure ONE char is alive, in its zone, and farming — pausing another
    farmer only as long as needed to free a WS slot. NEVER abandons the char.
    Returns list of log lines."""
    out = []
    cfg = CHARACTERS[cid]
    st = rest_state(rest, cid)
    if st is None:
        return [f'{cfg["name"]}:char-not-found']

    if (st.get('hp') or 0) <= 0:
        # Dead. Free a slot (pause any other farmer briefly), respawn + travel +
        # toggle-AF (ALL need a WS), then restore the paused farmer.
        was_sheltered = cid in _sheltered
        victim = _free_slot_candidate(rest, cid_list, cid)
        if victim is not None:
            ok, msg = await toggle_af(rest, victim, CHARACTERS[victim], on=False)
            out.append(f'{CHARACTERS[victim]["name"]}:pause:{msg}')
            await asyncio.sleep(2)
        ok, msg = await respawn_char(rest, cid, cfg)
        out.append(f'{cfg["name"]}:respawn:{msg}')
        await asyncio.sleep(2)
        if was_sheltered:
            # A sheltered char died in the safe city (rare — PvP etc). Restore
            # the shelter: travel back to SAFE_ZONE and stay AF-off. Do NOT
            # send it to the hunting zone (it's mid-rotation rest).
            ok, msg = await travel_to_zone(rest, cid, cfg, SAFE_ZONE)
            out.append(f'{cfg["name"]}:re-shelter:{msg}')
            await asyncio.sleep(2)
            if victim is not None and rest_af(rest, victim) is not True:
                ok, msg = await toggle_af(rest, victim, CHARACTERS[victim], on=True)
                out.append(f'{CHARACTERS[victim]["name"]}:resume:{msg}')
                await asyncio.sleep(2)
            return out
        # after respawn char is in a town — travel to its zone
        ok, msg = await travel_to_zone(rest, cid, cfg, target_zone)
        out.append(f'{cfg["name"]}:travel:{msg}')
        await asyncio.sleep(2)
        # toggle AF ON while the slot is STILL free (2nd farmer paused) — a
        # separate pass after resume would have no free slot to issue the toggle.
        if rest_af(rest, cid) is not True:
            ok, msg = await toggle_af(rest, cid, cfg, on=True)
            out.append(f'{cfg["name"]}:af:{msg}')
            await asyncio.sleep(2)
        # restore the paused farmer LAST — after all the target's WS needs are done
        if victim is not None and rest_af(rest, victim) is not True:
            ok, msg = await toggle_af(rest, victim, CHARACTERS[victim], on=True)
            out.append(f'{CHARACTERS[victim]["name"]}:resume:{msg}')
            await asyncio.sleep(2)
        return out

    # Alive but out of zone. Travel + toggle-AF under one paused slot, then restore.
    if st.get('zone') != target_zone:
        # SAFETY (2026-08-05): a char sheltered in the safe city after being
        # rotated OUT is idle BY DESIGN — do NOT drag it back to the hunting
        # zone. rotate_slots brings it back when its turn comes up.
        if cid in _sheltered:
            out.append(f'{cfg["name"]}:sheltered (safe zone, rotation governs)')
            return out
        victim = _free_slot_candidate(rest, cid_list, cid)
        if victim is not None:
            ok, msg = await toggle_af(rest, victim, CHARACTERS[victim], on=False)
            out.append(f'{CHARACTERS[victim]["name"]}:pause:{msg}')
            await asyncio.sleep(2)
        ok, msg = await travel_to_zone(rest, cid, cfg, target_zone)
        out.append(f'{cfg["name"]}:travel:{msg}')
        await asyncio.sleep(2)
        # toggle AF on while the slot is still free
        if rest_af(rest, cid) is not True:
            ok, msg = await toggle_af(rest, cid, cfg, on=True)
            out.append(f'{cfg["name"]}:af:{msg}')
            await asyncio.sleep(2)
        if victim is not None and rest_af(rest, victim) is not True:
            ok, msg = await toggle_af(rest, victim, CHARACTERS[victim], on=True)
            out.append(f'{CHARACTERS[victim]["name"]}:resume:{msg}')
            await asyncio.sleep(2)
        return out

    # Alive, in zone, but AF off — toggle ON only if a farm slot is free
    # (fewer than 2 other chars farming). If both slots are held, this char is
    # rotation-idle — leave it for rotate_slots to swap fairly rather than
    # hammering a toggle the server will reject (2-farmer cap).
    if rest_af(rest, cid) is not True:
        others_farming = sum(1 for x in cid_list if x != cid and rest_af(rest, x) is True)
        if others_farming >= 2:
            # Rotation-idle: both farm slots are held. SAFETY (2026-08-05): do
            # NOT leave this char standing in the hunting zone — it's monster
            # bait (HermesHeal death pattern). Shelter it in the safe city so
            # it rests safely while it waits for its rotation turn. rotate_slots
            # will travel it back + resume farming when the slot frees.
            if cid not in _sheltered and st.get('zone') != SAFE_ZONE:
                try:
                    ok_t, msg_t = await travel_to_zone(rest, cid, cfg, SAFE_ZONE)
                    if ok_t:
                        _sheltered[cid] = time.time()
                    out.append(f'{cfg["name"]}:af-wait-sheltered:{msg_t}')
                except Exception as e:
                    out.append(f'{cfg["name"]}:af-wait-shelter-fail:{e}')
            else:
                out.append(f'{cfg["name"]}:af-wait (2 slots held, rotation governs)')
            return out
        if time.time() - _last_attempt[cid] < (2 ** _fail[cid]) * 10:
            st2 = rest_state(rest, cid)
            out.append(f'{cfg["name"]}:af-backoff (hp={st2.get("hp") if st2 else "?"})')
            return out
        _last_attempt[cid] = time.time()
        ok, msg = await toggle_af(rest, cid, cfg, on=True)
        if ok and 'OFF' in msg:
            _fail[cid] += 1
        else:
            _fail[cid] = 0
            out.append(f'{cfg["name"]}:af:{msg}')
    return out


async def ensure_all_farming(rest, cid_list):
    """Ensure EVERY char is alive, in its zone, and farming. No char is ever
    deferred or abandoned. Order chosen to minimise slot contention (fix the
    char that most needs a WS first, then toggle the rest on)."""
    logmsg = []
    # Pass 1: fix each char that needs a WS (dead or out-of-zone) — one at a time
    # so slot contention between their needs is serialised.
    for cid in cid_list:
        st = rest_state(rest, cid)
        if st is None:
            continue
        target = CHAR_ZONE.get(cid, PARTY_ZONE)
        needs_ws = (st.get('hp') or 0) <= 0 or st.get('zone') != target
        if needs_ws:
            lines = await ensure_char_working(rest, cid, cid_list, target)
            logmsg.extend(lines)
            await asyncio.sleep(2)
    # Pass 2: toggle AF ON for any alive/in-zone char that's off.
    for cid in cid_list:
        st = rest_state(rest, cid)
        if st is None:
            continue
        target = CHAR_ZONE.get(cid, PARTY_ZONE)
        if (st.get('hp') or 0) > 0 and st.get('zone') == target and rest_af(rest, cid) is not True:
            lines = await ensure_char_working(rest, cid, cid_list, target)
            logmsg.extend(lines)
            await asyncio.sleep(2)
    return logmsg


def record_gold(snap):
    now = time.time()
    for cid, info in snap.items():
        _gold_history.setdefault(cid, deque(maxlen=400)).append((now, info.get('gold') or 0))
    # Durable telemetry: persist to the shared DB (gold_history table) so
    # gold rates survive restarts and the dashboard/analytics can chart them.
    # Throttled to ~once/5min by the caller's cadence (record_gold is called
    # each cycle); each write is one row per char.
    try:
        db = _gold_db()
        rows = [(int(cid), now, int(info.get('gold') or 0)) for cid, info in snap.items()]
        db.executemany('INSERT INTO gold_history (char_id, timestamp, gold) VALUES (?,?,?)', rows)
        db.commit()
    except Exception:
        pass  # telemetry is best-effort; never break the farm loop


_gold_db_conn = None


def _gold_db():
    """Lazy single sqlite connection for gold telemetry (reopened if dropped)."""
    global _gold_db_conn
    try:
        if _gold_db_conn is None:
            import sqlite3
            from ga_config import DB_PATH
            _gold_db_conn = sqlite3.connect(DB_PATH, timeout=5)
            _gold_db_conn.execute(
                'CREATE TABLE IF NOT EXISTS gold_history ('
                'id INTEGER PRIMARY KEY AUTOINCREMENT, char_id INTEGER NOT NULL, '
                'timestamp REAL NOT NULL, gold INTEGER NOT NULL)')
        return _gold_db_conn
    except Exception:
        _gold_db_conn = None
        raise


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


async def rotate_slots(rest, cid_list, target_zone=PARTY_ZONE):
    """Fair-rotation: if a char is alive+in-zone but AF-off (sidelined by the
    2-farmer cap), swap it into a slot by pausing the farmer that has been
    farming the longest. Returns log lines.

    SAFETY (2026-08-05): a farmer paused while standing in the hunting zone is
    monster bait — HermesHeal was repeatedly killed this way (rot-pause at
    14:56 → dead by 15:00, standing idle in zone 53). Before pausing the
    victim we FIRST travel it back to the safe city (Gludios 149) so it rests
    safely while sidelined, and mark it _sheltered so the ensure pass doesn't
    drag it back. The incoming char then takes the freed slot (its _sheltered
    flag is cleared). Travel of the victim happens WHILE it still farms (no
    slot needed for the victim's own WS); the slot is only freed by the pause
    AFTER arrival.
    """
    out = []
    # Idle = alive, AF-off, and either in its hunting zone OR sheltered in the
    # safe city (resting from a prior rotation — still eligible for its turn).
    idle = [c for c in cid_list
            if (rest_state(rest, c) or {}).get('hp', 0) > 0
            and (rest_state(rest, c) or {}).get('zone') in (CHAR_ZONE.get(c, target_zone), SAFE_ZONE)
            and rest_af(rest, c) is not True]
    if not idle:
        return out  # everyone farming (or dead/out-of-zone handled elsewhere)
    farmers = [c for c in cid_list if rest_af(rest, c) is True]
    if not farmers:
        return out  # no farmer to swap with; enable_* passes handle this
    # Swap the highest-priority idle char into a slot, pausing the farmer
    # who has farmed the longest (fair — no one hoards a slot forever).
    cid = idle[0]  # ORDER-ordered = lowest id first = BuffBot gets in first
    victim = max(farmers, key=lambda x: _farmer_started.get(x, 0) or 0)
    # SAFETY: move the victim to the safe city BEFORE pausing so it never
    # stands idle in the hunting zone (HermesHeal death pattern 2026-08-05).
    v_cfg = CHARACTERS[victim]
    v_st = rest_state(rest, victim) or {}
    if v_st.get('zone') != SAFE_ZONE:
        # Travel while still farming — the victim's own WS is fine; only the
        # 2-farmer cap matters and it's not being evicted (it's a farmer).
        try:
            ok_t, msg_t = await travel_to_zone(rest, victim, v_cfg, SAFE_ZONE)
            out.append(f'{v_cfg["name"]}:rot-shelter:{msg_t}')
            await asyncio.sleep(2)
        except Exception as e:
            out.append(f'{v_cfg["name"]}:rot-shelter-fail:{e}')
    ok, msg = await toggle_af(rest, victim, v_cfg, on=False)
    out.append(f'{v_cfg["name"]}:rot-pause:{msg}')
    _sheltered[victim] = time.time()  # ensure pass must not drag it back
    await asyncio.sleep(3)
    _sheltered.pop(cid, None)  # the incoming char is back in the rotation
    # If the incoming char is resting in the safe city, travel it to its zone
    # FIRST (AF-on in the city farms nothing / is wrong).
    c_st = rest_state(rest, cid) or {}
    if c_st.get('zone') == SAFE_ZONE:
        try:
            ok_t, msg_t = await travel_to_zone(rest, cid, CHARACTERS[cid],
                                               CHAR_ZONE.get(cid, target_zone))
            out.append(f'{CHARACTERS[cid]["name"]}:rot-travel:{msg_t}')
            await asyncio.sleep(2)
        except Exception as e:
            out.append(f'{CHARACTERS[cid]["name"]}:rot-travel-fail:{e}')
    ok, msg = await toggle_af(rest, cid, CHARACTERS[cid], on=True)
    out.append(f'{CHARACTERS[cid]["name"]}:rot-in:{msg}')
    await asyncio.sleep(3)
    # The rotated-out char is now in the safe city — the ensure pass will
    # travel it back when its slot comes around again.
    _farmer_started[victim] = 0
    _farmer_started[cid] = time.time()
    return out


async def pool_gold_cycle(rest, cid_list, npc_id=1051, keep=80000, fill_to=150000):
    """Redistribute gold through the ACCOUNT-SHARED warehouse (NPC 1051).

    Runs EVERY supervisor cycle (not just on connect) so the permanent
    farmers (e.g. BuffBot, who never gets toggled by rotation) also get
    pooled. Rules:
    - gold > keep   -> deposit surplus (keep = farming liquidity floor).
    - gold < keep   -> withdraw up to fill_to if the pool has >= 10k
      (broke chars get funded for training/crafting).
    Never drops a char below keep; never overdraws the pool.
    Returns list of log lines.
    """
    out = []
    try:
        pool = (rest.get(f'/api/warehouse/{npc_id}/gold') or {}).get('gold') or 0
        for cid in cid_list:
            d = rest.get(f'/api/characters/{cid}')
            if not isinstance(d, dict):
                continue
            gold = d.get('gold') or 0
            name = CHARACTERS[cid]['name']
            if gold > keep:
                excess = gold - keep
                res = rest.post(f'/api/warehouse/{npc_id}/deposit-gold', {
                    'characterId': cid, 'amount': excess})
                if isinstance(res, dict) and res.get('status') == 'ok':
                    pool += excess
                    out.append(f'{name}:pool-deposit:{excess}')
            elif gold < keep and pool >= 10000:
                want = min(fill_to - gold, pool)
                if want > 0:
                    res = rest.post(f'/api/warehouse/{npc_id}/withdraw-gold', {
                        'characterId': cid, 'amount': want})
                    if isinstance(res, dict) and res.get('status') == 'ok':
                        pool -= want
                        out.append(f'{name}:pool-withdraw:{want}')
        return out
    except Exception as e:
        log(f'pool cycle error: {e}')
        return out


async def main():
    global _last_rotation
    r = RestClient(ACCOUNT_EMAIL, ACCOUNT_PASSWORD)
    r.login()
    if not getattr(r, 'token', None):
        log('LOGIN FAILED — exiting')
        return 1

    snap = snapshot(r)
    log(f'start {json.dumps(snap)}')
    record_gold(snap)

    cid_list = list(ORDER)
    # RECOVER SHELTER STATE after a restart (2026-08-05): _sheltered is
    # in-memory, so a crash/restart loses it. Any char resting AF-off in the
    # safe city from a prior rotation would otherwise get dragged back to its
    # hunting zone by ensure_char_working. Re-mark them sheltered on boot.
    for cid in cid_list:
        st = rest_state(r, cid)
        if st and (st.get('hp') or 0) > 0 and st.get('zone') == SAFE_ZONE and rest_af(r, cid) is not True:
            _sheltered[cid] = time.time()
            log(f'start: recovered shelter for {CHARACTERS[cid]["name"]} (in {SAFE_ZONE})')
    logmsg = await ensure_all_farming(r, cid_list)
    for m in logmsg:
        log(m)

    # No long verify loop — a capped 3rd char (2-farmer server limit) can't be
    # forced into a slot, retrying it just wastes connect time and toggles the
    # ACTIVE farmers off. The main loop's ensure + fair-rotation handles the
    # 3rd slot promptly. Just report the sweep result and move on.
    log(f'AF sweep complete: {json.dumps({CHARACTERS[c]["name"]: rest_af(r, c) for c in cid_list})}')

    # Persistent loop — keep ALL chars alive + farming. Never defer anyone.
    last_rate_log = time.time()
    last_pool = 0.0
    while _running:
        try:
            await asyncio.sleep(CYCLE_S)
            try:
                with open(PID_FILE, 'w') as f:
                    f.write(str(os.getpid()))
            except OSError:
                pass
            snap = snapshot(r)
            record_gold(snap)
            changed = []
            # Refresh every char toward alive+in-zone+farming.
            for cid in cid_list:
                st = rest_state(r, cid)
                if st is None:
                    continue
                target = CHAR_ZONE.get(cid, PARTY_ZONE)
                if (st.get('hp') or 0) <= 0 or st.get('zone') != target or rest_af(r, cid) is not True:
                    lines = await ensure_char_working(r, cid, cid_list, target)
                    changed.extend(lines)
                # reset backoff on healthy chars
                if (st.get('hp') or 0) > 0 and rest_af(r, cid) is True:
                    _fail[cid] = 0
                    _farmer_started.setdefault(cid, time.time())
                await asyncio.sleep(1)
            # GOLD POOLING (2026-08-05): balance all chars through the shared
            # warehouse every cycle. Runs at supervisor level so even the
            # permanent farmer (BuffBot, never toggled by rotation) gets pooled.
            if time.time() - last_pool >= POOL_S:
                pool_lines = await pool_gold_cycle(r, cid_list)
                changed.extend(pool_lines)
                last_pool = time.time()
            # FAIR ROTATION: periodically swap an idle-but-healthy char into a
            # farm slot so no one is permanently sidelined by the 2-farmer cap.
            if time.time() - _last_rotation >= ROTATE_S:
                lines = await rotate_slots(r, cid_list)
                changed.extend(lines)
                _last_rotation = time.time()
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