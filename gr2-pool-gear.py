#!/usr/bin/env python3
"""One-time gold-pool + gear-up pass for GA2-B (2026-08-05, remote-only).

Goal: get BuffBot (sorcerer, Lv21) funded + a proper staff so he stops dying.
All operations (warehouse deposit/withdraw, shop buy, inventory equip) work
REMOTELY from hunting zones — no city travel, no 2-WS slot contention, no
travel-timeout abort paths (the June-era city-travel dance caused the exit-1
failures). Flow:
  1. ShieldBot (richest) deposits most of his gold to the ACCOUNT-SHARED
     warehouse (NPC 1051 — NOT characterId).
  2. BuffBot withdraws, buys Arcane Staff (itemId 87) + Steel armor set,
     equips everything.
Run with supervisor STOPPED (no slot contention)."""
import sys, json, time, asyncio, os
sys.path.insert(0, '/home/hindsight/GA2-B')
sys.path.insert(0, '/home/hindsight/.hermes/scripts')

from ga_rest import RestClient
from ga_config import ACCOUNT_EMAIL, ACCOUNT_PASSWORD
from grimeage_agent import CHARACTERS

ZONES = {1069: 53, 1070: 64188, 1071: 64188}

def log(m):
    print(f'[{time.strftime("%H:%M:%S")}] {m}', flush=True)

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

    # REMOTE-ONLY flow (verified 2026-08-05): the warehouse is ACCOUNT-SHARED
    # and deposit/withdraw/buy ALL work from hunting zones — no city travel,
    # no 2-WS slot contention, no travel-timeout abort paths. The June-era
    # city-travel dance was the source of the exit-1 failures (travel aborts).

    # 1. ShieldBot (richest) deposits most of his gold to the shared pool.
    c = r.get('/api/characters/1071')
    sb_gold = c.get('gold') or 0
    deposit = max(0, sb_gold - 15000)  # keep 15k for himself
    res = r.post('/api/warehouse/1051/deposit-gold', {'characterId': 1071, 'amount': deposit})
    log(f'ShieldBot deposit {deposit}: {res}')
    time.sleep(1)

    # 2. BuffBot withdraws from the pool.
    wg = r.get('/api/warehouse/1051/gold')
    log(f'Warehouse balance: {wg}')
    need = 360000
    res = r.post('/api/warehouse/1051/withdraw-gold', {'characterId': 1069, 'amount': need})
    log(f'BuffBot withdraw {need}: {res}')
    time.sleep(1)
    c = r.get('/api/characters/1069')
    log(f'BuffBot gold after withdraw: {c.get("gold")}')

    # 3. Buy Arcane Staff (itemId 87) — m_atk 55 (remote buy, works from zone)
    res = r.post('/api/shop/8/buy', {'characterId': 1069, 'itemId': 87, 'quantity': 1})
    log(f'Buy Arcane Staff: {res}')
    time.sleep(1)
    # Buy Steel armor pieces: Plate 96, Greaves 98, Helm 95, Gauntlets 97, Boots 99
    for item_id, nm in [(96, 'Steel Plate'), (98, 'Steel Greaves'), (95, 'Steel Helm'),
                        (97, 'Steel Gauntlets'), (99, 'Steel Boots')]:
        res = r.post('/api/shop/8/buy', {'characterId': 1069, 'itemId': item_id, 'quantity': 1})
        log(f'Buy {nm}: {res}')
        time.sleep(0.5)

    # 4. Equip the staff + best armor via inventory equip
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

    # 5. Re-verify equipped main hand is the staff (m_atk class check)
    inv = r.get('/api/inventory/1069')
    for e in (inv.get('equipped') or []):
        if e.get('itemType') == 'weapon':
            log(f'BuffBot main weapon: {e.get("itemName")} {e.get("statsJson")}')

    # Final state
    for cid in ZONES:
        c = r.get(f'/api/characters/{cid}')
        log(f'{CHARACTERS[cid]["name"]}: gold={c.get("gold")} hp={c.get("hp")} zone={c.get("currentZoneId")}')
    return 0

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
