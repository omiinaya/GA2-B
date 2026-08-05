#!/usr/bin/env python3
"""One-time gold-pool + gear-up pass for GA2-B (2026-08-05).

Goal: get BuffBot (sorcerer, Lv21) a proper staff + Steel armor so he stops
dying / starts dealing real damage. Warehouse gold transfer requires CITY
proximity (zone 149 Gludios), so we:
  1. Travel ShieldBot (richest, 234k) to Gludios 149, deposit gold.
  2. Travel BuffBot to Gludios, withdraw, buy Arcane Staff + Steel armor,
     equip everything.
  3. Return both to their farming zones.
Run with supervisor STOPPED (no slot contention)."""
import sys, json, time, asyncio, os
sys.path.insert(0, '/home/hindsight/GA2-B')
sys.path.insert(0, '/home/hindsight/.hermes/scripts')

from ga_rest import RestClient
from ga_config import ACCOUNT_EMAIL, ACCOUNT_PASSWORD
from grimeage_agent import CharacterAgent, Analytics, init_db, CHARACTERS

GLUDIOS = 149
ZONES = {1069: 53, 1070: 64188, 1071: 64188}

def log(m):
    print(f'[{time.strftime("%H:%M:%S")}] {m}', flush=True)

async def toggle_af(rest, cid, on, timeout=20):
    """Toggle auto-farm via the supervisor's proven pattern (brief WS + REST poll)."""
    a = CharacterAgent(cid, CHARACTERS[cid], rest, Analytics(init_db()))
    a._keep_running = True
    try:
        st = rest.get(f'/api/characters/{cid}') or {}
        a.is_autofarming = bool(st.get('isAutoFarming'))
        ok = await a.connect()
        if not ok:
            return False, 'connect-failed'
        if a.is_autofarming == on:
            return True, f'already-{"ON" if on else "OFF"}'
        if on:
            await a.start_autofarm()
        else:
            await a.stop_autofarm()
        t0 = time.time()
        while time.time() - t0 < timeout:
            await asyncio.sleep(1)
            st = rest.get(f'/api/characters/{cid}') or {}
            if bool(st.get('isAutoFarming')) == on:
                return True, f'toggled->{"ON" if on else "OFF"} (t={int(time.time()-t0)}s)'
        return False, f'still-{"ON" if on else "OFF"}'
    finally:
        try:
            await a.disconnect()
        except Exception:
            pass


