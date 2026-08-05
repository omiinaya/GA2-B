#!/usr/bin/env python3
"""Grimeage2 auto-farm watchdog. Checks all 3 bots are farming.
Silent if all good, alerts if any are idle/dead/wandering.

Uses ga_config (no hardcoded creds) and per-char safe zones from
gr2-autofarm-supervisor's CHAR_ZONE mapping. Supervises the
gr2-autofarm-supervisor.service too: if systemd shows it dead, that's an
alert (the service has Restart=always, so this only fires if systemd itself
gave up or the unit was stopped).
"""
import json, sys, subprocess, os

sys.path.insert(0, '/home/hindsight/GA2-B')
sys.path.insert(0, '/home/hindsight/.hermes/scripts')

from ga_rest import RestClient
from ga_config import ACCOUNT_EMAIL, ACCOUNT_PASSWORD

# Per-char safe zones (mirror of gr2-autofarm-supervisor CHAR_ZONE):
# BuffBot (Lv21 sorcerer) -> zone 53 (Windmill Plains South, Lv20-22)
# HermesHeal (bishop) -> zone 53 (safe relocation 2026-08-05)
# ShieldBot (warlord) -> zone 64188 (Windy Meadow Gates, Lv21-24)
CHAR_ZONE = {1069: 53, 1070: 53, 1071: 64188}


def main():
    issues = []
    # 1. Supervisor service health
    try:
        out = subprocess.run(['systemctl', 'is-active', 'gr2-autofarm-supervisor.service'],
                             capture_output=True, text=True, timeout=15)
        if out.stdout.strip() != 'active':
            issues.append(f'⚠️ gr2-autofarm-supervisor.service is {out.stdout.strip() or "unknown"}!')
    except Exception as e:
        issues.append(f'⚠️ could not check supervisor service: {e}')

    # 2. Character state
    r = RestClient(ACCOUNT_EMAIL, ACCOUNT_PASSWORD)
    r.login()
    if not getattr(r, 'token', None):
        print(f'[FAIL] Login failed')
        sys.exit(1)
    chars = r.get('/api/characters')
    if not isinstance(chars, list):
        print(f'[FAIL] Characters fetch failed: {chars}')
        sys.exit(1)
    per_char = []
    farming_count = 0
    for c in chars:
        cid = c.get('id')
        name = c.get('name')
        lv = c.get('level')
        zone = c.get('currentZoneId')
        state = c.get('state')
        farming = c.get('isAutoFarming')
        hp = c.get('hp') or 0
        max_hp = c.get('maxHp') or 1
        target = CHAR_ZONE.get(cid)
        if farming:
            farming_count += 1
        per_char.append({'id': cid, 'name': name, 'lv': lv, 'zone': zone,
                         'target': target, 'state': state, 'farming': farming,
                         'hp': hp, 'max_hp': max_hp})

    # The server caps 2 simultaneous farm sessions; the 3rd char is rotated
    # out to af=false (idle) by fair-rotation by design. So ONE idle char is
    # NORMAL. Only flag when the system genuinely degrades:
    #   - a char is dead / in the wrong zone (never acceptable)
    #   - MORE than one char is not-farming (>1 idle means production loss)
    #   - the farm service is down
    for c in per_char:
        name, lv, zone, target, state = c['name'], c['lv'], c['zone'], c['target'], c['state']
        hp, max_hp = c['hp'], c['max_hp']
        if zone != target:
            issues.append(f'{name} (Lv{lv}): WRONG ZONE {zone} (should be {target}) | State:{state}')
        elif state == 'dead' or hp <= 0:
            issues.append(f'{name} (Lv{lv}): DEAD at zone {zone}!')
        elif hp < max_hp * 0.3:
            issues.append(f'{name} (Lv{lv}): LOW HP {hp}/{max_hp} at zone {zone}')
    idle = [c['name'] for c in per_char if not c['farming'] and c['state'] != 'traveling']
    if len(idle) > 1:
        issues.append(f'{len(idle)} chars NOT FARMING (should be ≤1 rotated out): {" ".join(idle)}')

    if issues:
        print('⚠️  Grimeage2 Watchdog Alert:')
        for issue in issues:
            print(f'  • {issue}')
    # else: silent — all good


if __name__ == '__main__':
    main()