async def travel(rest, cid, target, timeout=60):
    """Robust travel using the agent's travel_complete event (coordinator pattern).

    The server hard-caps 2 simultaneous WS/farm sessions. If the target char's
    WS drops immediately, a slot is held by another farmer — the caller must
    have paused one first (toggle_af off) to free the slot."""
    a = CharacterAgent(cid, CHARACTERS[cid], rest, Analytics(init_db()))
    a._keep_running = True
    try:
        ok = await a.connect()
        if not ok:
            return False, 'connect-failed'
        # CRITICAL: the server closes idle WS connections within ~2s. Send
        # travel IMMEDIATELY — do NOT sleep first. (2026-08-05: adding a 1.5s
        # settle sleep let the server close the WS → ws-evicted.)
        # Force-exit combat so travel is accepted (pitfall #45) — but only if
        # state says we're in combat; these sends are fast and safe.
        try:
            if getattr(a, 'is_in_combat', False) or getattr(a, '_target_attack_initiated', False):
                await a.ws_send('combat:stop_attack', {})
                a._target_attack_initiated = False
                a.is_in_combat = False
            await a.ws_send('combat:rest', {})
            await asyncio.sleep(0.2)
            await a.ws_send('combat:cancel_rest', {})
            await asyncio.sleep(0.2)
        except Exception:
            pass
        if a.current_zone_id == target:
            return True, f'already-in-{target}'
        a.combat_state = 'TRAVELING'
        a.travel_complete.clear()
        await a.ws_send('start_travel', {'path': [target]})
        try:
            await asyncio.wait_for(a.travel_complete.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        # Confirm via REST
        c = rest.get(f'/api/characters/{cid}')
        if c and c.get('currentZoneId') == target:
            return True, f'arrived-{target}'
        # Fallback: keep sending until REST confirms (re-hops)
        t0 = time.time()
        while time.time() - t0 < 30:
            c = rest.get(f'/api/characters/{cid}')
            if c and c.get('currentZoneId') == target:
                return True, f'arrived-{target}-retry'
            try:
                a.travel_complete.clear()
                await a.ws_send('start_travel', {'path': [target]})
            except Exception:
                pass
            await asyncio.sleep(3)
        c = rest.get(f'/api/characters/{cid}')
        return False, f'travel-timeout (zone={c.get("currentZoneId") if c else "?"})'
    finally:
        try:
            await a.disconnect()
        except Exception:
            pass

async def main():
    r = RestClient(ACCOUNT_EMAIL, ACCOUNT_PASSWORD)
    r.login()
    if not getattr(r, 'token', None):
        log('LOGIN FAILED')
        return 1

    # Snapshot starting gold
    for cid in ZONES:
        c = r.get(f'/api/characters/{cid}')
        log(f'{CHARACTERS[cid]["name"]}: gold={c.get("gold")} hp={c.get("hp")} zone={c.get("currentZoneId")}')

    # 0. Free a farm slot: pause HermesHeal (idle-safe; BuffBot is the one we
    #    need to keep alive, and ShieldBot is traveling). The server caps 2
    #    simultaneous WS/farm sessions, and ShieldBot's WS is evicted while
    #    both farmers hold slots.
    log('--- free a slot: pause HermesHeal ---')
    ok, msg = await toggle_af(r, 1070, False)
    log(f'HermesHeal pause: {msg}')
    await asyncio.sleep(3)

    # 1. ShieldBot -> Gludios, deposit
    log('--- ShieldBot to Gludios ---')
    ok, msg = await travel(r, 1071, GLUDIOS)
    log(f'ShieldBot travel: {msg}')
    if not ok:
        log('ABORT: ShieldBot could not reach city')
        return 1
    c = r.get('/api/characters/1071')
    sb_gold = c.get('gold') or 0
    deposit = max(0, sb_gold - 15000)  # keep 15k for himself
    res = r.post('/api/warehouse/1071/deposit-gold', {'characterId': 1071, 'amount': deposit})
    log(f'ShieldBot deposit {deposit}: {res}')
    time.sleep(1)

    # 2. BuffBot -> Gludios, withdraw, buy staff + steel armor
    log('--- BuffBot to Gludios ---')
    ok, msg = await travel(r, 1069, GLUDIOS)
    log(f'BuffBot travel: {msg}')
    if not ok:
        log('ABORT: BuffBot could not reach city')
        return 1
    wg = r.get('/api/warehouse/1069/gold')
    log(f'BuffBot warehouse view: {wg}')
    # withdraw enough for Arcane Staff (259,896) + steel armor (~100k)
    need = 360000
    res = r.post('/api/warehouse/1069/withdraw-gold', {'characterId': 1069, 'amount': need})
    log(f'BuffBot withdraw {need}: {res}')
    time.sleep(1)
    c = r.get('/api/characters/1069')
    log(f'BuffBot gold after withdraw: {c.get("gold")}')

    # Buy Arcane Staff (itemId 87) — m_atk 55
    res = r.post('/api/shop/8/buy', {'characterId': 1069, 'itemId': 87, 'quantity': 1})
    log(f'Buy Arcane Staff: {res}')
    time.sleep(1)
    # Buy Steel armor pieces: Plate 96, Greaves 98, Helm 95, Gauntlets 97, Boots 99
    for item_id, nm in [(96, 'Steel Plate'), (98, 'Steel Greaves'), (95, 'Steel Helm'),
                        (97, 'Steel Gauntlets'), (99, 'Steel Boots')]:
        res = r.post('/api/shop/8/buy', {'characterId': 1069, 'itemId': item_id, 'quantity': 1})
        log(f'Buy {nm}: {res}')
        time.sleep(0.5)

    # Equip the staff + best armor via inventory equip
    inv = r.get('/api/inventory/1069')
    bag = inv.get('bag') or []
    equip_map = {}
    for b in bag:
        nm = b.get('itemName')
        if nm == 'Arcane Staff':
            equip_map['main_hand'] = b.get('id')
        elif nm == 'Steel Plate':
            equip_map['body'] = b.get('id')
        elif nm == 'Steel Greaves':
            equip_map['legs'] = b.get('id')
        elif nm == 'Steel Helm':
            equip_map['head'] = b.get('id')
        elif nm == 'Steel Gauntlets':
            equip_map['gloves'] = b.get('id')
        elif nm == 'Steel Boots':
            equip_map['boots'] = b.get('id')
    for slot, inv_id in equip_map.items():
        res = r.post(f'/api/inventory/1069/equip', {'inventoryId': inv_id})
        log(f'Equip {slot}: {res}')
        time.sleep(0.5)
    c = r.get('/api/characters/1069')
    log(f'BuffBot after gear: gold={c.get("gold")} hp={c.get("hp")}/{c.get("maxHp")}')

    # 3. Return both to farming zones
    log('--- return to zones ---')
    ok, msg = await travel(r, 1069, ZONES[1069])
    log(f'BuffBot return: {msg}')
    ok, msg = await travel(r, 1071, ZONES[1071])
    log(f'ShieldBot return: {msg}')

    # 4. Resume HermesHeal farming (slot is free again after both returned)
    log('--- resume HermesHeal ---')
    ok, msg = await toggle_af(r, 1070, True)
    log(f'HermesHeal resume: {msg}')

    # Final state
    for cid in ZONES:
        c = r.get(f'/api/characters/{cid}')
        log(f'{CHARACTERS[cid]["name"]}: gold={c.get("gold")} hp={c.get("hp")} zone={c.get("currentZoneId")}')
    return 0

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
