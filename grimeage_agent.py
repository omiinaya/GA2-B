# Source Generated with Decompyle++
# File: grimeage_agent.cpython-311.pyc (Python 3.11)

'''
GrimeAge2 Multi-Character Agent — plays, coordinates, progresses.
Connects all chars, forms party, farms optimal zones, upgrades gear,
manages health, tracks analytics, and reports.

Tier 1: Bidirectional WS control → Zone progression → Party → Health
Tier 2: Gear planner → Persistent analytics → Inventory
Tier 3: Error recovery → Quests → Discord → Trade
'''
import asyncio
import json
import urllib.request as urllib
import ssl
import sys
import os
import time
import sqlite3
from datetime import datetime, timezone
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Optional
from urllib.error import HTTPError
import websockets
ACCOUNT_EMAIL = 'hermes.bot.gr2@gmail.com'
ACCOUNT_PASSWORD = 'GrimeageBot2026!'
BASE = 'https://grimeage2.com'
WS_BASE = 'wss://grimeage2.com'
DB_PATH = '/home/hindsight/grimeage_data.db'
CHARACTERS = {
    1069: {
        'name': 'BuffBot',
        'class': 'wizard',
        'role': 'dps' },
    1070: {
        'name': 'HermesHeal',
        'class': 'wizard',
        'role': 'healer' },
    1071: {
        'name': 'ShieldBot',
        'class': 'fighter',
        'role': 'tank' } }
HP_SAFE_PCT = 0.4
HP_REST_PCT = 0.8
MP_LOW_PCT = 0.2
POTION_HP_PCT = 0.35
POTION_MP_PCT = 0.15
AUTOFARM_HP_MIN = 0.5
AUTOFARM_MP_MIN = 0.3
GEAR_SLOTS = {
    'belt',
    'body',
    'head',
    'legs',
    'boots',
    'ring1',
    'ring2',
    'amulet',
    'gloves',
    'earring1',
    'earring2',
    'necklace',
    'off_hand',
    'main_hand'}
JUNK_TYPES = {
    'key'}
# Crafting materials (type='material') are NEVER junk — they feed the crafting
# economy (Mithril Alloy, Magical Dust/Shard, Magic/Enchanted/Dark Crystal,
# Stone of Purity, Leather, Reinforced Bone...). The old blanket `material`
# rule + over-broad keywords would sell the exact materials every weapon
# recipe needs (2026-08-04 dagger-craft discovery). Only unambiguous
# vendor-fodder keywords remain.
VENDOR_TRASH_KEYWORDS = {
    'old coin',
    'rusty',
    'broken',
    'torn',
    'worn'}

# Weapon stats by name: (p_atk, m_atk, levelRequired) — from the game's item
# catalog (2026-08-04). Used by _auto_equip_best_weapon to never leave an
# upgrade in the bag (equipping ShieldBot's bagged Mithril Warhammer 5.3x'd the
# manual farm rate: 2,440 -> 12,976 g/hr).
WEAPON_CATALOG = {
    'Abyssal Blade': (184, 106, 40),
    'Abyssal Crusher': (210, 122, 40),
    'Abyssal Greatsword': (267, 128, 40),
    'Abyssal Kris': (138, 91, 40),
    'Abyssal Staff': (167, 210, 40),
    'Abyssal War Fists': (191, 81, 40),
    'Abyssal Warbow': (323, 83, 40),
    'Aether Blade': (209, 121, 52),
    'Aether Crusher': (239, 139, 52),
    'Aether Greatsword': (304, 146, 52),
    'Aether Kris': (157, 103, 52),
    'Aether Staff': (190, 239, 52),
    'Aether War Fists': (217, 92, 52),
    'Aether Warbow': (367, 94, 52),
    'Apprentice Greatsword': (18, 9, 0),
    'Arcane Staff': (44, 55, 0),
    "Archmage's Staff": (88, 110, 20),
    "Assassin's Dagger": (36, 24, 0),
    'Broad Sword': (28, 16, 0),
    "Champion's Greatsword": (70, 34, 0),
    "Crab King's Claw": (62, 36, 0),
    'Crystal-Woven Staff': (64, 80, 0),
    'Dual Abyssal Swords': (241, 115, 40),
    'Dual Aether Swords': (274, 131, 52),
    'Dual Eldritch Swords': (164, 78, 40),
    'Dual Empyrean Swords': (303, 145, 52),
    'Dual Mithril Swords': (95, 45, 0),
    'Dual Runic Swords': (126, 60, 20),
    'Eldritch Blade': (125, 72, 40),
    'Eldritch Crusher': (143, 83, 40),
    'Eldritch Greatsword': (182, 87, 40),
    'Eldritch Kris': (94, 62, 40),
    'Eldritch Staff': (114, 143, 40),
    'Eldritch War Fists': (130, 55, 40),
    'Eldritch Warbow': (220, 47, 40),
    'Empyrean Blade': (231, 134, 52),
    'Empyrean Crusher': (264, 154, 52),
    'Empyrean Greatsword': (336, 161, 52),
    'Empyrean Kris': (174, 114, 52),
    'Empyrean Staff': (210, 264, 52),
    'Empyrean War Fists': (240, 102, 52),
    'Empyrean Warbow': (406, 104, 52),
    'Iron Greatsword': (42, 20, 0),
    'Iron Knuckles': (10, 5, 0),
    'Iron Mace': (32, 19, 0),
    "Knight's Sword": (48, 28, 0),
    'Longbow': (38, 11, 0),
    'Mithril Claws': (66, 32, 0),
    'Mithril Composite Bow': (98, 27, 0),
    'Mithril Greatsword': (105, 50, 0),
    'Mithril Longsword': (72, 42, 0),
    'Mithril Stiletto': (54, 36, 0),
    'Mithril Warhammer': (82, 48, 0),
    'Oak Staff': (26, 32, 0),
    'Runic Blade': (96, 56, 20),
    'Runic Crusher': (110, 64, 20),
    'Runic Greatsword': (140, 67, 20),
    'Runic Kris': (72, 48, 20),
    'Runic War Fists': (88, 42, 20),
    'Runic Warbow': (132, 36, 20),
    'Rusted Dagger': (8, 5, 0),
    "Shadowlord's Blade": (88, 42, 0),
    'Short Sword': (12, 7, 0),
    'Shortbow': (16, 4, 0),
    'Spiked Gauntlets': (44, 21, 0),
    'Steel Cestus': (25, 12, 0),
    'Steel Dagger': (20, 13, 0),
    "Treant Elder's Staff": (58, 72, 0),
    'War Bow': (65, 18, 0),
    'War Mace': (55, 32, 0),
    'Wooden Mace': (14, 8, 0),
    'Wooden Staff': (11, 14, 0),
}

def init_db():
    '''Initialize SQLite database for persistent analytics.'''
    conn = sqlite3.connect(DB_PATH)
    conn.execute('\n        CREATE TABLE IF NOT EXISTS sessions (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            char_id INTEGER NOT NULL,\n            started_at REAL NOT NULL,\n            ended_at REAL,\n            zone_id INTEGER,\n            kills INTEGER DEFAULT 0,\n            damage INTEGER DEFAULT 0,\n            healing INTEGER DEFAULT 0,\n            xp_gained INTEGER DEFAULT 0,\n            gold_gained INTEGER DEFAULT 0\n        )\n    ')
    conn.execute('\n        CREATE TABLE IF NOT EXISTS gear_snapshots (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            char_id INTEGER NOT NULL,\n            timestamp REAL NOT NULL,\n            slot TEXT NOT NULL,\n            item_name TEXT NOT NULL,\n            rarity TEXT,\n            p_atk INTEGER DEFAULT 0,\n            m_atk INTEGER DEFAULT 0,\n            p_def INTEGER DEFAULT 0,\n            m_def INTEGER DEFAULT 0\n        )\n    ')
    conn.execute('\n        CREATE TABLE IF NOT EXISTS gold_history (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            char_id INTEGER NOT NULL,\n            timestamp REAL NOT NULL,\n            gold INTEGER NOT NULL\n        )\n    ')
    conn.execute("\n        CREATE TABLE IF NOT EXISTS progression_markers (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            char_id INTEGER NOT NULL,\n            timestamp REAL NOT NULL,\n            event_type TEXT NOT NULL,  -- 'level_up', 'gear_upgrade', 'ascend', 'zone_move'\n            detail TEXT\n        )\n    ")
    conn.commit()
    return conn


class RestClient:
    '''HTTP API wrapper with auto auth and refresh.'''
    
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.ctx = ssl.create_default_context()
        self.token = None
        self.refresh_token = None
        self._last_error = None

    
    def _request(self, method, path, data = (None,)):
        headers = {
            'Content-Type': 'application/json' }
        if self.token:
            headers['Authorization'] = f'''Bearer {self.token}'''
        body = json.dumps(data).encode() if data else None
        req = urllib.Request(f'''{BASE}{path}''', data = body, headers = headers, method = method)
        
        try:
            resp = urllib.urlopen(req, context = self.ctx, timeout = 15)
            return json.loads(resp.read())
        except HTTPError as e:
            err_body = e.read().decode()[:500]
            if e.code == 401 and self.refresh_token:
                refresh_req = urllib.Request(f'''{BASE}/api/auth/refresh''', data = json.dumps({
                    'refreshToken': self.refresh_token }).encode(), headers = {
                    'Content-Type': 'application/json' }, method = 'POST')
                refresh_resp = json.loads(urllib.urlopen(refresh_req, context = self.ctx, timeout = 15).read())
                self.token = refresh_resp.get('accessToken', self.token)
                headers['Authorization'] = f'''Bearer {self.token}'''
                req2 = urllib.Request(f'''{BASE}{path}''', data = body, headers = headers, method = method)
                return json.loads(urllib.urlopen(req2, context = self.ctx, timeout = 15).read())
            self._last_error = f'''HTTP {e.code}: {err_body}'''
            return None

    
    def login(self):
        data = self._request('POST', '/api/auth/login', {
            'email': self.email,
            'password': self.password })
        self.token = data.get('accessToken')
        self.refresh_token = data.get('refreshToken')
        return data

    
    def get(self, path):
        return self._request('GET', path)

    
    def post(self, path, data):
        return self._request('POST', path, data)

    
    def put(self, path, data):
        return self._request('PUT', path, data)

    
    def delete(self, path):
        return self._request('DELETE', path)


from typing import NamedTuple
class ZoneInfo(NamedTuple):
    id: int
    name: str
    zone_type: str
    level_min: int
    level_max: int

class WorldData:
    '''Cached world map data — zones, connections, travel times.'''
    
    def __init__(self, rest=None):
        self.rest = rest
        self.zones = { }
        self.connections = []
        self.adjacency = { }
        self._loaded = False

    
    def load(self):
        if self._loaded:
            return None
        data = self.rest.get('/api/world/map')
        if isinstance(data, dict) and 'connections' in data:
            # Build zone info from zones array (has correct types)
            zones_info = {}
            for z in data.get('zones', []):
                zid = z['id']
                zones_info[zid] = ZoneInfo(
                    zid,
                    z.get('name', f'Zone{zid}'),
                    z.get('type', 'unknown'),
                    z.get('levelRangeMin', 1),
                    z.get('levelRangeMax', 99)
                )
            self.zones = zones_info
            # Build adjacency from connections
            for c in data['connections']:
                za = c.get('zoneAId')
                zb = c.get('zoneBId')
                tt = c.get('travelTimeSeconds', 30)
                if za and zb:
                    self.adjacency.setdefault(za, []).append({
                        'target_id': zb,
                        'travel_time': tt,
                        'name': c.get('targetZoneName', 'Unknown')
                    })
                    self.adjacency.setdefault(zb, []).append({
                        'target_id': za,
                        'travel_time': tt,
                        'name': c.get('sourceZoneName', 'Unknown')
                    })
            self.connections = data['connections']
            self._loaded = True
            return None

    
    def find_best_zones(self, level=None, zone_type='hunting_ground', max_results=5):
        '''Find best farming zones for a given level.'''
        if not self._loaded or level is None:
            return []
        candidates = []
        for zid, info in self.zones.items():
            if info.zone_type == zone_type and info.level_min <= level <= info.level_max:
                score = abs(level - (info.level_min + info.level_max) // 2)
                candidates.append((score, zid, info.name))
        candidates.sort()
        return [{'id': zid, 'name': name} for _, zid, name in candidates[:max_results]]

    
    def find_path(self, from_zone=None, to_zone=None):
        '''BFS to find shortest path between zones. Returns list of zone IDs.'''
        if from_zone not in self.adjacency or to_zone not in self.adjacency:
            return None
        if from_zone == to_zone:
            return [from_zone]
        visited = {from_zone: None}
        queue = [from_zone]
        found = False
        while queue and not found:
            cur = queue.pop(0)
            for edge in self.adjacency.get(cur, []):
                target = edge['target_id']
                if target not in visited:
                    visited[target] = cur
                    if target == to_zone:
                        found = True
                        break
                    queue.append(target)
        if not found:
            return None
        # Reconstruct path
        path = [to_zone]
        while path[-1] != from_zone:
            path.append(visited[path[-1]])
        path.reverse()
        return path

    
    def get_nearby_zones(self, zone_id=None, max_hops=2):
        '''Get zones within N hops of current zone.'''
        if zone_id is None or zone_id not in self.adjacency:
            return {}
        result = {}
        queue = [(zone_id, 0)]
        visited = {zone_id}
        while queue:
            cur, hops = queue.pop(0)
            if cur != zone_id:
                result[cur] = hops
            if max_hops is not None and hops >= max_hops:
                continue
            for edge in self.adjacency.get(cur, []):
                target = edge['target_id']
                if target not in visited:
                    visited.add(target)
                    queue.append((target, hops + 1))
        return result


WEAPON_TREE = {
    'wizard': [
        ('Wooden Staff', 85, 0, 14, 1, 11472),
        ('Oak Staff', 86, 0, 32, 10, 137659),
        ('Arcane Staff', 87, 0, 55, 20, 275318),
        ('Elven Staff', None, 0, 72, 25, 450000),
        ('Sorcerer Staff', None, 0, 90, 30, 600000),
        ('Mithril Staff', None, 0, 110, 35, 800000),
        ('Archmage Staff', None, 0, 135, 40, 1100000),
        ('Eldritch Staff', None, 0, 160, 45, 1500000),
        ('Abyssal Staff', None, 0, 190, 50, 2000000)],
    'fighter': [
        ('Broad Sword', None, 34, 0, 1, 10000),
        ('Long Sword', None, 48, 0, 10, 85000),
        ('Steel Sword', None, 60, 0, 15, 180000),
        ('Battle Axe', None, 75, 0, 20, 300000),
        ('Katana', None, 90, 0, 25, 500000),
        ('Great Sword', None, 108, 0, 30, 650000),
        ('Rune Blade', None, 128, 0, 35, 900000),
        ('Eldritch Blade', None, 152, 0, 40, 1200000),
        ('Abyssal Blade', None, 180, 0, 45, 1600000)] }
ARMOR_TREE = {
    'wizard': [
        ('Apprentice Robe', 'body', 12, 8, 1, 5000),
        ('Apprentice Pants', 'legs', 8, 5, 1, 3000),
        ('Hardened Tunic', 'body', 24, 16, 10, 65000),
        ('Hardened Pants', 'legs', 16, 10, 10, 40000),
        ('Silk Robe', 'body', 35, 25, 18, 150000),
        ('Silk Pants', 'legs', 22, 16, 18, 90000),
        ('Mithril Robe', 'body', 50, 35, 25, 350000),
        ('Mithril Pants', 'legs', 32, 22, 25, 200000),
        ('Karmian Robe', 'body', 68, 48, 32, 600000),
        ('Karmian Pants', 'legs', 44, 30, 32, 350000),
        ('Demon Robe', 'body', 85, 60, 38, 1000000),
        ('Demon Pants', 'legs', 55, 38, 38, 600000)],
    'fighter': [
        ('Leather Tunic', 'body', 18, 4, 1, 6000),
        ('Leather Pants', 'legs', 12, 3, 1, 3500),
        ('Hardened Tunic', 'body', 35, 10, 10, 75000),
        ('Hardened Pants', 'legs', 22, 7, 10, 45000),
        ('Manticore Skin', 'body', 52, 18, 18, 180000),
        ('Manticore Leggings', 'legs', 34, 12, 18, 110000),
        ('Plated Leather', 'body', 72, 25, 25, 400000),
        ('Plated Leggings', 'legs', 46, 16, 25, 240000),
        ('Theca Leather', 'body', 92, 32, 32, 700000),
        ('Theca Leggings', 'legs', 58, 20, 32, 420000)],
    'tank': [
        ('Steel Plate', 'body', 35, 6, 10, 90000),
        ('Steel Leggings', 'legs', 22, 4, 10, 50000),
        ('Chain Mail', 'body', 55, 12, 18, 220000),
        ('Chain Leggings', 'legs', 34, 8, 18, 130000),
        ('Composite Armor', 'body', 78, 20, 25, 500000),
        ('Composite Leggings', 'legs', 48, 14, 25, 300000),
        ('Full Plate', 'body', 100, 28, 32, 850000),
        ('Full Leggings', 'legs', 62, 18, 32, 500000)] }
ACCESSORY_TREE = {
    'general': [
        ('Silver Ring', 'ring1', 0, 0, 1, 15000, {
            'pDef': 2,
            'mDef': 2 }),
        ('Silver Amulet', 'amulet', 0, 0, 1, 20000, {
            'pDef': 3,
            'mDef': 5 }),
        ('Ruby Ring', 'ring1', 0, 0, 15, 80000, {
            'str': 2,
            'pAtk': 3 }),
        ('Sapphire Ring', 'ring1', 0, 0, 15, 80000, {
            'int': 2,
            'mAtk': 3 }),
        ('Topaz Earring', 'earring', 0, 0, 20, 150000, {
            'dex': 2,
            'evasion': 3 }),
        ('Emerald Necklace', 'necklace', 0, 0, 25, 250000, {
            'con': 3,
            'maxHp': 50 }),
        ('Blessed Ring', 'ring1', 0, 0, 30, 500000, {
            'pAtk': 6,
            'mAtk': 6,
            'str': 3,
            'int': 3 })] }

def get_armor_tree(character_class = None, pdef = dataclass, has_shield = None):
    '''Determine if char should use wizard, fighter, or tank armor tree.'''
    if character_class == 'wizard':
        return ARMOR_TREE['wizard']
    if None or pdef > 80:
        return ARMOR_TREE['tank']
    return ARMOR_TREE['fighter']


def suggest_gear_upgrade(character_class=None, current_gear=None, gold=None, has_shield=False):
    '''Suggest next gear upgrades based on current equipment and gold.'''
    suggestions = []

    # Check weapon upgrade
    weapon_tree = WEAPON_TREE.get(character_class, WEAPON_TREE.get('fighter', []))
    current_weapon_name = None
    current_p_atk = 0
    current_m_atk = 0
    for gear in (current_gear or []):
        if gear.get('slot') in ('main_hand', 'off_hand'):
            current_weapon_name = gear.get('itemName', '')
            current_p_atk = gear.get('pAtk', 0) or 0
            current_m_atk = gear.get('mAtk', 0) or 0
            break

    for name, _, p_atk, m_atk, _, cost in weapon_tree:
        if current_weapon_name != name and (gold or 0) >= cost:
            if (p_atk > current_p_atk or m_atk > current_m_atk):
                suggestions.append({'type': 'weapon', 'name': name, 'cost': cost, 'pAtk': p_atk, 'mAtk': m_atk})

    # Check body armor upgrade
    armor_tree = get_armor_tree(character_class, 0, has_shield)
    current_body = None
    current_body_pdef = 0
    for gear in (current_gear or []):
        if gear.get('slot') == 'body':
            current_body = gear.get('itemName', '')
            current_body_pdef = gear.get('pDef', 0) or 0
            break

    for name, slot, p_def, m_def, _, cost in armor_tree:
        if slot == 'body' and current_body != name and (gold or 0) >= cost and p_def > current_body_pdef:
            suggestions.append({'type': 'armor', 'name': name, 'slot': slot, 'cost': cost, 'pDef': p_def})

    suggestions.sort(key=lambda x: x.get('cost', 999999))
    return suggestions


class CharacterAgent:
    '''Controls a single character via WebSocket + REST API.'''
    
    # Class-level global zone productivity tracking — shared across ALL instances.
    # Records {zone_id: timestamp} for zones that have had monsters recently.
    # Used by zone selection to prefer active zones over empty ones.
    _global_zone_productivity = {}
    
    def __init__(self, char_id=None, config=None, rest=None, analytics=None):
        self.char_id = char_id
        self.name = config['name']
        self.char_class = config.get('class', 'fighter')
        self.role = config.get('role', 'dps')
        self.rest = rest
        self.analytics = analytics
        self.db = analytics.db
        self.ws = None
        self.connected = False
        self.is_autofarming = False
        self.is_dead = False
        self.is_resting = False
        self.is_in_combat = False
        self.is_casting = False
        self.current_zone_id = None
        self.level = 1
        self.hp = 100
        self.max_hp = 100
        self.mp = 100
        self.max_mp = 100
        self.gold = 0
        self.xp = 0
        self.inventory = []
        self.equipped_gear = []
        self.monsters = []
        self.attackers = []
        self.last_event_time = 0
        self._keep_running = True
        self._ws_task = None
        self.role = config.get('role', 'dps')
        self.party_members = { }
        self.partner_agents = { }
        self.is_in_party = False
        self.party_id = None
        # Async events for coordinator synchronization (no dumb delays)
        self.travel_complete = asyncio.Event()
        self.party_joined = asyncio.Event()
        self.monster_spawned = asyncio.Event()
        self.combat_enabled = False
        self._combat_task = None
        self._combat_lock = asyncio.Lock()
        self._skill_blocked_until = 0
        self.combat_state = 'IDLE'
        self.current_target = None
        self.last_attack_time = 0
        self.attack_speed_ms = 2479
        self.skill_cooldowns = { }
        self.heal_targets = []
        self._target_attack_initiated = False
        self._dot_skills = { }
        self._hp_at_rest_start = 0
        self._rest_start_time = 0
        self._hunting_zone_id = None
        self._respawn_zone = None
        self._last_respawn_time = 0
        self._rest_blocked_until = 0
        self._emergency_rest_until = 0
        self._last_rest_attempt = 0.0  # Rate-limit rest retries (3s min interval)
        self._last_seed_time = time.time()  # Don't re-seed immediately (was 0)
        self._failed_seed_count = 0
        self._zone_backoff_until = 0
        self._prior_hunting_zone = None
        self._zone_last_productive = {}  # zone_id → last time reseed produced monsters
        self._zone_surf_list = []  # pre-built list of zones to cycle through
        self._surf_visited = set()  # zones tried in current surf cycle — prevents dead loop
        self._zone_travel_blacklist = set()  # zones that failed travel — don't re-select
        self._town_autofarm_attempted = False  # prevent infinite town backoff retry loop
        self._travel_backoff = 0    # timestamp — don't retry travel before this
        self._last_reseed_delta = 0  # monsters added by last reseed (+/-)
        # ── Empirical profilers ──
        self._empirical_cast_times = {}     # skill_id -> running avg (seconds)
        self._empirical_cast_samples = {}   # skill_id -> count
        self._empirical_gcd = None          # min observed gap between skill uses (s)
        self._empirical_hp_regen = None     # HP per second while resting
        self._empirical_mp_regen = None     # MP per second while resting
        self._regen_sample_start = 0        # timestamp of regen sample window
        self._regen_sample_hp = 0
        self._regen_sample_mp = 0
        self._regen_samples = 0             # regen measurements taken
        self._skill_on_cooldown_errors = 0  # counter for "skill on cooldown" feedback
        self._last_skill_success = 0        # timestamp of last SUCCESSFUL skill fire
        self._next_action_time = 0          # wake target — sleep until this in combat loop
        self._pending_skill_sid = None      # skill_id of skill we just sent
        self._pending_skill_time = 0.0      # when we sent it
        self._last_skill_sid = None          # persistent copy for damage attribution after casting_complete clears _pending
        self._last_skill_clear_time = 0.0    # when _pending was cleared, for 5000ms window
        self._total_casts = 0
        self._total_cast_errors = 0
        self._skill_damage_log = {}  # skill_id -> {'casts': 0, 'total_dmg': 0, 'name': str}
        if self.role == 'tank':
            self.rest_hp_threshold = 0.40  # was 0.25 — tanks died before resting in Lv21-24 zones
            self.rest_mp_threshold = 0.30  # was 0.15
            self.rest_hp_target = 0.85
            self.rest_mp_target = 0.6
        elif self.role == 'healer':
            self.rest_hp_threshold = 0.5
            self.rest_mp_threshold = 0.50  # Rest earlier to avoid MP dead zone
            self.rest_hp_target = 0.9
            self.rest_mp_target = 0.85
        else:
            self.rest_hp_threshold = 0.35
            self.rest_mp_threshold = 0.4
            self.rest_hp_target = 0.6
            self.rest_mp_target = 0.6
        self.skills = []
        self.auto_config = []
        self.world = None  # WorldData — lazily initialized for multi-hop travel
        self._cached_map = None  # cache of /api/world/map — the endpoint is slow (1.4-4.4s) + flaky
        self.session_kills = 0
        self.session_damage = 0
        self.session_healing = 0
        self.session_xp = 0
        self.session_gold = 0
        self.session_start = None
        self.reconnect_delay = 1
        self.max_reconnect_delay = 30

    
    async def ensure_token(self):
        '''Fetch fresh token if needed. Only refresh when the current token is
        near expiry. The old code refreshed on EVERY connect, rotating the
        account session server-side and dropping any other live WS using the
        old token (the server allows one active session per account) — so a
        second character's connect killed the first character's connection.'''
        if self.rest.token:
            try:
                import base64
                payload_b64 = self.rest.token.split('.')[1]
                payload_b64 += '=' * (-len(payload_b64) % 4)
                exp = json.loads(base64.urlsafe_b64decode(payload_b64)).get('exp', 0)
                if exp and exp - time.time() > 120:
                    return  # Token still valid — reuse it, no session rotation
            except Exception:
                pass
        # Refresh if we have a refresh_token (token missing or near expiry)
        try:
            import urllib.request, urllib.error, json
            refresh_req = urllib.request.Request(
                f'{BASE}/api/auth/refresh',
                data=json.dumps({'refreshToken': self.rest.refresh_token}).encode(),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            refresh_resp = json.loads(urllib.request.urlopen(refresh_req, context=self.rest.ctx).read())
            if refresh_resp.get('accessToken'):
                self.rest.token = refresh_resp['accessToken']
                self.rest.refresh_token = refresh_resp.get('refreshToken', self.rest.refresh_token)
                return
        except Exception:
            # Refresh failed (expired or invalid refresh token) — force full login
            pass
        # Fallback: full login. Always call login() on refresh failure — the old
        # check `if not self.rest.token:` only catches unset tokens, not stale ones.
        # A token that exists but is expired still passes `if not token:`, so the
        # character gets stuck in an infinite WS reconnect loop with the dead token.
        self.rest.login()

    # ── SpacetimeDB event push ──
    _STDB_HOST = None
    _STDB_DB = None
    
    def _stdb_push(self, reducer, args):
        """Push events to SpacetimeDB via HTTP API. Non-blocking fire-and-forget."""
        import urllib.request
        host = self._STDB_HOST or '127.0.0.1'
        db = self._STDB_DB or 'grimeage2-dashboard'
        url = f'http://{host}:3001/v1/database/{db}/call/{reducer}'
        try:
            req = urllib.request.Request(
                url, data=json.dumps(args).encode(),
                headers={'Content-Type': 'application/json'}, method='POST',
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            pass

    def _skill_name(self, skill_id):
        """Resolve skill ID to name from cached skills list."""
        for s in self.skills:
            if s.get('id') == skill_id:
                return s.get('name', f'Skill#{skill_id}')
        return f'Skill#{skill_id}'


    def get_ws_url(self):
        return f'''{WS_BASE}/ws?token={self.rest.token}&characterId={self.char_id}'''


    async def ws_send(self, msg_type=None, payload=None):
        '''Send a command over WebSocket.'''
        if not self.ws:
            self.analytics.track_error(self.name, 'ws_send: no connection')
            return
        msg = json.dumps({
            'type': msg_type,
            'payload': payload or {},
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
        })
        try:
            await self.ws.send(msg)
        except Exception as e:
            self.analytics.track_error(self.name, f'ws_send error: {e}')
            self.connected = False


    async def connect(self):
        '''Connect WebSocket and start message loop.'''
        await self.ensure_token()
        # Pre-check character state via REST before WS connection.
        # Dead characters (HP=0) trigger a server-side WS close shortly after
        # the HTTP upgrade. By sending respawn immediately after WS connect
        # (before _message_loop), we ensure the command is processed before
        # the server closes the connection. The reconnect watcher retries
        # ~6s later when the character is alive.
        try:
            char_data = self.rest.get(f'/api/characters/{self.char_id}')
            if char_data:
                self.hp = char_data.get('hp', self.hp)
                self.max_hp = char_data.get('maxHp', self.max_hp)
                self.mp = char_data.get('mp', self.mp)
                self.max_mp = char_data.get('maxMp', self.max_mp)
                self.gold = char_data.get('gold', self.gold)
                self.level = char_data.get('level', self.level)
                self.current_zone_id = char_data.get('currentZoneId', self.current_zone_id)
                self.is_dead = self.hp <= 0
        except Exception:
            pass  # REST fetch is advisory — WS game_state is authoritative
        ws_url = self.get_ws_url()
        try:
            # Cancel old tasks before creating new ones to prevent
            # duplicate _message_loop and _reconnect_watcher accumulation
            # that causes "cannot call recv while another coroutine" errors.
            for task_attr in ('_ws_task', '_reconnect_task', '_combat_task'):
                task = getattr(self, task_attr, None)
                if task and not task.done():
                    task.cancel()
                    setattr(self, task_attr, None)
            self.ws = await websockets.connect(ws_url, ping_interval=10, ping_timeout=5)
            self.connected = True
            self.reconnect_delay = 1  # Reset backoff on successful connect
            # If dead, send respawn IMMEDIATELY before _message_loop starts.
            # The server may close the connection for dead chars, but sending
            # early gives the respawn command the best chance of being processed.
            # Even if the WS still drops, respawn was processed server-side and
            # the reconnect watcher retries with the character now alive.
            if self.is_dead and self.hp <= 0:
                respawn_msg = json.dumps({
                    'type': 'respawn',
                    'payload': {},
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
                })
                try:
                    await self.ws.send(respawn_msg)
                except Exception:
                    pass  # Server may close — respawn may still process
            # Reset sync events on fresh connect
            self.travel_complete.clear()
            self.party_joined.clear()
            self.monster_spawned.clear()
            # Start message loop in background
            self._ws_task = asyncio.create_task(self._message_loop())
            # Start reconnect watcher in background
            self._reconnect_task = asyncio.create_task(self._reconnect_watcher())
            return True
        except Exception as e:
            self.analytics.track_error(self.name, f'connect error: {e}')
            self.connected = False
            return False


    async def _message_loop(self):
        '''Process incoming WebSocket messages.'''
        while self._keep_running and self.connected:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=30)
                data = json.loads(raw)
                await self._handle_message(data)
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                self.connected = False
                break
            except Exception as e:
                self.analytics.track_error(self.name, f'msg loop: {e}')
                self.connected = False
                break
        # Connection lost — the daemon's monitor loop handles reconnection
        if self._keep_running:
            pass

    
    async def _send_keepalive(self):
        """No explicit keepalive needed — server doesn't use ping/pong."""
        pass

    
    
    async def _handle_message(self, data: dict):
        msg_type = data.get('type', '')
        payload = data.get('payload', {})
        self.last_event_time = time.time()

        if msg_type == 'game_state':
            await self._handle_game_state(payload)
        elif msg_type == 'player:stats_update':
            self._handle_stats_update(payload)
        elif msg_type == 'player:level_up':
            self._handle_level_up(payload)
        elif msg_type == 'player:loot':
            self._handle_loot(payload)
        elif msg_type == 'combat:start':
            # Don't interrupt rest during emergency grace period (force-exit recovery).
            # The force-exit code in _check_rest_needed() sets _emergency_rest_until
            # after sending stop_attack and clearing combat state. If the server sends
            # combat:start during this window (from reseed toggle or zone activity),
            # we must NOT cancel rest — otherwise the character enters an unrecoverable
            # loop: force-exit → rest → combat:start cancels → cannot rest → HP drains → die.
            if getattr(self, '_emergency_rest_until', 0) > time.time():
                pass  # Within emergency grace period — keep resting
            else:
                self.is_in_combat = True
                self.is_resting = False
                self.combat_state = 'FIGHTING'
        elif msg_type == 'combat:attack':
            self._handle_attack(payload)
            # Detect skill cast completion: if we sent a skill and this attack
            # is from us with magical/dot type, the cast likely completed.
            # Use this for empirical cast time measurement on wizard spells
            # where casting_complete never fires.
            # ⚠️ CRITICAL: Only fire the proxy if enough time has elapsed since
            # the skill was sent (at least 70% of the skill's cast time). Without
            # this guard, auto-attack events (which also have damageType='magical'
            # for wizards and fire every ~200ms) trigger _record_cast_completion
            # prematurely, clearing _pending_skill_sid and causing the next skill
            # to fire while the previous one is still casting. This was the root
            # cause of wizard zero-damage bug (all "casts" were auto-attack ticks
            # attributed to skills, real skill casts never completed).
            if (self._pending_skill_sid and self._pending_skill_time > 0
                    and payload.get('attackerId') == self.char_id
                    and payload.get('damageType') in ('magical', 'dot', 'skill')):
                elapsed = time.time() - self._pending_skill_time
                skill_info = next((s for s in self.skills if s.get('id') == self._pending_skill_sid), None)
                if skill_info:
                    min_cast = skill_info.get('castTimeMs', 2000) / 1000.0 * 0.7
                else:
                    min_cast = 1.0
                if elapsed >= min_cast:
                    self._record_cast_completion(payload.get('remainingHp'))
        elif msg_type == 'combat:heal_applied':
            self._handle_heal(payload)
            # Healing skill completed — measure cast time
            if (self._pending_skill_sid and self._pending_skill_time > 0
                    and payload.get('casterId') == self.char_id):
                self._record_cast_completion()
        elif msg_type == 'combat:monster_died':
            self._handle_monster_died(payload)
        elif msg_type == 'combat:monster_update':
            self._handle_monster_update(payload)
        elif msg_type == 'combat:rewards':
            self._handle_rewards(payload)
        elif msg_type == 'combat:player_died':
            self._handle_player_died(payload)
        elif msg_type == 'combat:session_restore':
            self.is_autofarming = payload.get('isAutoFarming', False)
            self.is_resting = payload.get('isResting', False)
            self.is_casting = payload.get('isCasting', False)
            tgt_id = payload.get('targetId')
            if tgt_id:
                self.current_target = {
                    'id': tgt_id,
                    'name': payload.get('targetName', '?'),
                    'hp': payload.get('targetHp', 0),
                    'maxHp': payload.get('targetMaxHp', 1),
                }
            for cd in payload.get('cooldowns', []):
                sid = cd.get('skillId')
                expires_at = cd.get('expiresAt', 0)
                if sid and expires_at > 0:
                    self.skill_cooldowns[sid] = expires_at / 1000.0
        elif msg_type == 'combat:rest_start':
            self.is_resting = True
        elif msg_type == 'combat:rest_complete':
            self.is_resting = False
        elif msg_type == 'combat:rest_interrupted':
            self.is_resting = False
        elif msg_type == 'combat:casting_start':
            self.is_casting = True
        elif msg_type == 'combat:casting_complete':
            self.is_casting = False
            cd_sec = payload.get('cooldownSec', 0)
            skill_id = payload.get('skillId')
            if skill_id and cd_sec > 0:
                self.skill_cooldowns[skill_id] = time.time() + cd_sec
            # Measure actual cast time from this event
            if self._pending_skill_sid and self._pending_skill_time > 0:
                if not skill_id or skill_id == self._pending_skill_sid:
                    self._record_cast_completion()
            # Push skill event to SpacetimeDB
            if skill_id:
                sname = self._skill_name(skill_id)
                self._stdb_push('record_skill_event', [self.char_id, self.name, skill_id, sname, 'cast', 0, ''])
        elif msg_type == 'combat:cooldown_started':
            skill_id = payload.get('skillId')
            cd_sec = payload.get('cooldownSec', 0)
            if skill_id and cd_sec > 0:
                self.skill_cooldowns[skill_id] = time.time() + cd_sec
        elif msg_type == 'combat:stopped':
            self.is_in_combat = False
            self.combat_state = 'IDLE'
            self.is_autofarming = False
            reason = payload.get('reason', 'unknown')
            if reason == 'death':
                self.is_dead = True
        elif msg_type == 'combat:waiting':
            pass
        elif msg_type == 'combat:monster_spawned':
            now = time.time()
            monster = {
                'id': payload.get('monsterId'),
                'monsterId': payload.get('monsterId'),
                'name': payload.get('monsterName'),
                'hp': payload.get('hp'),
                'maxHp': payload.get('maxHp'),
                '_spawned_at': now,
                '_last_hp_update': now,
            }
            if not any(m.get('id') == monster['id'] for m in self.monsters):
                self.monsters.append(monster)
                self._last_reseed_delta = 1  # New monster arrived naturally — reset guard
                self.monster_spawned.set()
                # Update global zone productivity — this zone has active monsters
                if self.current_zone_id:
                    CharacterAgent._global_zone_productivity[self.current_zone_id] = time.time()
        elif msg_type == 'respawn:complete':
            # Character respawned — alive again. Update current_zone_id to respawn zone
            # so the combat tick's travel-back check triggers (character is now in town).
            # CRITICAL: When connecting already dead, _handle_player_died never fires,
            # so _respawn_zone is None. In that case, if current_zone_id still shows
            # the hunting zone, force it to zone 1 (town — default respawn zone).
            # CRITICAL: Must reset is_dead and hp — without this the character stays
            # at 0 HP permanently and every combat tick returns immediately (dead check
            # at line 1468/1548). The respawn payload may not include hp, so set
            # is_dead based on whether we got a valid HP value.
            if self._respawn_zone:
                self.current_zone_id = self._respawn_zone
            else:
                # Connected-dead respawn: _respawn_zone is None (no death event
                # captured). The old code forced zone 1 (Talking Island) assuming
                # the default town respawn — but this server respawns high-level
                # chars to Gludios (149). With the wrong local zone (1), the zone
                # finder planned travel from zone-1 reachability and the server
                # (physically in 149) rejected every hop with "no connection" →
                # stuck-in-town loop, 0 kills (observed 2026-08-04 post-fix run).
                # Query REST for the authoritative respawn zone instead of guessing.
                try:
                    cd = self.rest.get(f'/api/characters/{self.char_id}')
                    if isinstance(cd, dict):
                        cz = cd.get('currentZoneId')
                        if isinstance(cz, int) or (isinstance(cz, str) and cz.isdigit()):
                            self.current_zone_id = int(cz)
                        else:
                            # REST lag/wrong — fall back to old behavior
                            self.current_zone_id = 1
                    else:
                        self.current_zone_id = 1
                except Exception:
                    # REST fetch failed — safe fallback so the finder can still run
                    self.current_zone_id = 1
            self._respawn_zone = None
            self.is_dead = False
            # Update HP from payload if available (server may send post-respawn HP)
            respawn_hp = payload.get('hp', None)
            if respawn_hp is not None and respawn_hp > 0:
                self.hp = respawn_hp
            # Clear respawn backoff — character is alive now
            self._respawn_attempts = 0
        elif msg_type == 'combat:attackers_update':
            self.attackers = payload.get('attackers', [])
        elif msg_type == 'combat:threat_update':
            mid = payload.get('monsterId')
            entries = payload.get('entries', [])
            if mid and entries:
                if not hasattr(self, '_threat_table'):
                    self._threat_table = {}
                if mid not in self._threat_table:
                    self._threat_table[mid] = {}
                for e in entries:
                    cid = e.get('characterId')
                    threat = e.get('threat', 0)
                    if cid:
                        self._threat_table[mid][cid] = threat
        elif msg_type == 'combat:target_changed':
            if payload.get('targetId'):
                self.current_target = {'id': payload['targetId']}
        elif msg_type == 'combat:target_fled':
            self.current_target = None
            self._target_attack_initiated = False
        elif msg_type == 'travel_start':
            pass
        elif msg_type == 'travel_complete':
            zid = payload.get('zoneId', payload.get('toZoneId', None))
            # Guard against string zone names (same bug as game_state) — only
            # accept numeric zone ids so comparisons against _hunting_zone_id
            # stay valid (2026-08-04 travel-loop root cause).
            if isinstance(zid, int) or (isinstance(zid, str) and zid.isdigit()):
                self.current_zone_id = int(zid)
                self._save_hunting_zone(self.current_zone_id)
            self.combat_state = 'IDLE'
            self.travel_complete.set()
            # Clear travel blacklist — we're in a new zone with fresh connections
            self._zone_travel_blacklist.clear()
            # Reset stuck-travel detection — we arrived successfully
            self._travel_sent_at = 0
        elif msg_type == 'error':
            err_msg = str(payload)
            if 'cannot rest while under attack' in err_msg.lower():
                # Server says character is under active monster attack — different
                # from stale combat state. The generic "cannot rest" handler sets
                # an 8s backoff which creates a 15-25% HP dead zone: character
                # can't rest but also can't fight effectively at low HP.
                # Instead, set is_in_combat=True to route the next _check_rest_needed()
                # call into the force-exit path (line 1760+), which sends stop_attack,
                # toggles auto-farm to clear server state, and runs a 15s rest retry
                # loop with proper backoff handling.
                self.is_resting = False
                self.combat_state = 'IDLE'
                self._target_attack_initiated = False
                self.is_in_combat = True  # Redirects to force-exit path
                # Short backoff — the force-exit retry loop handles retry timing.
                self._rest_blocked_until = time.time() + 2.0
                # Set emergency grace so the backoff gate (line 1967) doesn't
                # block the force-exit path. The backoff gate checks
                # _emergency_rest_until before returning False — without this,
                # _rest_blocked_until +2.0 blocks the is_in_combat force-exit
                # check at line 1849, trapping the character in an unrecoverable
                # cycle where rest is rejected, backoff blocks retries, and
                # the character keeps fighting with critically low HP/MP.
                # Without this, wizards at 7% MP cycle rest→rejected→fight→rest
                # forever with 0 successful rests (Tick 50 fix).
                self._emergency_rest_until = time.time() + 5.0
                # NOT tracked as an error — this is a server state transition that
                # the force-exit path handles automatically.
            elif 'cannot rest while in combat' in err_msg.lower():
                # Same as 'under attack' above — stale combat state persists
                # after monsters are cleared. Route to force-exit path instead
                # of the generic 8s backoff which creates a 15-25% HP dead zone.
                self.is_resting = False
                self.combat_state = 'IDLE'
                self._target_attack_initiated = False
                self.is_in_combat = True  # Force-exit will clear stale combat state
                self._rest_blocked_until = time.time() + 2.0
                # Same emergency grace fix — prevents backoff gate from blocking
                # the is_in_combat force-exit path (see above comment).
                self._emergency_rest_until = time.time() + 5.0
                # Not tracked as error — force-exit retry handles the timing.
            elif 'cannot rest' in err_msg.lower() or 'not resting' in err_msg.lower():
                self.is_resting = False
                self.combat_state = 'IDLE'
                # If we're in the emergency grace period (recently force-exited combat),
                # skip the backoff AND the error track — rest rejection is expected
                # during the rest retry loop (server combat timer ~6-10s). The retry
                # loop handles this gracefully without needing an error signal.
                if getattr(self, '_emergency_rest_until', 0) > time.time():
                    pass
                else:
                    self.analytics.track_error(self.name, f"Server: {payload}")
                    # Backoff: dynamic cooldown after rejected rest.
                    # Base 8s, extended by current blocked_until if we keep getting rejected.
                    backoff = 8.0
                    blocked_until = getattr(self, '_rest_blocked_until', 0)
                    if blocked_until > time.time():
                        backoff += (blocked_until - time.time()) * 0.5  # 50% extension
                    self._rest_blocked_until = time.time() + backoff
            elif 'already attacking' in err_msg.lower():
                # Benign — server acknowledges existing targeting. Don't track.
                pass
            elif 'already casting' in err_msg.lower():
                self._total_cast_errors += 1
                # Skill cast still in progress — push the global block timer forward
                # to prevent immediate retry on the next tick
                now = time.time()
                blocked_until = getattr(self, '_skill_blocked_until', now)
                if now >= blocked_until:
                    # No global block set, use empirical cast time + measured latency
                    empirical = self._empirical_cast_times.get(self._pending_skill_sid)
                    backstop = empirical + 0.2 if empirical else 2.0
                    self._skill_blocked_until = now + backstop
                else:
                    # Already blocked — extend by measured latency * 2
                    latency = self._get_measured_latency()
                    extension = max(latency * 2.0, 0.5)
                    self._skill_blocked_until = now + max(0, blocked_until - now) + extension
            elif 'skill on cooldown' in err_msg.lower():
                self._skill_on_cooldown_errors += 1
                # Our cooldown estimate was too short. Extend it for this skill
                # and mark so the global block accounts for it.
                sid = self._pending_skill_sid
                if sid and sid in self.skill_cooldowns:
                    now = time.time()
                    remaining = self.skill_cooldowns[sid] - now
                    if remaining < 3.0:  # Only extend if our estimate is < 3s off
                        # Extend by 50% of the gap — should converge quickly
                        self.skill_cooldowns[sid] = now + remaining + remaining * 0.5
            elif 'target not alive' in err_msg.lower():
                self.analytics.track_error(self.name, f"Server: {payload}")
                # Monster died between target selection and skill cast —
                # remove it from the monster list and clear targeting state
                dead_id = self.current_target.get('id') if self.current_target else None
                if dead_id:
                    self.monsters = [m for m in self.monsters if m.get('id') != dead_id]
                self.current_target = None
                self._target_attack_initiated = False
            elif 'already traveling' in err_msg.lower():
                # Character IS traveling — don't reset combat_state or set backoff.
                # The server accepted a previous travel and the character is in transit.
                # Reset combat_state would cause infinite retry: _travel_to_hunting_zone
                # sends start_travel → "already traveling" → error handler sets IDLE →
                # next tick retries travel. Instead, leave TRAVELING state so the
                # guard at _travel_to_hunting_zone line 1966 blocks retries.
                # Set a timeout so we don't wait forever if travel never completes:
                self._travel_timeout = time.time() + 30.0
                self.analytics.log(f"[{self.name}] Already traveling — waiting for arrival")
            elif 'cannot travel' in err_msg.lower() or 'no connection' in err_msg.lower():
                self.analytics.track_error(self.name, f"Server: {payload}")
                # Server rejected travel — character still in combat,
                # rest state active, or destination not directly connected.
                # Reset combat_state so the next tick can retry.
                # Add backoff to prevent busy-looping:
                self._travel_backoff = time.time() + 5.0
                self.combat_state = 'IDLE'
                # If no direct connection, clear hunting zone so _find_and_travel_hunting_zone
                # will re-evaluate with correct reachability info.
                if 'no connection' in err_msg.lower():
                    # Get the failed dest from _hunting_zone_id before it's cleared
                    failed_zone = getattr(self, '_hunting_zone_id', None)
                    if failed_zone:
                        self._zone_travel_blacklist.add(failed_zone)
                        self.analytics.log(f"[{self.name}] Blacklisting zone {failed_zone} — no connection from current position")
                    self._hunting_zone_id = None
                    self.analytics.log(f"[{self.name}] No direct connection — hunting zone cleared for re-evaluation")
                    # Zone 1 (town) long backoff: freshly respawned characters can't
                    # travel from town until the server fully processes the spawn.
                    # Without this, the 5s backoff burns through all 3 zone candidates
                    # in ~15s, producing 8+ "no connection" errors and wasting the
                    # entire test window. A 30s backoff gives the server time to settle.
                    if self.current_zone_id == 1:
                        self._travel_backoff = time.time() + 10.0
                        self.analytics.log(f"[{self.name}] In town — extended travel backoff to 10s")
                        # Track consecutive zone-1 travel failures. After the first
                        # failure from town, set a 120s backoff that switches the
                        # character to auto-farm in town instead of looping on doomed
                        # travel attempts. This prevents the entire test window from
                        # being consumed by repeated "no connection" errors.
                        if getattr(self, '_town_auto_backoff', 0) < time.time():
                            self._town_auto_backoff = time.time() + 120
                            self.analytics.log(f"[{self.name}] Town travel failed — will auto-farm in town for 120s")
                else:
                    self.analytics.log(f"[{self.name}] Travel rejected — will retry in 5s")
            elif 'cannot use auto-farm while in a party' in err_msg.lower():
                self.analytics.track_error(self.name, f"Server: {payload}")
                # Server-side party state blocks auto-farm but the client doesn't
                # know about it (party:joined never fired on this connection).
                # Flag ourselves as partied so reseed knows to leave first.
                self.is_autofarming = False
                if not self.is_in_party:
                    self.is_in_party = True
                    self.analytics.log(f"[{self.name}] Detected server-side party state — marked as partied")
        elif msg_type.startswith('party:'):
            await self._handle_party_event(msg_type, payload)
        elif msg_type.startswith('whisper:'):
            pass


    async def _handle_game_state(self, payload: dict):
        """Full game state on connect — character, stats, zone, players."""
        char = payload.get('character', {})

        # Character basics
        self.char_class = char.get('class', self.char_class)
        self.level = char.get('level', self.level)
        self.hp = char.get('hp', self.hp)
        self.max_hp = char.get('maxHp', self.max_hp)
        self.mp = char.get('mp', self.mp)
        self.max_mp = char.get('maxMp', self.max_mp)
        self.gold = char.get('gold', self.gold)
        self.xp = char.get('xp', self.xp)
        self.current_zone_id = char.get('currentZoneId', self.current_zone_id)
        # Guard: currentZoneId is normally numeric; if it's a name string
        # (observed "Gludios" in game_state zone.id), keep the numeric value.
        if isinstance(self.current_zone_id, str) and not self.current_zone_id.isdigit():
            self.current_zone_id = None
        elif self.current_zone_id is not None:
            self.current_zone_id = int(self.current_zone_id)
        self.is_dead = char.get('hp', 0) <= 0

        # Base stats
        stats = payload.get('stats', {})
        if isinstance(stats, dict):
            self.attack_speed_ms = stats.get('attackSpeedMs', self.attack_speed_ms)

        # Zone info
        zone = payload.get('zone', {})
        if zone:
            zid = zone.get('id')
            # CRITICAL (2026-08-04 travel-loop root cause): the server's
            # game_state `zone.id` is sometimes the zone NAME STRING (e.g.
            # "Gludios") instead of the numeric id — sent while the character
            # is physically in a hunting ground (64188). Assigning the string
            # clobbers current_zone_id → every zone comparison fails →
            # endless "Traveling to 64188" re-travel → manual farm 0-kill loop
            # (observed 15-min run + 90s capture). char.currentZoneId (set
            # above from payload.character) holds the correct numeric zone, so
            # only apply zone.id when it's numeric; otherwise keep it.
            if isinstance(zid, int) or (isinstance(zid, str) and zid.isdigit()):
                self.current_zone_id = int(zid)

        # Mark connected + log progression
        if not self.session_start:
            self.session_start = time.time()
            self.analytics.char_connected(self.char_id, self.name, self.current_zone_id, self.gold)
            self._log_progression('connect', f'Lv{self.level} in zone {self.current_zone_id}')
            # Fetch skills, gear, and inventory from REST
            self.fetch_inventory()  # Populates equipped_gear for weapon checks
            # Never leave an upgrade in the bag — equip the best weapon by class
            # stat BEFORE filtering skills, so dagger/bow-gated skills get
            # included in the rotation when a qualifying weapon is equipped.
            self._auto_equip_best_weapon()
            self.fetch_inventory()  # refresh after equip
            await self._load_skills_from_rest()
            # Pre-filter skills based on current weapon — removes skills that
            # require weapons we don't have, so _use_best_skill doesn't waste
            # ticks iterating through unusable skills.
            self._filter_skills_by_weapon()
            # Track initial zone as potential hunting zone (only on first connect)
            self._save_hunting_zone(self.current_zone_id)
        elif not self.skills or not self.auto_config:
            # Skills missing after reconnect (WS disconnected before game_state
            # loaded skills on first connect). Re-fetch so combat AI can fire.
            self.fetch_inventory()
            await self._load_skills_from_rest()
            self._filter_skills_by_weapon()

    
    def _handle_stats_update(self, payload=None):
        self.hp = payload.get('hp', self.hp)
        self.max_hp = payload.get('maxHp', self.max_hp)
        self.mp = payload.get('mp', self.mp)
        self.max_mp = payload.get('maxMp', self.max_mp)
        self.xp = payload.get('xp', self.xp)
        old_level = self.level
        self.level = payload.get('level', self.level)
        # Reset respawn backoff counter when revived
        was_dead = self.is_dead
        self.is_dead = self.hp <= 0
        if was_dead and not self.is_dead:
            self._respawn_attempts = 0

    
    def _handle_level_up(self, payload=None):
        self.level = payload.get('newLevel', self.level)
        self._log_progression('level_up', f'''Reached Lv{self.level}''')
        self.analytics.track_level_up(self.char_id, self.level)

    
    def _handle_loot(self, payload=None):
        item_name = payload.get('itemName', '?')
        quantity = payload.get('quantity', 1)
        rarity = payload.get('rarity', 'common')
        self.analytics.track_loot(self.char_id, item_name, rarity)

    
    def _handle_attack(self, payload=None):
        if payload.get('attackerId') == self.char_id:
            dmg = payload.get('damage', 0)
            dmg_type = payload.get('damageType', '?')
            self.session_damage += dmg
            self.analytics.track_damage(self.char_id, dmg)
            # Attribute damage to pending skill if we're expecting one.
            # Also check _last_skill_sid (persistent copy) for 5000ms after clear,
            # because fighter skills fire casting_complete BEFORE combat:attack arrives,
            # clearing _pending_skill_sid and losing the attribution window.
            # ⚠️ Tick 76 fix: When BOTH _pending_skill_sid and _last_skill_sid are set,
            # the damage may belong to _last_skill_sid (previous skill) if the pending
            # skill was sent too recently for its damage to have arrived. This happens
            # when wizard spell A's physical damage arrives AFTER spell B is already sent
            # (spell A's proxy-cleared _pending_skill_sid was already overwritten by B).
            # Check: if _last_skill_clear_time is recent AND the pending skill hasn't
            # been pending long enough for its damage to arrive (<80% of cast time),
            # use _last_skill_sid instead of _pending_skill_sid.
            now = time.time()
            skill_sid = self._pending_skill_sid
            if skill_sid and self._last_skill_sid:
                # Both pending and last are set. Check if pending was sent recently
                # (damage likely belongs to last, not pending).
                sent_ago = now - self._pending_skill_time if self._pending_skill_time > 0 else 999
                last_age = now - self._last_skill_clear_time if self._last_skill_clear_time > 0 else 999
                # If last_skill was cleared within the last 5s AND pending is very young
                # (<80% of typical cast time for the pending skill) OR last is much newer
                # than pending (last cleared <1s ago but pending sent >1.5s ago),
                # attribute to last_skill instead.
                if last_age < 5.0:
                    skill_info = next((s for s in self.skills if s.get('id') == skill_sid), None)
                    min_cast_to_attrib = 0.5  # default 500ms minimum
                    if skill_info:
                        min_cast_to_attrib = skill_info.get('castTimeMs', 2000) / 1000.0 * 0.8
                    if sent_ago < min_cast_to_attrib:
                        # Pending skill is too young — damage belongs to last skill
                        skill_sid = self._last_skill_sid
            if not skill_sid and self._last_skill_sid:
                # Within 5000ms of clear? Use persistent copy.
                if now - self._last_skill_clear_time < 5.0:
                    skill_sid = self._last_skill_sid
            if dmg > 0 and skill_sid:
                sid = skill_sid
                if sid not in self._skill_damage_log:
                    self._skill_damage_log[sid] = {'casts': 0, 'total_dmg': 0, 'name': '?'}
                self._skill_damage_log[sid]['total_dmg'] += dmg
                # ⚠️ DIAGNOSTIC: Log combat:attack with damage during pending skill.
                # Tick 56 found that ALL use_skill produces 0 dmg. This log captures
                # what damage arrives during the pending window to determine if skills
                # produce damage through a different event path or with different keys.
                # Remove after root cause found (Tick 57+).
                diag = getattr(self, '_dmg_diag_count', 0)
                if diag < 10:
                    self._dmg_diag_count = diag + 1
                    sname = self._skill_name(skill_sid)
                    self.analytics.log(f"[DIAG] dmg={dmg} type={dmg_type} skill={sname}({skill_sid}) target={payload.get('targetName','?')} from={'_pending' if self._pending_skill_sid else '_last'}")
            if dmg > 0:
                self._stdb_push('record_combat_event', [self.char_id, self.name, 'damage', int(dmg), payload.get('targetName', '')])
        self._handle_monster_update(payload)

    
    def _handle_heal(self, payload=None):
        if payload.get('casterId') == self.char_id:
            amt = payload.get('amount', 0)
            self.session_healing += amt
            self.analytics.track_healing(self.char_id, amt)
            if amt > 0:
                self._stdb_push('record_combat_event', [self.char_id, self.name, 'heal', int(amt), payload.get('targetName', '')])
            return None

    
    def _handle_monster_died(self, payload: dict):
        mid = payload.get('monsterId')
        # Remove from monster list
        self.monsters = [m for m in self.monsters if m.get('id') != mid]
        # Clear DoT tracking for this target
        for skill_id in list(self._dot_skills.keys()):
            self._dot_skills[skill_id].pop(mid, None)
            if not self._dot_skills[skill_id]:
                del self._dot_skills[skill_id]
        if self.current_target and self.current_target.get('id') == mid:
            self.current_target = None
            # Reset attack state — the old target is gone, need fresh select_target
            self._target_attack_initiated = False
            # Track the kill event - always on monster_died (someone got the kill)
            monster_name = payload.get('monsterName', payload.get('name', 'unknown'))
            self._stdb_push('record_combat_event', [self.char_id, self.name, 'kill', 1, monster_name])
            self._target_attack_initiated = False
            if payload.get('winnerId') == self.char_id:
                self.session_kills += 1
                name = payload.get('monsterName', 'unknown')
                self.analytics.track_kill(self.char_id, name)

    def _handle_monster_update(self, payload: dict):
        """Update monster HP from combat:monster_update and combat:attack events."""
        mid = payload.get('monsterId')
        hp = payload.get('hp')
        # Also update from combat:attack which has targetId and remainingHp
        if not mid:
            mid = payload.get('targetId')
        if not hp:
            hp = payload.get('remainingHp')
        if mid and hp is not None:
            for m in self.monsters:
                if m.get('id') == mid:
                    m['hp'] = hp
                    m['_last_hp_update'] = time.time()
                    break
            if self.current_target and self.current_target.get('id') == mid:
                self.current_target['hp'] = hp

    
    def _handle_rewards(self, payload=None):
        xp = payload.get('xpGained', 0)
        gold = payload.get('goldGained', 0)
        self.session_xp += xp
        self.session_gold += gold
        self.analytics.track_rewards(self.char_id, xp, gold)
        if xp > 0:
            self._stdb_push('record_combat_event', [self.char_id, self.name, 'xp', int(xp), ''])
        if gold > 0:
            self._stdb_push('record_combat_event', [self.char_id, self.name, 'gold', int(gold), ''])

    
    def _handle_player_died(self, payload=None):
        self.is_dead = True
        self.is_in_combat = False
        self._target_attack_initiated = False
        self.analytics.track_error(self.name, f'''Died to {payload.get('killedByName', '?')}''')
        self._log_progression('death', f'''Killed by {payload.get('killedByName', '?')}''')
        self._respawn_zone = payload.get('respawnZone')

    
    async def _handle_party_event(self, msg_type=None, payload=None):
        """Handle party-related WS events."""
        if msg_type == 'party:invite_received':
            self._pending_invite_from = payload.get('fromCharId')
            self._pending_invite_name = payload.get('fromName')
            self._pending_party_id = payload.get('partyId')
            # Signal any waiting coordinator that invite arrived
            if hasattr(self, '_invite_received_event'):
                self._invite_received_event.set()
            self.analytics.log(f"[{self.name}] Party invite from {payload.get('fromName')}")
        elif msg_type == 'party:joined':
            self.is_in_party = True
            self.party_id = payload.get('partyId')
            members = payload.get('members', [])
            for m in members:
                cid = m.get('characterId')
                if cid:
                    self.party_members[cid] = {
                        'name': m.get('name'),
                        'hp': m.get('hp', 0),
                        'maxHp': m.get('maxHp', 1),
                        'mp': m.get('mp', 0),
                        'maxMp': m.get('maxMp', 1),
                        'level': m.get('level', 1),
                        'zone': m.get('zoneId'),
                        'online': m.get('online', False),
                    }
            self.analytics.log(f"[{self.name}] Joined party {self.party_id}")
            self.party_joined.set()
        elif msg_type == 'party:update':
            self.party_id = payload.get('partyId')
            self.is_in_party = True
            members = payload.get('members', [])
            for m in members:
                cid = m.get('characterId')
                if cid:
                    self.party_members[cid] = {
                        'name': m.get('name'),
                        'hp': m.get('hp', 0),
                        'maxHp': m.get('maxHp', 1),
                        'mp': m.get('mp', 0),
                        'maxMp': m.get('maxMp', 1),
                        'level': m.get('level', 1),
                        'zone': m.get('zoneId'),
                        'online': m.get('online', False),
                    }
            self.party_joined.set()
        elif msg_type == 'party:member_joined':
            cid = payload.get('characterId')
            if cid:
                self.party_members[cid] = {
                    'name': payload.get('name'),
                    'hp': payload.get('hp', 0),
                    'maxHp': payload.get('maxHp', 1),
                    'zone': payload.get('zoneId'),
                    'online': True,
                }
            # If this character joined, signal the event
            if payload.get('characterId') == self.char_id:
                self.party_joined.set()
                self.is_in_party = True
        elif msg_type == 'party:member_left':
            cid = payload.get('characterId')
            if cid and cid in self.party_members:
                del self.party_members[cid]
        elif msg_type == 'party:member_stats':
            cid = payload.get('characterId')
            if cid and cid in self.party_members:
                self.party_members[cid]['hp'] = payload.get('hp', self.party_members[cid].get('hp', 0))
                self.party_members[cid]['maxHp'] = payload.get('maxHp', self.party_members[cid].get('maxHp', 1))
                self.party_members[cid]['mp'] = payload.get('mp', self.party_members[cid].get('mp', 0))
                self.party_members[cid]['maxMp'] = payload.get('maxMp', self.party_members[cid].get('maxMp', 1))
        elif msg_type == 'party:member_zone':
            cid = payload.get('characterId')
            if cid and cid in self.party_members:
                self.party_members[cid]['zone'] = payload.get('zoneId')
        elif msg_type == 'party:disbanded':
            self.is_in_party = False
            self.party_id = None
            self.party_members = {}
        elif msg_type == 'party:left':
            self.is_in_party = False
            self.party_id = None
            self.party_members = {}
            self.party_joined.clear()
            self.analytics.log(f"[{self.name}] Left party (confirmed)")
        elif msg_type == 'party:invite_failed':
            self.analytics.log(f"[{self.name}] Party invite failed: {payload.get('reason')}")

    
    async def _reconnect_watcher(self):
        '''Background watcher that triggers reconnect when WS drops.
        Also restarts combat AI after successful reconnect.'''
        while self._keep_running:
            await asyncio.sleep(5)  # Check every 5s
            if not self.connected:
                self.analytics.log(f'[{self.name}] WS disconnected — starting reconnect...')
                self.combat_state = 'DISCONNECTED'
                await self._reconnect()
                # Combat AI needs restart after reconnect
                if self.combat_enabled and self.connected:
                    self._combat_task = None
                    await self.enable_combat()

    async def _reconnect(self):
        '''Reconnect with exponential backoff.'''
        while self._keep_running and not self.connected:
            self.analytics.log(f'[{self.name}] Reconnecting in {self.reconnect_delay}s...')
            await asyncio.sleep(self.reconnect_delay)
            self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
            ok = await self.connect()
            if ok:
                self.reconnect_delay = 1
                self.analytics.log(f'[{self.name}] Reconnected')
                break

    
    def _log_progression(self, event_type=None, detail=None):
        
        try:
            self.db.execute('INSERT INTO progression_markers (char_id, timestamp, event_type, detail) VALUES (?, ?, ?, ?)', (self.char_id, time.time(), event_type, detail))
            self.db.commit()
            return None
        except Exception:
            return None


    
    async def start_autofarm(self):
        """Start auto-farming."""
        if not self.is_autofarming:
            await self.ws_send('combat:toggle_autofarm', {})
            self.is_autofarming = True

    
    async def stop_autofarm(self):
        '''Stop auto-farming.'''
        if self.is_autofarming:
            await self.ws_send('combat:toggle_autofarm', {})
            self.is_autofarming = False

    
    async def rest(self):
        """Start resting."""
        await self.ws_send('combat:rest', {})
        self.is_resting = True

    async def cancel_rest(self):
        """Cancel current rest."""
        await self.ws_send('combat:cancel_rest', {})
        self.is_resting = False

    
    
    async def set_rest_config(self, enabled=None, hp_threshold=None, mp_threshold=None):
        """Configure rest thresholds for auto-rest."""
        if enabled is not None:
            self.rest_enabled = enabled
        if hp_threshold is not None:
            self.rest_hp_threshold = hp_threshold / 100.0
        if mp_threshold is not None:
            self.rest_mp_threshold = mp_threshold / 100.0

    
    async def travel_to(self, zone_id=None):
        '''Travel to a zone.'''
        if zone_id and zone_id != self.current_zone_id:
            self.combat_state = 'TRAVELING'
            await self.ws_send('start_travel', {'path': [zone_id]})
            self._target_attack_initiated = False
            self.current_target = None

    async def travel_path(self, path=None):
        '''Travel along a multi-hop path.'''
        if path:
            self.combat_state = 'TRAVELING'
            await self.ws_send('start_travel', {'path': path})
            self._target_attack_initiated = False
            self.current_target = None

    async def fast_travel(self, zone_id=None):
        '''Fast travel to a known zone.'''
        await self.travel_to(zone_id)

    
    
    async def respawn(self):
        await self.ws_send('respawn', {})

    
    async def use_skill(self, skill_id=None, target_id=None, target_type='monster'):
        '''Use a skill on a target.'''
        if skill_id and target_id:
            await self.ws_send('combat:use_skill', {
                'skillId': skill_id,
                'targetId': target_id,
                'targetType': target_type
            })

    
    async def attack(self, target_id=None, target_type='monster'):
        '''Start auto-attacking a target.'''
        if target_id:
            await self.ws_send('combat:attack', {
                'targetId': target_id,
                'targetType': target_type
            })

    
    async def select_target(self, target_id=None, target_type='monster'):
        '''Select a target (required before attack by server protocol).'''
        if target_id:
            await self.ws_send('combat:select_target', {
                'targetId': target_id,
                'targetType': target_type
            })

    
    async def chat(self, message=None):
        '''Send a chat message.'''
        if message:
            await self.ws_send('chat:send', {'message': message})

    
    async def party_invite(self, character_name=None):
        """Send party invite to a character by name."""
        if character_name:
            await self.ws_send('party:invite', {'characterName': character_name})
            self.analytics.log(f"[{self.name}] Invited {character_name} to party")

    
    async def party_accept(self, from_char_id=None):
        """Accept party invite from a character."""
        if from_char_id:
            await self.ws_send('party:accept', {'fromCharId': from_char_id})
            self.analytics.log(f"[{self.name}] Accepted party invite from {from_char_id}")

    
    async def party_leave(self):
        """Leave current party."""
        await self.ws_send('party:leave', {})
        self.is_in_party = False
        self.party_id = None
        self.party_members = {}
        self.analytics.log(f"[{self.name}] Left party")

    
    async def set_autofarm_rotation(self, skills_config=None):
        '''Set auto-farm skill rotation via REST.'''
        if skills_config:
            result = self.rest.post(f'/api/skills/config/{self.char_id}', {'autoConfig': skills_config})
            if isinstance(result, list):
                self.auto_config = result
                self.auto_config.sort(key=lambda c: self._skill_efficiency(c), reverse=True)

    
    def link_partner_agents(self, partners=None):
        '''Link references to other characters on the same account for cross-character awareness.'''
        self.partner_agents = partners
        if self.role == 'healer':
            self.heal_targets = list(partners.items()) if partners else []

    
    async def enable_combat(self):
        """Enable the manual combat AI loop.
        Stops auto-farm if active (pure manual mode — no hybrid).
        Re-starts the combat loop if it's not running (handles reconnection).
        Handles dead-connect: respawns + travels to hunting zone before starting combat."""
        if self.combat_enabled and self._combat_task and not self._combat_task.done():
            return  # Already running
        # Ensure auto-farm is off before starting manual combat
        if self.is_autofarming:
            await self.stop_autofarm()
            await asyncio.sleep(0.5)
        # Stale party cleanup: if we think we're in a party but have no partner
        # agents (e.g., test_char.py after daemon killed), the party state is
        # stale — leave so the server clears combat state and allows rest.
        if self.is_in_party and not self.partner_agents:
            self.analytics.log(f"[{self.name}] Stale party state (no partners) — leaving party")
            await self.ws_send('party:leave', {})
            self.is_in_party = False
            self.party_members = {}
        # Dead-character recovery: if dead at connect, respawn and travel before starting loop
        # Note: connect() now pre-checks death via REST and sends respawn immediately
        # after WS upgrade (before _message_loop starts). This handler is a fallback
        # for cases where the WS reconnection already resolved death.
        if self.hp <= 0 or self.is_dead:
            self.analytics.log(f"[{self.name}] Dead at connect — respawning...")
            self.combat_state = 'DEAD'
            # If WS is already closed (dead char connection dropped), skip respawn
            # and let reconnect watcher handle it — connect() sends respawn immediately
            # on the new WS connection.
            if self.ws and self.connected:
                await self.ws_send('respawn', {})
                # Wait for respawn to complete (up to 15s)
                for i in range(30):
                    await asyncio.sleep(0.5)
                    if not self.is_dead and self.hp > 0:
                        break
            else:
                self.analytics.log(f"[{self.name}] WS disconnected — respawn will be handled by reconnect")
                # If the WS disconnected during respawn attempt and reconnect resolves
                # death, skip ahead. Otherwise the reconnect watcher triggers
                # enable_combat() again once connected.
                if not self.connected:
                    return  # Let reconnect watcher handle the full restart
            # After respawn, characters may be in town OR back in the hunting zone.
            # Check actual current_zone_id from game_state before trying to travel.
            self.analytics.log(f"[{self.name}] Respawed, zone={self.current_zone_id}, HP={self.hp}/{self.max_hp}")
            # Always re-evaluate hunting zone after respawn — old _hunting_zone_id
            # may be unreachable from the respawn zone (e.g., zone 1 → 44342 is multi-hop).
            await self._find_and_travel_hunting_zone()
            # Log arrival status
            if self.current_zone_id == self._hunting_zone_id:
                self.analytics.log(f"[{self.name}] In hunting zone {self._hunting_zone_id} after respawn")
            else:
                self.analytics.log(f"[{self.name}] Traveling from zone {self.current_zone_id} to {self._hunting_zone_id}...")
            # Recovery phase: rest/regen to safe HP/MP before engaging combat.
            # Only attempt recovery if we've actually ARRIVED in the hunting zone.
            # If the character is still traveling, recovery commands (stop_attack,
            # auto-farm toggle, combat:rest) are all rejected by the server — the
            # character stands IDLE for the recovery loop's full 20s while travel
            # completes, then enters combat at critically low HP.
            # The combat loop's _check_rest_needed handles low-HP recovery after
            # arrival, so it's safe to skip the pre-arrival recovery entirely.
            if self.current_zone_id == self._hunting_zone_id:
                self.combat_state = 'IDLE'
                hp_pct = self.hp / max(self.max_hp, 1)
                if hp_pct < self.rest_hp_target:
                    self.analytics.log(f"[{self.name}] Recovering HP ({hp_pct:.0%}) after respawn...")
                    await self._recover_before_combat()
            else:
                self.analytics.log(f"[{self.name}] Traveling to zone {self._hunting_zone_id} — deferring HP recovery until arrival")
        else:
            # Validate hunting zone — ensure we're in a valid hunting_ground zone.
            # If not (e.g., _hunting_zone_id saved a city zone like Zone 149 Gludios
            # from game_state), _find_and_travel_hunting_zone() will detect the
            # current zone isn't a hunting ground and travel to the best available one.
            # It returns immediately if current zone is already a valid hunting ground.
            if self.combat_state != 'TRAVELING':
                await self._find_and_travel_hunting_zone()
            # Critical-start recovery: if HP is below rest threshold, recover before entering combat
            # (Prevents low-HP characters from dying immediately on connect)
            # Use 5% buffer above threshold to catch borderline starts (e.g., 36% HP when threshold is 35%)
            # ONLY attempt recovery if we're not traveling — recovery commands (stop_attack,
            # auto-farm toggle, combat:rest) are all rejected by the server while traveling.
            # The combat loop's _check_rest_needed handles low-HP recovery after arrival.
            if self.combat_state != 'TRAVELING':
                hp_pct = self.hp / max(self.max_hp, 1)
                recovery_threshold = self.rest_hp_threshold + 0.05
                if hp_pct < recovery_threshold:
                    self.analytics.log(f"[{self.name}] HP critically low ({hp_pct:.0%}) — recovering before combat")
                    await self._recover_before_combat()

        # Pre-seed: if we're in a hunting zone with 0 monsters, do an initial
        # auto-farm toggle to seed monsters before the combat loop starts.
        # Without this, characters sit IDLE for 60s until the tick-based reseed fires.
        # No time guard needed — enable_combat() prevents re-entry (line 1217)
        # and the other conditions (hunting zone match, no monsters) are sufficient.
        # Note: pre-seed also fires from the combat loop when the character arrives
        # at the hunting zone after travel (see _combat_tick near line 1720).
        if (self._hunting_zone_id is not None
                and self.current_zone_id == self._hunting_zone_id
                and not self.monsters
                and not self.is_dead
                and self.hp > 0
                and not self.is_in_party
                and not self.is_autofarming):
            self.analytics.log(f"[{self.name}] Pre-seeding monsters before combat loop...")
            await self._reseed_monsters()

        self.combat_enabled = True
        if self.combat_state != 'TRAVELING':
            self.combat_state = 'IDLE'
        if not self._combat_task or self._combat_task.done():
            self._combat_task = asyncio.create_task(self._combat_loop())
            self.analytics.log(f"[{self.name}] Combat AI enabled ({self.role})")

    async def disable_combat(self):
        """Disable the manual combat AI loop."""
        self.combat_enabled = False
        if self._combat_task and not self._combat_task.done():
            self._combat_task.cancel()
            self._combat_task = None
        self.analytics.log(f"[{self.name}] Combat AI disabled")

    async def _combat_loop(self):
        """Main combat AI loop — simple 300ms tick rate during combat.
        Attack speed is read from the API by _refresh_stats() but has no
        bearing on the decision loop — all decisions are event-driven."""
        self._last_stats_refresh = time.time()
        while self._keep_running and self.connected and self.combat_enabled:
            try:
                await self._combat_tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.analytics.track_error(self.name, f"Combat tick: {e}")
            # Refresh stats every 30s wall-clock to pick up gear/upgrade changes
            if time.time() - self._last_stats_refresh > 30.0:
                self._last_stats_refresh = time.time()
                await self._refresh_stats()
            # Adaptive tick rate: during combat, sleep until the next action
            # is available instead of busy-looping at 200ms. This saves ~60-70%
            # of wasted ticks when waiting for skill cast+block to complete.
            # When _next_action_time is set (from _use_best_skill), we sleep
            # until just before the block expires so we can fire immediately.
            # Fallback to 200ms when no next_action_time is scheduled.
            if self.combat_state in ('FIGHTING', 'TARGETING'):
                now = time.time()
                if self._next_action_time > now:
                    # Cap at 1s to keep HP/death/monster checks responsive
                    await asyncio.sleep(min(self._next_action_time - now, 1.0))
                else:
                    await asyncio.sleep(0.2)
            else:
                await asyncio.sleep(1.0)

    async def _refresh_stats(self):
        """Refresh character stats from API to pick up gear/upgrade changes."""
        try:
            stats = self.fetch_stats()
            if stats:
                speed = stats.get('attackSpeedMs')
                if speed:
                    self.attack_speed_ms = speed
        except Exception:
            pass

    async def _combat_tick(self):
        """Single combat AI tick — handles death, rest, then role-specific fighting.
        Pure manual — no auto-farm. Monsters arrive via combat:monster_spawned events."""
        async with self._combat_lock:
            # Death check — respawn then initiate travel back to hunting zone
            if self.is_dead:
                await self._respawn_if_dead()
                return

            self._clean_monsters()

            # Preemptive reseed: when 1 monster remains, start respawning
            # while still fighting it. Overlaps spawn downtime with combat —
            # new monsters arrive as the last one dies instead of waiting
            # 12s+ after all monsters are gone.
            # Preemptive reseed skipped in party mode — coordinator handles it
            if not self.is_in_party and (len(self.monsters) == 1
                    and self.current_zone_id == self._hunting_zone_id
                    and not self.is_dead and self.hp > 0
                    and time.time() - self._last_seed_time > (15 if self._last_reseed_delta > 0 else 25)):
                hp_ok = self.hp / max(self.max_hp, 1) >= self.rest_hp_target * 0.8
                if hp_ok:
                    await self._reseed_monsters()
                    # After reseed, continue to fight whatever we have
                    self._clean_monsters()

            # If no monsters, check if we need to travel back after respawn
            # CRITICAL: Only set IDLE if NOT TRAVELING — the travel guard on line 1028
            # is a second check, but combat_state must not be clobbered here.
            if not self.monsters:
                # After respawn we might be in town — travel back to hunting zone
                if self.current_zone_id == 1:
                    # In town — use reachability-aware zone finder with backoff
                    if self.combat_state != 'TRAVELING' and time.time() > getattr(self, '_travel_backoff', 0):
                        await self._find_and_travel_hunting_zone()
                    # Even when travel attempts are on backoff or failed, check rest.
                    # A character stuck in town at 30% HP should recover HP/MP
                    # instead of sitting idle for 60+ seconds.
                    rested = await self._check_rest_needed()
                    return
                # City escape (zone 149): the zone finder is the ONLY way back —
                # _hunting_zone_id may be None after the travel error handler
                # cleared it, and without this call the char sits IDLE in the
                # city forever at full HP (observed 2026-08-04 manual run:
                # 9 min IDLE in Gludios with 0 monsters, 0 gold).
                if self.combat_state != 'TRAVELING':
                    zi_now = None
                    if self.world and self.world.zones:
                        zi_now = self.world.zones.get(self.current_zone_id)
                    if (zi_now and zi_now.zone_type == 'city') or not self._hunting_zone_id:
                        if time.time() > getattr(self, '_travel_backoff', 0):
                            await self._find_and_travel_hunting_zone()
                if self._hunting_zone_id and self.current_zone_id != self._hunting_zone_id:
                    # Travel timeout: if we've been stuck in TRAVELING past the
                    # travel timeout (90s for multi-hop), reset to IDLE so the
                    # next tick can re-evaluate the zone.
                    if self.combat_state == 'TRAVELING':
                        if getattr(self, '_travel_timeout', 0) > 0 and time.time() > self._travel_timeout:
                            self.combat_state = 'IDLE'
                            self._travel_timeout = 0
                            self.analytics.log(f"[{self.name}] Travel timeout expired — resetting travel state")
                        # Also detect stuck travel: if travel was sent but zone
                        # hasn't changed after 30s, the server likely accepted
                        # the command but will never complete it (silent failure,
                        # broken route). Reset so the next tick re-evaluates.
                        elif (getattr(self, '_travel_sent_at', 0) > 0
                              and time.time() - self._travel_sent_at > 30
                              and self.current_zone_id == self._zone_at_travel_start):
                            self.combat_state = 'IDLE'
                            self._travel_timeout = 0
                            self._travel_sent_at = 0
                            self.analytics.log(f"[{self.name}] Travel stuck for 30s — resetting to IDLE")
                        return
                    if self.combat_state != 'TRAVELING':
                        # _travel_to_hunting_zone handles setting combat_state
                        await self._travel_to_hunting_zone()
                    return
                # Even with no monsters, check if we need rest (low HP/MP from previous fight)
                if self.combat_state != 'TRAVELING':
                    rested = await self._check_rest_needed()
                    if rested:
                        return  # Don't set IDLE if we're now resting
                # Re-seed monsters if we're in a hunting zone with 0 monsters
                # Server doesn't spawn monsters without recent auto-farm activity.
                # Reseed skipped in party mode — coordinator handles it
                if self.is_in_party:
                    pass
                elif self.combat_state != 'TRAVELING':
                    if (self.current_zone_id == self._hunting_zone_id
                            and not self.is_dead and self.hp > 0):
                        now = time.time()
                        # Adaptive reseed interval: base 10s, extend by 10s per failure.
                        # This was 20+count*20 but that took 60s for 2 reseeds in 60s tests —
                        # zone surf (3 failures) never triggered. 10+count*10 gives 10,20,30s
                        # intervals so zone surf fires within a 60s test window.
                        reseed_interval = 10 + self._failed_seed_count * 10
                        if now - self._last_seed_time > reseed_interval:
                            # Don't waste reseed while recovering — server won't spawn
                            # monsters for a low-HP character. Wait until HP is healthy.
                            hp_ok = self.hp / max(self.max_hp, 1) >= self.rest_hp_target * 0.8
                            if hp_ok:
                                await self._reseed_monsters()
                            return
                # If in a party, don't go IDLE — role handlers can use party leader's targets
                if self.is_in_party:
                    pass  # Fall through to role-specific handler
                else:
                    # Auto-farm fallback: if we've exhausted reseeds and can't find
                    # a better zone, enable auto-farm to at least produce some
                    # XP/gold instead of sitting IDLE. This handles characters
                    # stuck in dead zones with no reachable alternatives.
                    if (self.combat_state != 'TRAVELING'
                            and self.current_zone_id == self._hunting_zone_id
                            and not self.is_autofarming
                            and self._failed_seed_count >= 3
                            and not self.is_dead and self.hp > 0
                            and self.hp / max(self.max_hp, 1) >= self.rest_hp_target * 0.8):
                        self.analytics.log(f"[{self.name}] Dead zone — enabling auto-farm fallback")
                        await self.ws_send('start_autofarm', {})
                        self.combat_state = 'IDLE'
                        return
                    if self.combat_state != 'TRAVELING':
                        self.combat_state = 'IDLE'
                    return

            # Dispatch to role-specific handler
            if self.role == 'healer':
                await self._healer_tick()
            elif self.role == 'tank':
                await self._tank_tick()
            else:
                await self._dps_tick()

    # ── Shared combat utilities ──

    async def _respawn_if_dead(self) -> bool:
        """Respawn if dead. Returns True if we were dead."""
        if self.is_dead:
            if self.combat_state != 'DEAD':
                self.combat_state = 'DEAD'
                self.current_target = None
            # Don't spam — dynamic respawn interval based on server response
            if time.time() - self._last_respawn_time > self._get_respawn_interval():
                self._last_respawn_time = time.time()
                await self.ws_send('respawn', {})
            return True
        return False

    def _get_respawn_interval(self) -> float:
        """Exponential backoff for respawn retries.
        Starts at 3s, doubles each attempt, caps at 15s.
        Reset is automatic when _respawn_attempts gets cleared on revive."""
        count = getattr(self, '_respawn_attempts', 0)
        interval = min(3.0 * (2.0 ** count), 15.0)
        self._respawn_attempts = count + 1
        return interval

    # ── Empirical profiler methods ──

    def _get_measured_latency(self) -> float:
        """Return measured server latency in seconds.
        Uses average of empirical cast time variance as a proxy for
        round-trip latency. Defaults to 0.2s if no measurements taken."""
        all_times = list(self._empirical_cast_times.values())
        if not all_times or self._total_casts < 3:
            return 0.2
        # Latency ≈ 15% of the shortest measured cast (network overhead
        # is proportionally larger on fast casts)
        return min(all_times) * 0.15

    def _record_cast_completion(self, extra=None):
        """Record actual time a skill took to cast, based on server events.
        Fires via three paths:
        - combat:casting_complete (fighters/physical skills — reliable)
        - combat:heal_applied (healing skills — works if casterId matches)
        - combat:attack with magical/dot/skill damageType (wizard spells —
          proxy detection since wizard spells never fire casting_complete)
        After 2+ samples, uses empirical average + latency for block duration.
        Before convergence, falls back to API castTimeMs + latency."""
        if not self._pending_skill_sid or self._pending_skill_time <= 0:
            return
        sid = self._pending_skill_sid
        elapsed = time.time() - self._pending_skill_time
        if elapsed < 0.1 or elapsed > 30.0:
            self._pending_skill_sid = None
            self._pending_skill_time = 0
            return
        # Running average: 80% old / 20% new — adapts fast but smooth
        if sid in self._empirical_cast_times:
            prev = self._empirical_cast_times[sid]
            self._empirical_cast_times[sid] = prev * 0.8 + elapsed * 0.2
        else:
            self._empirical_cast_times[sid] = elapsed
        self._empirical_cast_samples[sid] = self._empirical_cast_samples.get(sid, 0) + 1
        # Track minimum inter-skill gap for empirical GCD
        if self._last_skill_success > 0:
            gap = time.time() - self._last_skill_success
            if self._empirical_gcd is None or gap < self._empirical_gcd:
                self._empirical_gcd = gap
        self._last_skill_success = time.time()
        # Save last skill ID before clearing — allows _handle_attack to attribute
        # damage that arrives after casting_complete (fighters) within a 5000ms window.
        self._last_skill_sid = sid
        self._last_skill_clear_time = time.time()
        # Cast is done — unblock immediately instead of extending block.
        # The original code set _skill_blocked_until to empirical+latency HERE,
        # which DOUBLED the block duration (initial block in _use_best_skill +
        # this extension) — causing 1-2s of dead time after every skill.
        # After casting_complete, the skill has finished casting. Cooldown is
        # tracked separately via skill_cooldowns. Unblock so the next tick can
        # immediately check if another skill is available.
        self._skill_blocked_until = 0
        self._next_action_time = 0
        self._pending_skill_sid = None
        self._pending_skill_time = 0

    async def _check_rest_needed(self) -> bool:
        """Rest if HP/MP too low. Returns True if resting.
        Stops auto-attack first so we can rest (can't rest while in combat)."""
        hp_pct = self.hp / max(self.max_hp, 1)
        mp_pct = self.mp / max(self.max_mp, 1)

        if self.is_resting:
            self.combat_state = 'RESTING'
            # If in combat while resting, check if we should cancel rest and fight.
            # But if HP is critically low (below rest_hp_target), KEEP RESTING even
            # with monsters — fighting at low HP produces 0 kills and just drains more
            # HP in a rest-cancel loop. Only stop resting when HP recovers enough to
            # fight effectively.
            if self.is_in_combat or self.monsters or self.is_autofarming:
                hp_pct = self.hp / max(self.max_hp, 1)
                # Keep resting if HP below target — ignore monsters until recovered.
                # Extend grace period to prevent rest-cancel loop.
                if hp_pct < self.rest_hp_target:
                    self._emergency_rest_until = time.time() + 5.0
                elif getattr(self, '_emergency_rest_until', 0) > time.time():
                    pass  # Stay resting during grace period
                else:
                    await self.ws_send('combat:cancel_rest', {})
                    self.is_resting = False
                    self.combat_state = 'IDLE'
                    return False
            # If we're taking damage while resting (monsters attacking), cancel rest
            # But not during emergency grace period — HP fluctuations are normal during recovery.
            # Also keep resting if HP is below rest_hp_target (same logic as above).
            if self.hp < self._hp_at_rest_start:
                hp_pct = self.hp / max(self.max_hp, 1)
                if hp_pct < self.rest_hp_target:
                    # HP loss while still below target — keep resting, extend grace
                    self._emergency_rest_until = time.time() + 5.0
                    self._hp_at_rest_start = self.hp  # Reset baseline
                elif getattr(self, '_emergency_rest_until', 0) > time.time():
                    self._hp_at_rest_start = self.hp  # Reset baseline during grace
                else:
                    await self.ws_send('combat:cancel_rest', {})
                    self.is_resting = False
                    self.combat_state = 'IDLE'
                    return False
            # Rest timeout — dynamic: estimate time to reach targets based on
            # how much HP/MP is missing. Uses empirical regen rates if available.
            missing_hp = self.max_hp * self.rest_hp_target - self.hp
            missing_mp = self.max_mp * self.rest_mp_target - self.mp
            # Sample regen every 5s to build empirical rates
            if self._regen_sample_start == 0:
                self._regen_sample_start = time.time()
                self._regen_sample_hp = self.hp
                self._regen_sample_mp = self.mp
            elif time.time() - self._regen_sample_start >= 5.0:
                elapsed = time.time() - self._regen_sample_start
                hp_rate = (self.hp - self._regen_sample_hp) / elapsed
                mp_rate = (self.mp - self._regen_sample_mp) / elapsed
                if hp_rate > 0 and hp_rate < self.max_hp * 0.5:  # Sanity
                    if self._empirical_hp_regen is None:
                        self._empirical_hp_regen = hp_rate
                    else:
                        self._empirical_hp_regen = self._empirical_hp_regen * 0.7 + hp_rate * 0.3
                if mp_rate > 0 and mp_rate < self.max_mp * 0.5:
                    if self._empirical_mp_regen is None:
                        self._empirical_mp_regen = mp_rate
                    else:
                        self._empirical_mp_regen = self._empirical_mp_regen * 0.7 + mp_rate * 0.3
                self._regen_samples += 1
                self._regen_sample_start = time.time()
                self._regen_sample_hp = self.hp
                self._regen_sample_mp = self.mp
            # Use empirical regen if we have samples, otherwise conservative estimate
            regen_hp_sec = self._empirical_hp_regen if self._empirical_hp_regen and self._regen_samples >= 2 else self.max_hp * 0.05
            regen_mp_sec = self._empirical_mp_regen if self._empirical_mp_regen and self._regen_samples >= 2 else self.max_mp * 0.03
            time_to_full = max(
                missing_hp / max(regen_hp_sec, 1),
                missing_mp / max(regen_mp_sec, 1)
            ) + 3.0  # 3s buffer
            rest_timeout = max(15.0, min(time_to_full, 60.0))
            if time.time() - self._rest_start_time > rest_timeout:
                await self.ws_send('combat:cancel_rest', {})
                self.is_resting = False
                self.combat_state = 'IDLE'
                return False
            if hp_pct >= self.rest_hp_target and mp_pct >= self.rest_mp_target:
                await self.ws_send('combat:cancel_rest', {})
                self.is_resting = False
                self.combat_state = 'IDLE'
            # Update HP baseline — if HP rose during rest, use new peak for damage detection
            if self.hp > self._hp_at_rest_start:
                self._hp_at_rest_start = self.hp
            return True

        # Can't rest while in combat
        if self.is_in_combat:
            # Force-exit combat state when it's stale — no monsters to fight.
            # The server keeps combat state active after monsters are cleared
            # (unreliable combat:stopped event), blocking rest even when idle.
            # Without this, HP slowly drains across reseed cycles without recovery:
            # reseed toggle spawns monsters → they damage the character → monsters
            # despawn but is_in_combat stays True → rest blocked → next reseed
            # continues draining HP → accumulates from 100% to 0% over minutes.
            # Use a 5% buffer above the threshold to pre-empt the 15-25% dead zone:
            # at 26% HP the check `26% < 25%` fails and the character keeps fighting
            # until 24%, then force-exits but can't complete rest before dying.
            hp_buffer = self.rest_hp_threshold + 0.05
            # When monsters are alive, only HP matters — low MP is fine during
            # combat (the skill rotation already skips skills with insufficient
            # MP). Force-exiting combat to rest at 23% MP while fighting 2
            # monsters wastes 15s in the retry loop for zero benefit.
            if self.monsters:
                # MP emergency: when MP is critically low (below half of rest_mp_threshold),
                # the character can't cast skills — auto-attack only. Force-exit combat
                # to rest and recover MP so skills become available again.
                emergency_mp = self.rest_mp_threshold * 0.5
                needs_rest = hp_pct < hp_buffer or mp_pct < emergency_mp
            else:
                needs_rest = hp_pct < hp_buffer or mp_pct < self.rest_mp_threshold
            if not self.monsters:
                # Stale combat state — no active threat. Only force-exit AND
                # rest-try if HP/MP is actually below threshold. At high HP the
                # rest is unnecessary and the retry loop wastes 15s of potential
                # combat time. Just clear the stale is_in_combat flag and go.
                if needs_rest:
                    # SHORT path: no monsters means no active threat. Skip the
                    # auto-farm toggle dance (8.5s+) and just stop_attack, wait
                    # briefly, and try rest. The long path was designed for stale
                    # combat state where the server needs time to expire its
                    # combat timer, but when a new monster spawns during that
                    # 8.5s window (from reseed or party activity), the character
                    # stands still taking damage with no way to defend.
                    await self.ws_send('combat:stop_attack', {})
                    self._target_attack_initiated = False
                    await asyncio.sleep(2.0)
                    self.is_in_combat = False
                    self._rest_blocked_until = 0
                    self._emergency_rest_until = time.time() + 25.0
                    # Try rest immediately — short path keeps critical-low-HP
                    # chars from dying while the long 8.5s path processes.
                    self._last_rest_attempt = time.time()
                    await self.ws_send('combat:rest', {})
                    self.is_resting = True
                    self._hp_at_rest_start = self.hp
                    self._rest_start_time = time.time()
                    self.combat_state = 'RESTING'
                    await asyncio.sleep(0.5)
                    if self.is_resting:
                        self._emergency_rest_until = time.time() + 20.0
                        return True
                    # Short path failed — fall through to long retry below
                else:
                    self.is_in_combat = False
                    return False
            if needs_rest:
                # Always send stop_attack to server — even when _target_attack_initiated
                # is False, the server may have combat active from auto-farm (reseed
                # toggle). Without this, server rejects combat:rest because it still
                # thinks the character is in combat.
                await self.ws_send('combat:stop_attack', {})
                self._target_attack_initiated = False
                await asyncio.sleep(1.0)
                # Use start/stop auto-farm with party-clearing pattern (same as
                # _reseed_monsters). Raw toggle_autofarm can be silently rejected if
                # the server has stale party state (pitfall #41), leaving combat
                # state intact and blocking rest. By using start_autofarm + checking
                # is_autofarming, we detect rejection and clear the party first.
                await self.start_autofarm()
                await asyncio.sleep(0.5)
                if not self.is_autofarming:
                    # Server-side party state blocks auto-farm — leave party and retry
                    self.is_in_party = False
                    self.party_members = {}
                    await self.ws_send('party:leave', {})
                    await asyncio.sleep(3)
                    await self.start_autofarm()
                    await asyncio.sleep(0.5)
                await self.stop_autofarm()
                # The auto-farm toggle re-entered combat state on the server.
                # Send another stop_attack to clear it and start the combat
                # cooldown timer fresh. Then wait long enough for the server's
                # combat timer to expire (~6-10s from last action).
                await self.ws_send('combat:stop_attack', {})
                await asyncio.sleep(7.0)  # ~8.5s total from first stop_attack

                self.is_in_combat = False
                self.is_autofarming = False
                self.monsters = []  # Clear monsters we can't fight — prevents rest-cancel loop
                self._rest_blocked_until = 0  # Reset backoff after force-exit
                # Set emergency grace BEFORE retry loop so the error handler
                # skips error tracking AND backoff for rest rejections during
                # retries. Without this, each failed retry adds an analytics
                # error and the 10s backoff at line 1944 blocks retries even
                # during the grace window (since _emergency_rest_until was only
                # set on rest success, which never happens if retries all fail).
                self._emergency_rest_until = time.time() + 25.0

                # Try rest once — the combat timer has had ~8.5s to expire.
                self._last_rest_attempt = time.time()
                await self.ws_send('combat:rest', {})
                self.is_resting = True
                self._hp_at_rest_start = self.hp
                self._rest_start_time = time.time()
                self.combat_state = 'RESTING'
                await asyncio.sleep(0.5)
                if self.is_resting:
                    # Rest accepted! Set emergency grace to cover the
                    # rest cycle (reject combat:start that would cancel it).
                    self._emergency_rest_until = time.time() + 20.0
                    return True

                # First attempt failed — server timer may be longer than 8.5s.
                # Retry every 2s for 10s. The emergency grace period covers
                # all retries so no errors are tracked for expected rejections.
                retry_end = time.time() + 10.0
                while time.time() < retry_end:
                    await asyncio.sleep(2.0)
                    self._last_rest_attempt = time.time()
                    await self.ws_send('combat:rest', {})
                    self.is_resting = True
                    self._hp_at_rest_start = self.hp
                    self._rest_start_time = time.time()
                    self.combat_state = 'RESTING'
                    await asyncio.sleep(0.5)
                    if self.is_resting:
                        self._emergency_rest_until = time.time() + 20.0
                        return True

                # 10s retry timeout — server never accepted rest. Set backoff so
                # subsequent ticks don't spam retries immediately. Emergency grace
                # is still active for ~7s (25 - 8.5 - 10), so the backoff guard
                # at line 1949 will skip the backoff and allow an immediate retry.
                self._rest_blocked_until = time.time() + 10.0
                return False
            else:
                return False
        # Don't retry rest too soon after a "cannot rest while in combat" rejection
        if getattr(self, '_rest_blocked_until', 0) > time.time():
            # During the emergency grace period (after force-exit), skip the backoff
            # so we can retry rest immediately. The force-exit cleared local combat
            # state but the server rejected rest — another try after the server
            # processes the stop_attack should succeed.
            if getattr(self, '_emergency_rest_until', 0) <= time.time():
                return False

        # Don't rest mid-combat unless below rest threshold
        # The role handlers call _check_rest_needed before checking monsters,
        # so without this guard chars try to rest while monsters are alive,
        # get rejected with "cannot rest while in combat", cycle error+backoff.
        # When monsters are cleared, _combat_tick handles rest at line 1339.
        if self.monsters:
            # When monsters are alive, low MP is normally fine for HP-based classes,
            # but if MP is critically low (below half of rest_mp_threshold), the
            # character can't cast skills — only auto-attack. Force rest to recover
            # MP so skills become available again.
            emergency_mp = self.rest_mp_threshold * 0.5
            if hp_pct >= self.rest_hp_threshold and mp_pct >= emergency_mp:
                return False
        else:
            # No monsters: use a higher threshold to ensure combat-readiness.
            # When returning from travel at low HP, the rest_hp_threshold (0.25)
            # is too low — characters arrive at 30% HP, 30% > 25% means rest is
            # skipped, and with no monsters they sit IDLE until passive regen
            # slowly brings HP up. Use rest_hp_target * 0.8 as the effective
            # rest threshold when idle — ensures characters are combat-ready
            # when monsters arrive.
            idle_hp_threshold = self.rest_hp_target * 0.8
            idle_mp_threshold = self.rest_mp_target * 0.8
            if hp_pct >= idle_hp_threshold and mp_pct >= idle_mp_threshold:
                return False
        # Rate-limit rest retries: minimum 2s between attempts.
        # After force-exit (stale combat state cleared locally), the server
        # may still consider the character in combat. A 200ms retry storm
        # produces 25+ rest rejections in 5s (all wasted). A 2s interval
        # gives the server time to process combat exit before accepting rest.
        if time.time() - getattr(self, '_last_rest_attempt', 0) < 2.0:
            return False

        # When no monsters, use idle thresholds for rest initiation.
        # Default to normal thresholds for the monsters case.
        effective_hp_threshold = self.rest_hp_threshold
        effective_mp_threshold = self.rest_mp_threshold
        if not self.monsters:
            effective_hp_threshold = self.rest_hp_target * 0.8
            effective_mp_threshold = self.rest_mp_target * 0.8

        if hp_pct < effective_hp_threshold or mp_pct < effective_mp_threshold:
            if not self.is_resting:
                # Record attempt time for rate-limiting
                self._last_rest_attempt = time.time()
                # Stop auto-attack first (can't rest while in combat)
                if self._target_attack_initiated:
                    await self.ws_send('combat:stop_attack', {})
                    self._target_attack_initiated = False
                    await asyncio.sleep(0.3)
                # Set emergency grace before sending rest — if the server rejects
                # with "not resting", the error handler will skip tracking the
                # error (expected rejection while server combat timer expires).
                # Without this, every rejected rest from the simple path adds to
                # the error count and sets a backoff.
                self._emergency_rest_until = time.time() + 15.0
                await self.ws_send('combat:rest', {})
                self.is_resting = True
                self._hp_at_rest_start = self.hp  # Track HP for damage detection
                self._rest_start_time = time.time()  # Track duration for timeout
                self.combat_state = 'RESTING'
            return True
        return False

    def _clean_monsters(self):
        """Remove dead and stale monsters from list."""
        now = time.time()
        fresh = []
        had_current = False
        for m in self.monsters:
            if m.get('hp', 0) <= 0:
                continue  # Dead
            # Remove stale entries (>60s old) — monster despawned but no death event
            spawn_time = m.get('_spawned_at', 0)
            if spawn_time > 0 and now - spawn_time > 60:
                if self.current_target and self.current_target.get('id') == m.get('id'):
                    had_current = True
                continue
            # HP stall: if server stopped updating HP for 10s, monster is likely
            # dead or despawned (missed death event, another player killed it,
            # or we were disconnected from the update stream). Clear it so we
            # don't waste skills on a ghost that will never die locally.
            last_hp = m.get('_last_hp_update', 0)
            if last_hp > 0 and now - last_hp > 10:
                if self.current_target and self.current_target.get('id') == m.get('id'):
                    had_current = True
                continue
            fresh.append(m)
        self.monsters = fresh
        if had_current:
            self.current_target = None
            self._target_attack_initiated = False

    async def _reseed_monsters(self):
        """Brief auto-farm toggle to trigger server monster spawning.
        Server only sends combat:monster_spawned events when auto-farm
        is or was recently active. Re-seed periodically to keep monsters flowing.
        Tracks consecutive failed re-seeds (0 monsters appeared) and triggers
        zone upgrade after 2 failures.
        In party mode, reseed is handled by the daemon (disband → seed → re-form)
        when partner_agents are set. Without partner_agents (e.g., test_char.py
        after daemon killed), the party state is stale — do solo reseed instead.
        This method is a no-op only in active daemon-controlled party mode."""
        if self.is_in_party and self.partner_agents and self.monsters:
            # Rate-limit the spam — only log every 30s when in party mode
            last_log = getattr(self, '_last_party_reseed_log', 0)
            if time.time() - last_log > 30:
                self.analytics.log(f"[{self.name}] Party mode: reseed handled by coordinator ({len(self.monsters)} monsters remain)")
                self._last_party_reseed_log = time.time()
            return

        old_count = len(self.monsters)
        self.analytics.log(f"[{self.name}] Re-seeding monsters (zone {self.current_zone_id})...")
        await self.start_autofarm()
        # Wait briefly to see if auto-farm was accepted
        await asyncio.sleep(0.5)
        if not self.is_autofarming:
            # Auto-farm was rejected (likely server-side party state not on client).
            # Leave party and retry — wait for server confirmation.
            self.analytics.log(f"[{self.name}] Auto-farm rejected — leaving stale party...")
            self.is_in_party = False  # Clear local state so reseed loop doesn't skip
            self.party_members = {}
            await self.ws_send('party:leave', {})
            await asyncio.sleep(3)  # Give server time to process party:leave
            self.analytics.log(f"[{self.name}] Retrying auto-farm after party leave...")
            await self.start_autofarm()
            await asyncio.sleep(0.5)
        # Dynamic reseed: check monsters every 2s, stop early when we have enough
        # Reduces downtime from fixed 20s to as little as 2s if monsters appear quickly
        # Set to 20s based on empirical data: 12s produced 0 monsters at 08:25 AM
        # (Tick 53 correction from Tick 52c reduction). 20s reliably produces 2-3
        # monsters in moderate-activity zones. Dynamic early exit (>=2 monsters)
        # minimizes waste in active zones with existing population.
        max_wait = 20
        check_interval = 2
        waited = 0
        while waited < max_wait:
            await asyncio.sleep(check_interval)
            waited += check_interval
            if len(self.monsters) >= 2:
                break
        await self.stop_autofarm()
        self.is_autofarming = False
        await asyncio.sleep(0.5)
        # Phase 1: stop attack — clear current target engagement
        self._target_attack_initiated = False
        await self.ws_send('combat:stop_attack', {})
        await asyncio.sleep(1.0)
        # Phase 2: if no monsters appeared, the auto-farm toggle left server in
        # combat state (sends combat:start WS events). This overrides the IDLE
        # state set by _combat_tick, keeping the character in FIGHTING with 0
        # monsters — causing HP drain from 100% → 26% over 60s (outdated 2.0s
        # sleep alone was insufficient — Tick 34/46 force-exit pattern needed).
        if len(self.monsters) == 0:
            await self.start_autofarm()
            await asyncio.sleep(0.5)
            if not self.is_autofarming:
                self.is_in_party = False
                self.party_members = {}
                await self.ws_send('party:leave', {})
                await asyncio.sleep(3)
                await self.start_autofarm()
                await asyncio.sleep(0.5)
            await self.stop_autofarm()
            await asyncio.sleep(0.5)
            # Phase 3: the toggle re-entered combat — send second stop_attack
            # and wait for the server's ~6-10s combat cooldown to expire.
            await self.ws_send('combat:stop_attack', {})
            await asyncio.sleep(7.0)
            self.is_in_combat = False
            self.is_autofarming = False
            self._rest_blocked_until = 0
        else:
            # Monsters appeared — light cleanup, no force-exit needed
            self.is_in_combat = False
            await asyncio.sleep(1.0)
        new_count = len(self.monsters)
        self.analytics.log(f"[{self.name}] Re-seed complete — {new_count} monsters (was {old_count})")

        # Update last_seed_time at COMPLETION, not at start — prevents the
        # preemptive reseed guard (line 1728) from immediately firing another
        # reseed when the first one just finished. Without this, a reseed that
        # completed at time T sets _last_seed_time = T-20s, and the guard
        # sees 20 > 15 = True, triggering a back-to-back 20s reseed.
        self._last_seed_time = time.time()

        # Reset attack flag when new monsters appear — they have fresh IDs
        # and need select_target before combat:attack will work
        if new_count > 0:
            self._target_attack_initiated = False

        # Track consecutive failed re-seeds (delta-based).
        # Old code used `new_count == 0 and old_count == 0` which broke when
        # a single persistent monster stayed alive across reseeds — the counter
        # kept resetting (never reached 3) and zone surf never fired.
        # Now uses delta: if reseed didn't ADD any monsters (delta <= 0), it's
        # a failed reseed regardless of residual monster count.
        delta = new_count - old_count
        if delta <= 0:
            self._failed_seed_count += 1
            # Upgrade zone after 2 consecutive failures AND cooldown expired.
            # Reduced from 3 in Tick 47 because 3×10+20+30=60s was too slow for 60s
            # test windows — characters in dead zones (52715, 53) wasted 45-60s
            # IDLE before surfing. With threshold 2: 10+20=30s → surf within 60s test.
            # One failure is normal in busy zones — other players clear spawns temporarily.
            # Two consecutive failures reliably indicates a dead zone.
            if self._failed_seed_count >= 2:
                cooldown_remaining = self._zone_backoff_until - time.time()
                if cooldown_remaining > 0:
                    self.analytics.log(f"[{self.name}] Zone backoff ({cooldown_remaining:.0f}s)")
                else:
                    self.analytics.log(f"[{self.name}] {self._failed_seed_count} dead re-seeds — surfing to next zone")
                    self._prior_hunting_zone = self._hunting_zone_id
                    await self._surf_to_next_zone()
                    self._zone_backoff_until = time.time() + 60  # Re-try in 60s
        else:
            self._failed_seed_count = 0
            self._surf_visited.clear()  # Reset surf tracking — we're productive
            # Record this zone as productive (per-character + global)
            self._zone_last_productive[self._hunting_zone_id] = time.time()
            CharacterAgent._global_zone_productivity[self._hunting_zone_id] = time.time()
        # Track reseed effectiveness for preemptive reseed guard
        self._last_reseed_delta = delta

        # Fail-back: new zone also empty after surf — immediately surf to next
        if new_count == 0 and self._prior_hunting_zone is not None:
            self.analytics.log(f"[{self.name}] Surf zone {self._hunting_zone_id} also empty — surfing again")
            # Add to visited so next surf doesn't pick the same zone
            self._surf_visited.add(self._hunting_zone_id)
            self._prior_hunting_zone = None
            self._failed_seed_count = 0
            self._zone_backoff_until = 0
            await self._surf_to_next_zone()

    async def _attack_target(self, target_id: int):
        """Send attack command — game auto-attacks continuously once started.
        Only send once per target; after that, just use skills.
        Must call select_target first (required by server protocol).
        Also fires the first skill immediately instead of waiting for next tick,
        saving ~200ms per target switch."""
        if self._target_attack_initiated:
            return
        await self.ws_send('combat:select_target', {'targetId': target_id, 'targetType': 'monster'})
        await asyncio.sleep(0.1)
        await self.ws_send('combat:attack', {
            'targetId': target_id,
            'targetType': 'monster'
        })
        self._target_attack_initiated = True
        # Fire first skill immediately — don't wait 200ms for next tick
        await self._use_best_skill(target_id)

    def _save_hunting_zone(self, zone_id: int):
        """Remember this as our hunting zone — skip town/respawn zones (id=1).
        Only accepts numeric ids — the server sometimes sends zone NAME strings
        (e.g. "Gludios") in game_state/travel payloads; saving those breaks
        every zone comparison (2026-08-04 travel-loop root cause)."""
        if isinstance(zone_id, str):
            if zone_id.isdigit():
                zone_id = int(zone_id)
            else:
                return
        if zone_id and zone_id != 1:
            self._hunting_zone_id = zone_id

    async def _travel_to_hunting_zone(self):
        """If we're not in a hunting zone and we know one, travel back.
        Force-exits combat state before traveling — server rejects travel
        if character is in combat."""
        if not self._hunting_zone_id:
            self.analytics.log(f"[{self.name}] No hunting zone known, staying put")
            return
        if self.current_zone_id == self._hunting_zone_id:
            return  # Already there
        if self.combat_state == 'TRAVELING':
            # Check if travel timeout expired — if we've been stuck for 30s,
            # reset to IDLE so the next tick can re-evaluate the zone or retry.
            if getattr(self, '_travel_timeout', 0) > 0 and time.time() > self._travel_timeout:
                self.combat_state = 'IDLE'
                self._travel_timeout = 0
                self.analytics.log(f"[{self.name}] Travel timeout expired — resetting travel state")
            return  # Already traveling (error handler will reset if rejected)
        # Backoff: if travel was recently rejected, wait before retrying
        if time.time() < getattr(self, '_travel_backoff', 0):
            return

        # Stop combat before traveling — server rejects travel if in combat.
        # Always send stop_attack even if client flags are False — the server
        # may have a stale combat state from a previous session (daemon crash).
        await self.ws_send('combat:stop_attack', {})
        self._target_attack_initiated = False
        self.current_target = None
        self.is_in_combat = False
        await asyncio.sleep(2.0)

        # Cancel rest RIGHT BEFORE sending travel, not at the start of this method.
        # Old code cancelled rest first, then waited 2s for stop_attack — during that
        # wait, the server's idle AI re-enters rest (no combat + idle = auto-rest).
        # By cancelling rest last, we close the window for server re-entry to ~0.3s.
        # However, if the server's REST state is persistent (not cleared by cancel_rest
        # when character isn't actively resting), we first ENTER rest, then CANCEL it.
        # This ensures the rest state is properly toggled and cleared before travel.
        # Suppress "not resting" errors during this toggle — the server may respond with
        # "not resting" if the character is already traveling (harmless).
        self._emergency_rest_until = time.time() + 10.0
        await self.ws_send('combat:rest', {})
        await asyncio.sleep(0.3)
        await self.ws_send('combat:cancel_rest', {})
        self.is_resting = False
        await asyncio.sleep(0.3)

        # Also leave party if stale — party state blocks travel too
        if self.is_in_party and not self.partner_agents:
            await self.ws_send('party:leave', {})
            self.is_in_party = False
            self.party_members = {}
            await asyncio.sleep(2.0)

        self.analytics.log(f"[{self.name}] Traveling to {self._hunting_zone_id}...")
        self.combat_state = 'TRAVELING'
        # Safety timeout: multi-hop travel (zone 149 → 64188) takes ~42s.
        # Single-hop is 3-10s. Use 90s timeout to cover worst-case multi-hop.
        self._travel_timeout = time.time() + 90.0
        # Stuck travel detection: record when and where we sent travel.
        # If zone hasn't changed in 30s, the server silently failed.
        self._travel_sent_at = time.time()
        self._zone_at_travel_start = self.current_zone_id
        await self._send_next_travel_hop()
        # Reset attack state for fresh targets when we arrive
        self._target_attack_initiated = False
        self.current_target = None

    async def _send_next_travel_hop(self):
        """Send the next single-hop travel command along the BFS path.
        The combat tick calls _travel_to_hunting_zone after each travel_complete,
        which calls this method again with the remaining path — creating a
        natural multi-hop loop. Uses WorldData if available, falls back to
        direct travel (single hop) if pathfinding isn't initialized."""
        target = self._hunting_zone_id
        if not target or not self.current_zone_id:
            return
        # Lazily init WorldData for multi-hop pathfinding
        if self.world is None:
            try:
                from grimeage_agent import WorldData
                self.world = WorldData(self.rest)
                self.world.load()
            except Exception as e:
                self.analytics.log(f"[{self.name}] WorldData init failed ({e}) — using direct travel")
                self.world = None
        if self.world and self.world._loaded:
            path = self.world.find_path(self.current_zone_id, target)
            if path and len(path) > 1:
                next_hop = path[1]  # First step from current position
                if len(path) > 2:
                    self.analytics.log(f"[{self.name}] Multi-hop travel: {self.current_zone_id} → {next_hop} ({len(path)-1} hops to {target})")
                await self.ws_send('start_travel', {'path': [next_hop]})
                return
        # Fallback: direct single-hop travel
        self.analytics.log(f"[{self.name}] Direct travel to {target}...")
        await self.ws_send('start_travel', {'path': [target]})

    async def _recover_before_combat(self) -> bool:
        """Critical-start recovery: rest/regen to safe HP/MP before engaging combat.
        Used when character connects with HP below rest threshold.
        Uses force-exit pattern (stop_attack → party:leave → auto-farm toggle)
        to break server-side combat state, then tries rest with retry loop."""
        hp_pct = self.hp / max(self.max_hp, 1)
        self.analytics.log(f"[{self.name}] Critical HP ({hp_pct:.0%}) — recovery phase...")
        recovered = False

        # Set emergency grace immediately — prevents "not resting" error tracking
        # during retry loop (expected rest rejections while server combat timer expires)
        self._emergency_rest_until = time.time() + 30.0

        # Step 1: Stop attack to break combat state
        await self.ws_send('combat:stop_attack', {})
        self._target_attack_initiated = False
        await asyncio.sleep(1.0)

        # Step 2: Try the full force-exit pattern if initial stop_attack wasn't
        # enough (server may have stale auto-farm or invisible party state).
        # Use auto-farm toggle with party-clearing fallback.
        await self.start_autofarm()
        await asyncio.sleep(0.5)
        if not self.is_autofarming:
            # Server-side party state blocks auto-farm — leave party and retry
            self.is_in_party = False
            self.party_members = {}
            await self.ws_send('party:leave', {})
            await asyncio.sleep(3)
            await self.start_autofarm()
            await asyncio.sleep(0.5)
        await self.stop_autofarm()
        await self.ws_send('combat:stop_attack', {})
        await asyncio.sleep(7.0)  # Server combat timer needs ~6-10s

        self.is_in_combat = False
        self.is_autofarming = False
        self.monsters = []
        self._rest_blocked_until = 0

        # Step 3: Try rest with retry loop (same pattern as _check_rest_needed force-exit)
        for attempt in range(8):  # ~20s total with 2s sleep + 0.5s check
            if self.is_dead:
                break
            self._last_rest_attempt = time.time()
            await self.ws_send('combat:rest', {})
            self.is_resting = True
            self._hp_at_rest_start = self.hp
            self._rest_start_time = time.time()
            self.combat_state = 'RESTING'
            await asyncio.sleep(0.5)
            if self.is_resting:
                # Rest accepted! Now monitor recovery
                wait_start = time.time()
                while time.time() - wait_start < 15.0:  # Max 15s rest window
                    await asyncio.sleep(1)
                    if self.is_dead:
                        break
                    hp_pct = self.hp / max(self.max_hp, 1)
                    mp_pct = self.mp / max(self.max_mp, 1)
                    if hp_pct >= self.rest_hp_target and mp_pct >= self.rest_mp_target:
                        recovered = True
                        break
                    # If rest got interrupted (monsters attacked), retry the
                    # force-exit pattern from scratch — don't count this as success
                    if not self.is_resting:
                        break
                if recovered or self.is_dead:
                    break
                # Rest interrupted before reaching target — fall through to retry
                # Cancel rest cleanly before next attempt
                await self.ws_send('combat:cancel_rest', {})
                self.is_resting = False
                await asyncio.sleep(0.5)
                # Brief force-exit again if we have monsters now
                if self.monsters:
                    await self.ws_send('combat:stop_attack', {})
                    await asyncio.sleep(2.0)
                    await self.start_autofarm()
                    await asyncio.sleep(0.5)
                    await self.stop_autofarm()
                    await asyncio.sleep(3.0)
                    self.monsters = []
                    self.is_in_combat = False
            else:
                # Rest not accepted yet — extend grace and retry
                self._emergency_rest_until = time.time() + 30.0
                await asyncio.sleep(2.0)

        await self.ws_send('combat:cancel_rest', {})
        self.is_resting = False
        hp_pct = self.hp / max(self.max_hp, 1)
        mp_pct = self.mp / max(self.max_mp, 1)
        self.analytics.log(f"[{self.name}] Recovery done — HP:{hp_pct:.0%} MP:{mp_pct:.0%} "
                          f"{'✓ recovered' if recovered else '✗ interrupted'}")
        return recovered

    async def _surf_to_next_zone(self):
        """Cycle through reachable hunting zones to find one with activity.
        Instead of upgrading to a 'better' zone, visits all directly-connected
        hunting grounds round-robin. Skips zones that were dead recently (<300s).
        Falls back to find_better_hunting_zone if no zones available."""
        current = self.current_zone_id or self._hunting_zone_id
        try:
            map_data = self.rest.get('/api/world/map')
            if not isinstance(map_data, dict) or not map_data.get('zones'):
                return

            zones_info = {}
            for z in map_data['zones']:
                zid = z['id']
                zones_info[zid] = {
                    'name': z.get('name', f'Zone{zid}'),
                    'type': z.get('type', ''),
                    'level_min': z.get('levelRangeMin', 1),
                    'level_max': z.get('levelRangeMax', 99),
                }

            # Build directly-reachable hunting grounds from current zone
            connections = map_data.get('connections', [])
            reachable = set()
            for c in connections:
                if c.get('zoneAId') == current:
                    reachable.add(c['zoneBId'])
                elif c.get('zoneBId') == current:
                    reachable.add(c['zoneAId'])

            # Filter to hunting grounds suitable for our level
            # ENHANCED: Allow up to 5 levels above max if zone has recent global activity
            candidates = []
            now = time.time()
            for zid in reachable:
                if zid in self._zone_travel_blacklist:
                    continue  # Skip zones that failed travel
                # Skip the zone we're ACTUALLY standing in — current_zone_id may
                # be fresher than `current` (stale WS event), and surfing to your
                # own zone is a no-op that loops forever.
                if zid == self.current_zone_id:
                    continue
                info = zones_info.get(zid)
                if not info:
                    continue
                if info.get('type') != 'hunting_ground':
                    continue
                # Level check: strict within range, OR up to 5 above max if productive
                within_level = info['level_min'] <= self.level <= info['level_max']
                global_prod = CharacterAgent._global_zone_productivity.get(zid, 0)
                prod_active = (global_prod > 0 and now - global_prod < 300)
                slightly_above = (self.level > info['level_max'] and
                                  self.level - info['level_max'] <= 5 and
                                  prod_active)
                if not within_level and not slightly_above:
                    continue
                # Score: prefer zones that were productive recently
                last_ok = self._zone_last_productive.get(zid, 0)
                recency_score = 0
                if last_ok > 0 and now - last_ok < 300:
                    recency_score = 50  # Was productive within 5 min
                # Global productivity bonus — prefer zones active from any char
                if prod_active:
                    recency_score += 200  # Strong bonus for globally active zones
                # Penalty if above level range
                if slightly_above:
                    recency_score -= 20 * (self.level - info['level_max'])
                # Skip zones already visited in this surf cycle
                if zid in self._surf_visited:
                    recency_score -= 100  # Penalize
                candidates.append((-recency_score, zid, info['name']))

            if not candidates:
                # Try zone 149 (Gludios city hub) first — it connects to Lv21-24
                # zones like 64188 that aren't reachable from zone 1 or low-level
                # zones. This is the same pattern as _find_and_travel_hunting_zone's
                # zone 149 escape for town-stuck characters (Tick 65).
                if 149 not in self._zone_travel_blacklist:
                    self.analytics.log(f"[{self.name}] No alternative hunting zones reachable — trying zone 149 (Gludios hub)...")
                    self._surf_visited.clear()
                    self._hunting_zone_id = 149
                    self._last_seed_time = time.time() + 30
                    return
                self.analytics.log(f"[{self.name}] No alternative hunting zones reachable — all surf zones exhausted. Escaping to town...")
                # All surf candidates exhausted. Travel to zone 1 (town) to re-evaluate
                # from a position where more zones may be reachable (e.g., zone 1 → 44341).
                # The combat tick will call _find_and_travel_hunting_zone after arrival.
                self._surf_visited.clear()
                self._hunting_zone_id = 1  # Set to town zone
                self._last_seed_time = time.time() + 30  # Don't reseed in town
                return

            candidates.sort()
            best_id = candidates[0][1]
            best_name = candidates[0][2]

            # Exhaustion check: if the best candidate has been visited this
            # surf cycle AND has zero global productivity (or stale >300s),
            # all available zones are dead — escape to town to re-evaluate.
            # Prevents infinite cycling when only one candidate exists and
            # it's also a dead zone (e.g., ShieldBot: 52715 → 52844 only).
            best_visited = best_id in self._surf_visited
            global_prod = CharacterAgent._global_zone_productivity.get(best_id, 0)
            best_stale = (global_prod == 0 or time.time() - global_prod > 300)
            if best_visited and best_stale:
                # Try zone 149 first before escaping to town
                if 149 not in self._zone_travel_blacklist and self._hunting_zone_id != 149:
                    self.analytics.log(f"[{self.name}] Best candidate {best_id} unproductive — trying zone 149 (Gludios hub)...")
                    self._surf_visited.clear()
                    self._hunting_zone_id = 149
                    self._last_seed_time = time.time() + 30
                    return
                self.analytics.log(f"[{self.name}] Best candidate {best_id} already visited and unproductive — all zones exhausted. Escaping to town...")
                self._surf_visited.clear()
                self._hunting_zone_id = 1  # Town zone
                self._last_seed_time = time.time() + 30
                return

            self.analytics.log(f"[{self.name}] Surfing to {best_id} ({best_name})")
            self._surf_visited.add(self._hunting_zone_id)
            self._hunting_zone_id = best_id
            self._failed_seed_count = 0
            self._last_seed_time = 0  # Allow immediate reseed in new zone
        except Exception as e:
            self.analytics.track_error(self.name, f'zone surf: {e}')

    async def _find_better_hunting_zone(self):
        """When current hunting zone produces no monsters after 2+ re-seeds,
        search for a better zone using the server zones API.
        Finds hunting grounds with higher level range that cover the character's level
        and are reachable from the current zone. Updates _hunting_zone_id."""
        current = self._hunting_zone_id
        self.analytics.log(f"[{self.name}] Finding better zone (current: {current})...")
        try:
            map_data = self.rest.get('/api/world/map')
            if not isinstance(map_data, dict) or not map_data.get('zones'):
                return

            # Build zone info
            zones_info = {}
            for z in map_data['zones']:
                zid = z['id']
                zones_info[zid] = {
                    'name': z.get('name', f'Zone{zid}'),
                    'type': z.get('type', ''),
                    'level_min': z.get('levelRangeMin', 1),
                    'level_max': z.get('levelRangeMax', 99),
                }

            current_info = zones_info.get(current, {})
            current_min = current_info.get('level_min', 1)

            # Build set of zones directly connected to current zone
            # Server only supports single-hop travel via start_travel {'path': [dest]}
            connections = map_data.get('connections', [])
            directly_reachable = set()
            for c in connections:
                if c.get('zoneAId') == current:
                    directly_reachable.add(c['zoneBId'])
                elif c.get('zoneBId') == current:
                    directly_reachable.add(c['zoneAId'])

            # Find candidates: hunting grounds, not current zone, covers level
            # ENHANCED: Also allow zones up to 5 levels below char if productive
            now = time.time()
            candidates = []
            for zid, info in zones_info.items():
                if zid == current:
                    continue
                if info.get('type') != 'hunting_ground':
                    continue
                # Productivity bonus from global tracking
                last_prod = CharacterAgent._global_zone_productivity.get(zid, 0)
                prod_bonus = 500 if (last_prod > 0 and now - last_prod < 300) else 0
                within_level = info['level_min'] <= self.level <= info['level_max']
                slightly_above = (self.level > info['level_max'] and
                                  self.level - info['level_max'] <= 5 and
                                  prod_bonus > 0)
                if not within_level and not slightly_above:
                    continue
                # CRITICAL: Server only supports single-hop travel.
                # Only consider zones directly reachable from current zone.
                if zid not in directly_reachable:
                    continue
                if within_level:
                    # Prefer zones with higher level minimum (progression upward)
                    # Score: closeness to mid-level range
                    score = (self.level - info['level_min']) + (info['level_max'] - self.level)
                    # Bonus for higher min level (graduating upward)
                    score -= (info['level_min'] - current_min) * 2
                    candidates.append((score - prod_bonus, zid, info['name']))
                elif slightly_above:
                    # Allow up to 5 levels above if productive
                    over_level = self.level - info['level_max']
                    score = 50 + over_level * 10
                    candidates.append((score - prod_bonus, zid, info['name']))

            if not candidates:
                self.analytics.log(f"[{self.name}] No alternative hunting zones for Lv{self.level}")
                self._failed_seed_count = 0  # Reset so we don't spam API
                return

            candidates.sort()
            best_id = candidates[0][1]
            best_name = candidates[0][2]
            self.analytics.log(f"[{self.name}] Better zone found: {best_id} ({best_name})")

            # Update hunting zone — combat tick will handle travel via _travel_to_hunting_zone()
            self._hunting_zone_id = best_id
            self._failed_seed_count = 0
            self.analytics.log(f"[{self.name}] Hunting zone updated to {best_id}")
        except Exception as e:
            self.analytics.track_error(self.name, f'find better zone: {e}')
            self._failed_seed_count = 0  # Reset to avoid infinite retries on error

    async def _find_and_travel_hunting_zone(self):
        '''Fetch zone map from REST and travel to best zone for level.
        Used when character connects in town with no known hunting zone.
        NOTE: The old guard (line 2073) returned immediately if current_zone_id
        wasn't town AND _hunting_zone_id was set. But _save_hunting_zone() can
        save non-hunting zones (e.g., city type=city like Zone 149 Gludios),
        causing the guard to silently skip zone validation. The inner early-exit
        at "Already in valid hunting zone" does the actual type check, so the
        outer guard is removed.'''
        # Town auto-farm backoff: if we're stuck in zone 1 and auto-farming,
        # don't waste time searching for hunting zones we can't reach.
        # Travel from zone 1 often fails even for directly-connected zones
        # (server-side respawn state or zone-level restrictions). Instead of
        # looping on failed travel attempts for the entire test window,
        # auto-farm in town where the character stays productive.
        if (self.current_zone_id == 1
                and getattr(self, '_town_auto_backoff', 0) > time.time()
                and self.is_autofarming):
            # Zone 149 routing override: before settling into 120s of town farming,
            # try to escape through Gludios city. Zone 149 is multi-hop reachable
            # from zone 1 and connects to Lv21-24 hunting grounds (e.g., 64188).
            # Dead-at-connect Lv23+ characters are stuck in zone 1 with all directly-
            # connected hunting grounds too low for their level and broken server-side
            # routing. Zone 149 is the only working escape path.
            if 149 not in self._zone_travel_blacklist:
                try:
                    if self.world is None:
                        from grimeage_agent import WorldData
                        self.world = WorldData(self.rest)
                        self.world.load()
                    self.analytics.log(f"[{self.name}] Town backoff active — attempting DIRECT zone 149 escape before farming")
                    self._hunting_zone_id = 149
                    if self.is_autofarming:
                        await self.ws_send('combat:toggle_autofarm', {})
                        self.is_autofarming = False
                        await asyncio.sleep(0.3)
                    # ⚠️ CRITICAL: Send DIRECT single-hop to 149, NOT via BFS path.
                    # _travel_to_hunting_zone → _send_next_travel_hop uses BFS which may
                    # route through a broken intermediate hop (e.g., 1→44280 doesn't exist).
                    # The error handler then blacklists 149 (the target) instead of the
                    # failed hop, permanently blocking future escape attempts even though
                    # 1→149 might have worked as a single hop. Direct single-hop avoids this.
                    await self.ws_send('start_travel', {'path': [149]})
                    self.combat_state = 'TRAVELING'
                    self._travel_timeout = time.time() + 90.0
                    self._travel_sent_at = time.time()
                    self._zone_at_travel_start = self.current_zone_id
                    self._target_attack_initiated = False
                    self.current_target = None
                    self._hunting_zone_id = None
                    # ⚠️ CRITICAL: 149 must be blacklisted HERE, not in the WS
                    # error handler (which runs async and reads _hunting_zone_id
                    # after we've already cleared it to None). Without this,
                    # 149 is never blacklisted and the escape retries on every tick.
                    self._zone_travel_blacklist.add(149)
                    return
                except Exception:
                    pass
                self._zone_travel_blacklist.add(149)
            return
        # In zone 1 with town backoff active but NOT auto-farming? Try zone 149
        # escape first (same as above — may be the first call after respawn when
        # auto-farm hasn't been toggled yet). If 149 fails or is blacklisted,
        # activate auto-farm and wait out the 120s backoff.
        # ⚠️ CRITICAL: combat:stopped WS event resets is_autofarming to False,
        # which causes this branch to re-enter on every tick and re-attempt
        # zone 149 escape (even though 149 is blacklisted). Track we've already
        # gone through this and skip re-entry when is_autofarming is False due
        # to the race condition from combat:stopped.
        if self.current_zone_id == 1 and getattr(self, '_town_auto_backoff', 0) > time.time():
            if 149 not in self._zone_travel_blacklist:
                try:
                    if self.world is None:
                        from grimeage_agent import WorldData
                        self.world = WorldData(self.rest)
                        self.world.load()
                    self.analytics.log(f"[{self.name}] Town backoff active (no auto-farm) — attempting DIRECT zone 149 escape")
                    self._hunting_zone_id = 149
                    # ⚠️ CRITICAL: Send DIRECT single-hop to 149, NOT via BFS path.
                    # Same reasoning as the auto-farming block above — BFS may route
                    # through a broken intermediate hop that doesn't actually exist.
                    await self.ws_send('start_travel', {'path': [149]})
                    self.combat_state = 'TRAVELING'
                    self._travel_timeout = time.time() + 90.0
                    self._travel_sent_at = time.time()
                    self._zone_at_travel_start = self.current_zone_id
                    self._target_attack_initiated = False
                    self.current_target = None
                    self._hunting_zone_id = None
                    # ⚠️ CRITICAL: 149 must be blacklisted HERE, not in the WS
                    # error handler (which runs async and reads _hunting_zone_id
                    # after we've already cleared it to None). Without this,
                    # 149 is never blacklisted and the escape retries on every tick.
                    self._zone_travel_blacklist.add(149)
                    return
                except Exception:
                    pass
                self._zone_travel_blacklist.add(149)
            # Only re-enable auto-farm if we haven't already been through
            # the 149 escape attempt AND auto-farm cycle. combat:stopped
            # resets is_autofarming asynchronously, causing an infinite
            # retry loop: enable auto-farm → combat:stopped → re-enter →
            # try 149 (blacklisted) → enable auto-farm → combat:stopped.
            # The _town_autofarm_attempted flag breaks this loop.
            if not getattr(self, '_town_autofarm_attempted', False):
                self._town_autofarm_attempted = True
                if not self.is_autofarming and not self.is_dead:
                    await self.ws_send('combat:toggle_autofarm', {})
                    self.is_autofarming = True
                    self.analytics.log(f"[{self.name}] Auto-farm enabled in zone 1 — waiting out {getattr(self, '_town_auto_backoff', 120) - time.time():.0f}s town backoff")
            return  # Skip zone search entirely while town backoff is active
        self.analytics.log(f"[{self.name}] Finding hunting zone for Lv{self.level}...")
        try:
            # Prefer the CACHED map (self._cached_map) — /api/world/map is slow
            # (1.4-4.4s) and flaky: when it returns None (observed 2026-08-04),
            # the whole block is skipped and the finder loops "Could not find
            # hunting zone" forever while the char sits IDLE. Cache successful
            # fetches; refresh at most once every 5 minutes.
            map_data = self._cached_map
            if map_data is None or time.time() - getattr(self, '_map_cached_at', 0) > 300:
                if self.world is not None and self.world.zones:
                    conns = []
                    for za, neighbors in self.world.adjacency.items():
                        for n in neighbors:
                            conns.append({'zoneAId': za, 'zoneBId': n.get('target_id')})
                    map_data = {'zones': [
                        {'id': zid, 'name': zi.name, 'type': zi.zone_type,
                         'levelRangeMin': zi.level_min, 'levelRangeMax': zi.level_max}
                        for zid, zi in self.world.zones.items()
                    ], 'connections': conns}
                else:
                    for _attempt in range(3):
                        map_data = self.rest.get('/api/world/map')
                        if isinstance(map_data, dict) and map_data.get('zones'):
                            break
                        await asyncio.sleep(1)
                if isinstance(map_data, dict) and map_data.get('zones'):
                    self._cached_map = map_data
                    self._map_cached_at = time.time()
                elif self._cached_map is not None:
                    # /api/world/map flaked (returned None) AND world not
                    # loaded — fall back to the LAST GOOD cache instead of
                    # dropping into the "Could not find hunting zone" loop
                    # (observed 2026-08-04 healer run: ~9 min stuck after the
                    # 5-min cache expired mid-run, map fetch returning None).
                    map_data = self._cached_map
            if isinstance(map_data, dict) and map_data.get('zones'):
                # Build zone info from the zones array (has correct types)
                zones_info = {}
                for z in map_data['zones']:
                    zid = z['id']
                    zones_info[zid] = {
                        'name': z.get('name', f'Zone{zid}'),
                        'type': z.get('type', ''),
                        'level_min': z.get('levelRangeMin', 1),
                        'level_max': z.get('levelRangeMax', 99),
                    }
                # CHECK: is current zone already a valid hunting ground?
                current = zones_info.get(self.current_zone_id)
                now = time.time()
                if current and current.get('type') == 'hunting_ground':
                    if current['level_min'] <= self.level <= current['level_max']:
                        self._hunting_zone_id = self.current_zone_id
                        self.analytics.log(f"[{self.name}] Already in valid hunting zone {self.current_zone_id} ({current['name']}) — staying put")
                        return
                    # Slightly above: allow staying if within 5 levels of zone max.
                    # Travel costs 15-45s of test time and risks landing in a dead
                    # zone. Better to fight in a slightly low-zone that's productive
                    # than waste half the test window traveling to a maybe-better zone.
                    slightly_above = (self.level > current['level_max'] and
                                      self.level - current['level_max'] <= 5)
                    if slightly_above:
                        last_prod = CharacterAgent._global_zone_productivity.get(self.current_zone_id, 0)
                        if last_prod > 0 and now - last_prod < 300:
                            self._hunting_zone_id = self.current_zone_id
                            self.analytics.log(f"[{self.name}] Staying in slightly-above-zone {self.current_zone_id} ({current['name']}, Lv{current['level_min']}-{current['level_max']}, Lv{self.level}) — recent activity detected")
                            return
                        # No recent activity data yet (cold start). Stay put anyway
                        # — the pre-seed + reseed will populate monster counts.
                        # Traveling to an identical-level zone is no better.
                        self._hunting_zone_id = self.current_zone_id
                        self.analytics.log(f"[{self.name}] Staying in slightly-above-zone {self.current_zone_id} ({current['name']}, Lv{current['level_min']}-{current['level_max']}, Lv{self.level}) — no recent data, avoiding wasted travel")
                        return
                # Also build connection map for route-finding
                connections = map_data.get('connections', [])
                reachable_ids = set()
                for c in connections:
                    if c.get('zoneAId') == self.current_zone_id:
                        reachable_ids.add(c['zoneBId'])
                    if c.get('zoneBId') == self.current_zone_id:
                        reachable_ids.add(c['zoneAId'])
                # Find best hunting ground for level — ONLY directly reachable zones.
                # Travel to non-reachable zones fails with "no connection between these
                # zones" (start_travel only accepts single-hop paths). If no reachable
                # zone matches the level range, relax the level constraint rather than
                # picking an unreachable zone that will fail on arrival.
                # ENHANCED: Prefer zones with recent monster activity (global productivity)
                # and allow up to 5 levels above zone max for highly productive zones.
                now = time.time()
                candidates = []
                for zid, info in zones_info.items():
                    if zid in self._zone_travel_blacklist:
                        continue  # Skip zones that failed travel
                    if info.get('type') == 'hunting_ground':
                        reachable = zid in reachable_ids
                        if reachable:
                            # Productivity bonus: zones with monsters in last 5 min
                            last_prod = CharacterAgent._global_zone_productivity.get(zid, 0)
                            prod_bonus = 500 if (last_prod > 0 and now - last_prod < 300) else 0
                            within_level = info['level_min'] <= self.level <= info['level_max']
                            slightly_above = (self.level > info['level_max'] and 
                                              self.level - info['level_max'] <= 5 and 
                                              prod_bonus > 0)
                            if within_level:
                                score = (self.level - info['level_min']) + (info['level_max'] - self.level)
                                # Current zone bonus: heavily prefer staying put over
                                # traveling to a different zone. Travel costs 15-45s of
                                # wasted test time and risks landing in a dead zone.
                                # Only a significantly better zone should trigger travel.
                                if zid == self.current_zone_id:
                                    score -= 200  # Strong preference for current zone
                                candidates.append((score - prod_bonus, zid, info['name']))
                            elif slightly_above:
                                # Relax upper bound: allow chars up to 5 levels above
                                # zone max if zone has been productive recently
                                over_level = self.level - info['level_max']
                                score = 50 + over_level * 10  # Penalize for being above
                                candidates.append((score - prod_bonus, zid, info['name']))
                            else:
                                # Record as fallback even if level-mismatched
                                level_score = abs(self.level - (info['level_min'] + info['level_max']) // 2)
                                candidates.append((100 + level_score - prod_bonus, zid, info['name']))
                if not candidates and self._zone_travel_blacklist:
                    # All reachable zones are blacklisted — no candidates available.
                    # This happens when the API map says zones are connected but the
                    # server disagrees (e.g., zone 1 → 44341 fails with 'no connection').
                    # Instead of clearing the blacklist (which retries same failing zones),
                    # try multi-hop routing through a known intermediary FIRST.
                    # Zone 149 (Gludios city) is known to be reachable from zone 1
                    # and has connections to zones like 64188.
                    # MUST try this BEFORE town backoff — the travel error handler
                    # (line 1044) sets _town_auto_backoff on the FIRST failed travel
                    # attempt from zone 1, which would cause the backoff check below
                    # to short-circuit before zone 149 routing is ever attempted.
                    # This was a silent bug (Tick 58 fix): zone 149 routing was gated
                    # on NOT having town backoff active, but backoff was always set
                    # before this code was reached.
                    if self.current_zone_id == 1 and 149 not in self._zone_travel_blacklist:
                        try:
                            if self.world is None:
                                from grimeage_agent import WorldData
                                self.world = WorldData(self.rest)
                                self.world.load()
                            if self.world and self.world._loaded:
                                path_to_149 = self.world.find_path(1, 149)
                                if path_to_149 and len(path_to_149) >= 2:
                                    self.analytics.log(f"[{self.name}] Routing through zone 149 (Gludios) to escape zone 1")
                                    self._hunting_zone_id = 149
                                    self.analytics.log(f"[{self.name}] Traveling to hub 149...")
                                    await self._travel_to_hunting_zone()
                                    self._hunting_zone_id = None
                                    return
                        except Exception:
                            pass
                        # Zone 149 routing already tried but failed — blacklist it
                        # so the subsequent pathfinding doesn't retry it.
                        self._zone_travel_blacklist.add(149)
                    # TOWN BACKOFF: if we've been stuck in zone 1 with repeated failed
                    # travel attempts (and even zone 149 routing failed), skip the
                    # blacklist-clear retry loop and go straight to the auto-farm fallback.
                    # The 120s backoff is set by the travel error handler for zone 1.
                    if self.current_zone_id == 1 and getattr(self, '_town_auto_backoff', 0) > time.time():
                        self.analytics.log(f"[{self.name}] Town backoff active ({getattr(self, '_town_auto_backoff', 0) - time.time():.0f}s) — activating auto-farm fallback")
                        # Activate auto-farm HERE and return immediately. On subsequent
                        # ticks, the early-return at line 2561-2564 (is_autofarming check)
                        # will skip zone selection entirely while the 120s backoff is active.
                        if not self.is_autofarming:
                            await self.ws_send('combat:toggle_autofarm', {})
                            self.is_autofarming = True
                            self.analytics.log(f"[{self.name}] Auto-farm enabled in town — productive until backoff expires")
                        return
                    # Fallback: clear the blacklist so we can retry from scratch.
                    # The 5s travel_backoff from the error handler prevents spam.
                    count = len(self._zone_travel_blacklist)
                    self._zone_travel_blacklist.clear()
                    self.analytics.log(f"[{self.name}] Cleared blacklist ({count} zones) — retrying with full zone list")
                    # Rebuild candidates with blacklist cleared
                    for zid, info in zones_info.items():
                        if info.get('type') == 'hunting_ground':
                            reachable = zid in reachable_ids
                            if reachable:
                                last_prod = CharacterAgent._global_zone_productivity.get(zid, 0)
                                prod_bonus = 500 if (last_prod > 0 and now - last_prod < 300) else 0
                                within_level = info['level_min'] <= self.level <= info['level_max']
                                slightly_above = (self.level > info['level_max'] and 
                                                  self.level - info['level_max'] <= 5 and 
                                                  prod_bonus > 0)
                                if within_level:
                                    score = (self.level - info['level_min']) + (info['level_max'] - self.level)
                                    candidates.append((score - prod_bonus, zid, info['name']))
                                elif slightly_above:
                                    over_level = self.level - info['level_max']
                                    score = 50 + over_level * 10
                                    candidates.append((score - prod_bonus, zid, info['name']))
                                else:
                                    level_score = abs(self.level - (info['level_min'] + info['level_max']) // 2)
                                    candidates.append((100 + level_score - prod_bonus, zid, info['name']))
                if candidates:
                    candidates.sort()
                    best_id = candidates[0][1]
                    best_name = candidates[0][2]
                    self.analytics.log(f"[{self.name}] Found zone {best_id} ({best_name}) for Lv{self.level}")
                    self._hunting_zone_id = best_id
                    if self.current_zone_id != best_id:
                        self.analytics.log(f"[{self.name}] Traveling to {best_id}...")
                        # Use _travel_to_hunting_zone which handles combat/rest
                        # cancel and backoff. The hunting zone is already set above.
                        await self._travel_to_hunting_zone()
                        return
                else:
                    # No reachable hunting grounds from current position (e.g., zone 1
                    # respawn point with no working zone connections). Try a reachable
                    # CITY zone as an intermediary — from there we can find hunting zones.
                    # The next _find_and_travel_hunting_zone call (after travel_complete)
                    # will re-evaluate from the new position.
                    city_candidates = []
                    for zid, info in zones_info.items():
                        if zid in self._zone_travel_blacklist:
                            continue
                        if info.get('type') in ('city', 'civilian', 'safe_zone', 'town'):
                            reachable = zid in reachable_ids
                            if reachable:
                                city_candidates.append(zid)
                    if city_candidates:
                        # Pick the first reachable city
                        hub_id = city_candidates[0]
                        hub_name = zones_info.get(hub_id, {}).get('name', f'Zone{hub_id}')
                        self.analytics.log(f"[{self.name}] No reachable hunting grounds — "
                                          f"traveling to hub zone {hub_id} ({hub_name}) first")
                        # Use _travel_to_hunting_zone's travel mechanism: set hunting zone
                        # temporarily to the city, travel there, then _find_and_travel will
                        # re-evaluate from the new position on the next tick.
                        self._hunting_zone_id = hub_id
                        self.analytics.log(f"[{self.name}] Traveling to hub {hub_id}...")
                        await self._travel_to_hunting_zone()
                        # Don't save the city as hunting zone — clear it so the next
                        # tick re-evaluates from the new position
                        self._hunting_zone_id = None
                        return
                    # No reachable city either. Try multi-hop pathfinding to any
                    # level-appropriate hunting ground via BFS. The travel infrastructure
                    # (_travel_to_hunting_zone → _send_next_travel_hop) already supports
                    # multi-hop travel — it's the zone SELECTION that was missing multi-hop.
                    if self.world is None:
                        try:
                            from grimeage_agent import WorldData
                            self.world = WorldData(self.rest)
                            self.world.load()
                        except Exception as e:
                            self.analytics.log(f"[{self.name}] WorldData init failed ({e})")
                            self.world = None
                    if self.world and self.world._loaded:
                        # Score all hunting grounds reachable via any path, not just direct
                        now = time.time()
                        multi_hop_candidates = []
                        for zid, info in zones_info.items():
                            if zid in self._zone_travel_blacklist:
                                continue
                            if info.get('type') != 'hunting_ground':
                                continue
                            within_level = info['level_min'] <= self.level <= info['level_max']
                            if not within_level:
                                # Allow up to 5 levels above zone max if globally productive
                                last_prod = CharacterAgent._global_zone_productivity.get(zid, 0)
                                prod_active = (last_prod > 0 and now - last_prod < 300)
                                slightly_above = (self.level > info['level_max'] and
                                                  self.level - info['level_max'] <= 5 and prod_active)
                                if not slightly_above:
                                    continue
                            path = self.world.find_path(self.current_zone_id, zid)
                            if path and len(path) > 1:
                                path_len = len(path) - 1  # Number of hops
                                # Prefer shorter paths + productive zones
                                last_prod = CharacterAgent._global_zone_productivity.get(zid, 0)
                                prod_bonus = 200 if (last_prod > 0 and now - last_prod < 300) else 0
                                score = (path_len * 10) - prod_bonus
                                multi_hop_candidates.append((score, zid, info['name'], path_len))
                        if multi_hop_candidates:
                            multi_hop_candidates.sort()
                            score, mzid, mzname, hops = multi_hop_candidates[0]
                            self.analytics.log(f"[{self.name}] Multi-hop ({hops} hops) to hunting zone "
                                              f"{mzid} ({mzname}) for Lv{self.level}")
                            self._hunting_zone_id = mzid
                            await self._travel_to_hunting_zone()
                            return
            self.analytics.log(f"[{self.name}] Could not find hunting zone for Lv{self.level} — clearing blacklist to retry flaky zones")
            # A zone that flaked once ("no connection") must not be banned
            # forever — the server's routing is inconsistent with the API map
            # (149→64188 works sometimes, fails others; observed 2026-08-04).
            # Clear the blacklist so the next tick retries the real hunting
            # grounds instead of looping "Could not find" for 9+ minutes.
            self._zone_travel_blacklist.clear()
            self._hunting_zone_id = None
            # When stuck in town (zone 1) with no reachable hunting zones,
            # enable auto-farm as a productive fallback instead of looping
            # on failed travel attempts that consume the entire test window.
            # The town has basic spawns and keeps the character active until
            # the backoff expires and _find_and_travel_hunting_zone retries.
            # Condition: in zone 1 AND not already auto-farming. The backoff
            # is also set here as a guard for the function-level backoff check,
            # but the auto-farm should activate regardless of backoff state.
            if self.current_zone_id == 1 and not self.is_autofarming:
                self._town_auto_backoff = time.time() + 120
                self.analytics.log(f"[{self.name}] Stuck in town — enabling auto-farm as fallback (120s cooldown)")
                await self.ws_send('combat:toggle_autofarm', {})
                self.is_autofarming = True
        except Exception as e:
            self.analytics.track_error(self.name, f'zone find: {e}')
            # Clear hunting zone on error so we don't try to travel to a broken state
            self._hunting_zone_id = None

    # ═════════════════════════════════════════
    # ROLE-BASED COMBAT AI
    # ═════════════════════════════════════════

    async def _dps_tick(self):
        """DPS combat — focus fire the tank's target, nuke it down."""
        if await self._respawn_if_dead():
            return

        # If already resting, don't attempt combat actions — server rejects them
        if self.is_resting:
            return

        # Self-preservation: self-heal only in EMERGENCY (HP critically low).
        # DPS should NOT interrupt damage output for minor HP loss — let the healer
        # or rest system handle recovery. Magic findings (tick14-15): 40% threshold
        # caused 0-8 dmg/min heal loop; 25% threshold gives 5-10x more combat uptime.
        hp_pct = self.hp / max(self.max_hp, 1)
        if hp_pct < 0.25:
            healed = await self._heal_party_members()
            if healed:
                return  # Skip attack this tick, let heal land

        self._clean_monsters()
        if not self.monsters:
            self.combat_state = 'IDLE'
            return

        # Focus fire: attack the tank's current target
        tank_target = self._get_tank_target()
        target = None

        if tank_target:
            # Check if tank's target is still alive
            if any(m.get('id') == tank_target.get('id') for m in self.monsters):
                target = tank_target

        if not target:
            target = self._select_best_target()

        if not target:
            return

        self.current_target = target
        self.combat_state = 'FIGHTING'
        # Attack initiation tick — use skills on subsequent ticks
        if not self._target_attack_initiated:
            await self._attack_target(target['id'])
        else:
            await self._use_best_skill(target['id'])

        # Rest check AFTER combat actions — prevents wasted ticks where rest
        # is attempted but rejected (mid-combat rest always fails), blocking
        # all damage output. Same bug as Tick 73 healer fix.
        # This is non-blocking: if rest succeeds, next tick's is_resting guard
        # will skip combat actions. If rest fails, no harm done — already attacked.
        await self._check_rest_needed()

    # ═════════════════════════════════════════
    # TANK COMBAT AI
    # ═════════════════════════════════════════

    async def _tank_tick(self):
        """Tank combat — grab aggro, take hits, protect the party."""
        if await self._respawn_if_dead():
            return
        
        # Self-preservation: try to rest if HP low, otherwise keep fighting.
        # The old code stopped all attacks at 25% HP and sat idle, causing a death
        # spiral where is_in_combat blocked rest recovery. Now: rest if possible,
        # otherwise fight to the death (death + respawn is faster than slow regen).
        hp_pct = self.hp / max(self.max_hp, 1)
        if await self._check_rest_needed():
            return  # Now resting (handles all HP levels including < 25%)

        self._clean_monsters()
        if not self.monsters:
            self.combat_state = 'IDLE'
            return

        # Periodic re-evaluation: every 3 ticks, repick the best target
        # instead of sticking with current_target. This lets the tank
        # switch to nearly-dead monsters for the killing blow, maximizing
        # gold from last-hit credit. Without this, the tank gets stuck on
        # a single monster while others die to auto-farm or other players.
        self._tank_recheck_counter = getattr(self, '_tank_recheck_counter', 0) + 1
        force_recheck = self._tank_recheck_counter >= 3

        target = None
        if self.current_target and not force_recheck:
            if any(m.get('id') == self.current_target.get('id') for m in self.monsters):
                target = self.current_target

        if not target:
            target = self._tank_select_target()
            self._tank_recheck_counter = 0  # Reset after fresh selection

        if not target:
            return

        self.current_target = target
        self.combat_state = 'FIGHTING'
        # Attack initiation tick — use skills on subsequent ticks
        if not self._target_attack_initiated:
            await self._attack_target(target['id'])
        else:
            await self._use_best_skill(target['id'])

    
    def _tank_select_target(self):
        """Tank target selection using real threat values from combat:threat_update.
        Prefers monsters that have high threat on non-tank party members
        (healer/DPS have aggro = urgent to taunt).
        Falls back to attacker-set heuristic if no threat data available."""
        if not self.monsters:
            return None

        threat_table = getattr(self, '_threat_table', None)
        has_threat_data = threat_table and len(threat_table) > 0

        scored = []
        attacker_ids = {a.get('id') for a in self.attackers}

        for m in self.monsters:
            mid = m.get('id')
            hp = m.get('hp', 1)
            max_hp = m.get('maxHp', 1)
            score = 0

            if has_threat_data and mid in threat_table:
                # Use real threat values from server
                threats = threat_table[mid]
                total_threat = sum(threats.values())
                my_threat = threats.get(self.char_id, 0)
                my_pct = my_threat / max(total_threat, 1)
                
                # High threat on anyone else = monster is a danger to party
                if my_pct < 0.4:
                    score += 100  # I don't have aggro — urgent!
                elif my_pct < 0.7:
                    score += 50   # Partial aggro — stabilize
                
                # If a non-tank has any threat on this monster, it's a threat
                for cid, threat in threats.items():
                    if cid != self.char_id:
                        if threat > 0:
                            score += 30  # Someone else has aggro
                            break
                
                # Low-HP monsters die faster = less incoming damage = higher priority
                score += (1.0 - hp / max(max_hp, 1)) * 25
            else:
                # No threat data: use attacker-set heuristic (legacy)
                if mid in attacker_ids:
                    score += 10  # Already attacking us = managed
                else:
                    score += 50  # Not on us = urgent (attacking healer/DPS)

                # Prefer lower HP targets (will die faster = less incoming damage)
                score += (1.0 - hp / max(max_hp, 1)) * 20

                # Prefer full-health monsters that haven't been hit yet
                if hp == max_hp:
                    score += 15

            scored.append((score, m))

        scored.sort(key=lambda x: -x[0])
        return scored[0][1] if scored else None


    # ═════════════════════════════════════════
    # HEALER COMBAT AI
    # ═════════════════════════════════════════

    async def _healer_tick(self):
        """Healer combat — keep party alive first, DPS when safe."""
        if await self._respawn_if_dead():
            return
        
        # Self-preservation: must be alive to heal others.
        # In solo mode (no party members), monsters damage the healer directly
        # with no tank to absorb. Raise the threshold from 40% to 55% so the
        # healer stops to self-heal before HP drops critically low. The extra
        # buffer gives the heal cast time to land even under monster fire.
        hp_pct = self.hp / max(self.max_hp, 1)
        solo_buffer = 0.15 if not self.party_members else 0.0
        self_preserve_threshold = 0.40 + solo_buffer
        if hp_pct < self_preserve_threshold:
            healed = await self._heal_party_members()
            if healed:
                return  # Wait for heal to land
            # Heal failed (cooldown/no MP) — try resting instead of standing idle
            if await self._check_rest_needed():
                return
            # Still can't rest either — don't engage at critical HP
            if hp_pct < 0.30:
                return

        # Check party HP and heal if needed BEFORE rest check.
        # _check_rest_needed() following this will return True if rest is
        # needed, but if rest fails (server rejects mid-combat rest), the
        # tick is wasted. By healing first, we ensure self-preservation
        # happens even when rest is attempted on the same tick.
        # After healing, check rest. If rest is successful, it will restore
        # HP/MP faster than killing monsters. If rest fails (server rejection),
        # the next tick heals again and DPSes (no rest check on next tick
        # when is_resting is False and monsters exist).
        healed = await self._heal_party_members()
        if healed:
            # If we just healed, skip attack this tick to let mana regen
            return

        if await self._check_rest_needed():
            return

        # Only DPS if nobody needs healing and we have spare MP
        # Dynamic MP gate: reserve enough for the cheapest heal
        self._clean_monsters()
        if not self.monsters:
            self.combat_state = 'IDLE'
            return

        # Only reserve MP for healing when party members exist.
        # In solo mode, there's nobody to heal but self (already handled by
        # _heal_party_members at line 2560 above). Skipping the gate lets
        # the healer DPS freely without wasting MP reservation on no one.
        if self.party_members:
            cheapest_heal = None
            for s in self.skills:
                if s.get('type') == 'heal' and not s.get('isPassive'):
                    mp = s.get('mpCost', 0)
                    if cheapest_heal is None or mp < cheapest_heal:
                        cheapest_heal = mp
            if cheapest_heal and self.max_mp > 0:
                mp_gate = cheapest_heal / self.max_mp * 1.5  # 1.5x safety buffer
            else:
                mp_gate = 0.35  # fallback
            mp_pct = self.mp / max(self.max_mp, 1)
            if mp_pct < mp_gate:
                # Save MP for urgent healing only, don't attack
                return

        # Attack the tank's target (focus fire)
        tank_target = self._get_tank_target()
        target = None
        if tank_target:
            if any(m.get('id') == tank_target.get('id') for m in self.monsters):
                target = tank_target
        if not target:
            target = self._select_best_target()
        if not target:
            return

        self.current_target = target
        self.combat_state = 'FIGHTING'
        # Initiate attack if new target, then use skills
        if not self._target_attack_initiated:
            await self._attack_target(target['id'])
        else:
            await self._use_best_skill(target['id'])

    async def _heal_party_members(self) -> bool:
        """Check party member HP and use healing skills on lowest HP ally.
        Also handles solo self-heal when no party is present.
        Fully dynamic — reads cooldowns and cast times from skill data.
        Returns True if a heal was cast.

        Role-based filter: DPS and tank roles only self-heal (the healer
        handles party healing). Healers check all party members."""
        now = time.time()
        hp_pct = self.hp / max(self.max_hp, 1)

        # Global skill block: don't heal if a previous cast is still in progress
        blocked_until = getattr(self, '_skill_blocked_until', 0)
        if now < blocked_until:
            return False

        # Find lowest HP party member (including self)
        candidates = []

        # Solo self-heal: only check self when HP critically low.
        # Threshold raised from 0.60 to 0.70 so the healer self-heals
        # BEFORE a DPS cast block expires, preventing the HP crash
        # where monster damage exceeds the heal block window.
        if not self.party_members:
            # Solo mode — only self-heal if HP below 70%
            if hp_pct > 0.70:
                return False
            # Anti-heal-loop: dynamic based on fastest heal's cast time + 2s buffer
            min_heal_gap = self._get_fastest_heal_interval()
            last_self = getattr(self, '_last_self_heal_time', 0)
            if now - last_self < min_heal_gap:
                return False
            self._last_self_heal_time = now
            candidates.append((hp_pct, self.char_id, 'self'))
        else:
            # Party mode — role-based: DPS/tank only self-heal, healer checks all
            if self.role in ('dps', 'tank'):
                # Non-healer: only self-heal in party
                if hp_pct > self.rest_hp_threshold:
                    return False  # Above rest threshold, don't waste a DPS/tank tick on healing
                candidates.append((hp_pct, self.char_id, 'self'))
            else:
                # Healer role: check all party members
                for cid, pm in self.party_members.items():
                    pm_hp = pm.get('hp', 1)
                    pm_max = pm.get('maxHp', 1)
                    if pm_max > 0 and pm_hp > 0:
                        pct = pm_hp / pm_max
                        candidates.append((pct, cid, 'party'))
                # Add self to candidates
                candidates.append((hp_pct, self.char_id, 'self'))

        if not candidates:
            return False

        # Sort by HP% ascending (lowest first)
        candidates.sort(key=lambda x: x[0])
        lowest_pct, lowest_cid, _ = candidates[0]

        # Only heal if below threshold
        if lowest_pct > 0.75:
            return False

        # Find a healing skill in our rotation
        if not self.auto_config:
            return False

        # Find healing skills (by checking skill type == heal)
        for c in sorted(self.auto_config, key=lambda x: x.get('autoPriority', 99)):
            if not c.get('autoEnabled'):
                continue
            sid = c.get('skillId')
            if not sid:
                continue
            # Check cooldown
            if sid in self.skill_cooldowns and now < self.skill_cooldowns[sid]:
                continue
            # Check MP cost and skill type
            skill_info = next((s for s in self.skills if s.get('id') == sid), None)
            if not skill_info:
                continue
            # Skip if not a heal-type skill
            if skill_info.get('type') != 'heal':
                continue
            mp_cost = skill_info.get('mpCost', 0)
            if self.mp < mp_cost:
                continue
            # Check self HP/MP gates
            if self._is_skill_gated(c, self.hp / max(self.max_hp, 1), self.mp / max(self.max_mp, 1)):
                continue

            await self.ws_send('combat:use_skill', {
                'skillId': sid,
                'targetId': lowest_cid,
                'targetType': 'self' if lowest_cid == self.char_id else 'party'
            })
            # Block global skill usage based on this heal's cast time
            # Heals never get casting_complete, so use generous 2.0x buffer
            cast_ms = skill_info.get('castTimeMs', 0) or 0
            block_duration = max(cast_ms / 1000.0 * 2.0, 1.5)
            self._skill_blocked_until = now + block_duration
            # Use skill's actual cooldown. Server starts cooldown at cast
            # completion, so effective CD = cast_time + server_cd.
            raw_cd = skill_info.get('cooldownSeconds', 0) or 0
            if raw_cd > 0:
                cd_sec = max(cast_ms / 1000.0 + raw_cd, 1.0)
            else:
                cd_sec = max(cast_ms / 1000.0 * 1.5, 1.5)
            self.skill_cooldowns[sid] = now + cd_sec
            self.analytics.log(f"[{self.name}] Healed {lowest_cid} (HP:{lowest_pct*100:.0f}%) "
                               f"with skill {sid} (cast:{cast_ms}ms, cd:{cd_sec}s)")
            return True

        return False

    def _get_fastest_heal_interval(self) -> float:
        """Find the shortest heal cast time + buffer for anti-heal-loop timing."""
        if not self.skills:
            return 5.0  # Safe fallback
        min_interval = 5.0
        for s in self.skills:
            if s.get('type') == 'heal' and not s.get('isPassive'):
                cast_ms = s.get('castTimeMs', 0) or 0
                interval = max(cast_ms / 1000.0 + 2.0, 3.0)
                min_interval = min(min_interval, interval)
        return min_interval

    def _get_tank_target(self):
        """Get the tank's current target for focus fire."""
        if not self.partner_agents:
            return None
        for cid, agent in self.partner_agents.items():
            if agent.role == 'tank' and agent.current_target:
                return agent.current_target
        return None

    def _select_best_target(self):
        """Generic target selection — prefers lowest HP monsters."""
        if not self.monsters:
            return None
        scored = []
        for m in self.monsters:
            hp = m.get('hp', 1)
            max_hp = m.get('maxHp', 1)
            hp_pct = hp / max(max_hp, 1)
            score = (1.0 - hp_pct) * 50
            if hp < max_hp:
                score += 10  # Already damaged = easier to kill
            scored.append((score, m))
        scored.sort(key=lambda x: -x[0])
        return scored[0][1] if scored else None

    def _skill_efficiency(self, cfg_entry: dict) -> float:
        """Compute uptime frequency of a skill = 1/(castTime + cooldown).
        Higher = more casts per second = more DPS.
        Used by _load_skills_from_rest to presort the rotation."""
        sid = cfg_entry.get('skillId')
        if not sid:
            return 0.01
        for s in self.skills:
            if s.get('id') == sid:
                cast_s = s.get('castTimeMs', 0) / 1000.0
                cd_s = s.get('cooldownSeconds', 3) or 3
                cycle = cast_s + cd_s
                return 1.0 / max(cycle, 1.0)
        return 0.01

    
    async def _use_best_skill(self, target_id: int):
        """Use the best available skill from the rotation on a monster target.
        Fully dynamic — no hardcoded intervals, reads castTimeMs, cooldownSeconds,
        duration, and weapon requirements from skill data."""
        if not self.auto_config or not target_id:
            return
        now = time.time()

        # Global skill block: wait for previous cast to finish + buffer
        blocked_until = getattr(self, '_skill_blocked_until', 0)
        if now < blocked_until:
            return

        # Clear stale pending skill (>15s safety timeout — normally resolves
        # via combat:attack (wizard) or casting_complete (fighter) events.
        # 15s is a hard failsafe for non-damaging debuffs or missed events.)
        if self._pending_skill_sid and self._pending_skill_time > 0:
            if now - self._pending_skill_time > 15.0:
                self._pending_skill_sid = None
                self._pending_skill_time = 0

        # Rotation is presorted in _load_skills_from_rest by uptime efficiency.
        # Iterate in order and pick the first usable skill.
        for c in self.auto_config:
            if not c.get('autoEnabled'):
                continue
            sid = c.get('skillId')
            if not sid:
                continue

            # Skip passive skills
            skill_info = next((s for s in self.skills if s.get('id') == sid), None)
            if skill_info and skill_info.get('isPassive'):
                continue

            # Cooldown check
            if sid in self.skill_cooldowns and now < self.skill_cooldowns[sid]:
                continue

            # Dynamic min interval: cast time + buffer (wizard spells need more)
            cast_ms = 0
            if skill_info:
                cast_ms = skill_info.get('castTimeMs', 0) or 0

            # Weapon requirement check
            current_weapon = self._get_current_weapon()
            if skill_info and not self._check_weapon_requirement(skill_info.get('requiredWeapons', []), current_weapon):
                continue

            # DoT check — use skill's duration if available, default to 8s
            if self._is_dot_skill(skill_info):
                if sid in self._dot_skills and target_id in self._dot_skills[sid]:
                    if now < self._dot_skills[sid][target_id]:
                        continue

            # HP/MP gate check
            hp_pct = self.hp / max(self.max_hp, 1)
            mp_pct = self.mp / max(self.max_mp, 1)
            if self._is_skill_gated(c, hp_pct, mp_pct):
                continue

            # MP floor: use actual mp_cost of the skill, not a hardcoded percentage
            if skill_info:
                mp_cost = skill_info.get('mpCost', 0)
                if self.mp < mp_cost:
                    continue
            elif mp_pct < 0.05:
                continue

            # Check if this is a heal-type skill — don't use healing skills on monsters
            if skill_info and skill_info.get('type') == 'heal':
                continue

            # Target-alive check: verify monster is still in our list.
            # Server returns "target not alive" if the monster died between
            # target selection and skill fire (common in busy zones).
            target_still_alive = any(
                m.get('id') == target_id for m in self.monsters
            )
            if not target_still_alive:
                self.analytics.log(f"[{self.name}] Target {target_id} no longer alive — skipping skill")
                self._target_attack_initiated = False
                return

            # Fire the skill!
            # Safety: if target wasn't selected (stale flag from monster respawn),
            # select it first. Server silently ignores use_skill without select_target.
            if not self._target_attack_initiated:
                await self.ws_send('combat:select_target', {'targetId': target_id, 'targetType': 'monster'})
                await asyncio.sleep(0.1)
                self._target_attack_initiated = True
            await self.ws_send('combat:use_skill', {
                'skillId': sid,
                'targetId': target_id,
                'targetType': 'monster'
            })
            self._total_casts += 1
            self._pending_skill_sid = sid
            self._pending_skill_time = time.time()
            # Track per-skill cast count for damage attribution
            if sid not in self._skill_damage_log:
                self._skill_damage_log[sid] = {'casts': 0, 'total_dmg': 0, 'name': skill_info.get('name', f'#{sid}') if skill_info else f'#{sid}'}
            self._skill_damage_log[sid]['casts'] += 1
            # Block next skill based on cast time + buffer.
            # Fighters (physical): casting_complete fires — use empirical or tight API + latency.
            # Wizards (magical/debuff/heal): casting_complete NEVER fires (server bug) —
            # use API cast time with a wizard-specific buffer that accounts for gear castSpeedPct.
            latency = self._get_measured_latency()
            if skill_info and skill_info.get('type') in ('magical', 'debuff'):
                # Wizard spells: no completion event — use empirical data if available.
                # Proxy detection via combat:attack with magical/dot damageType
                # (lines 643-646) records actual cast times in _record_cast_completion.
                # After 5+ samples use empirical avg + latency instead of 1.5x buffer
                # for tighter blocks — estimated +15-25% wizard DPS after convergence.
                if (sid and self._empirical_cast_samples.get(sid, 0) >= 5
                        and sid in self._empirical_cast_times):
                    empirical = self._empirical_cast_times[sid]
                    block_duration = max(empirical + latency, 0.5)
                else:
                    block_duration = max(cast_ms / 1000.0 * 2.0, 1.5) if cast_ms > 0 else 1.5
            elif skill_info and skill_info.get('type') == 'heal':
                # Heals: no completion event — use empirical data if available.
                # Proxy detection via combat:heal_applied (casterId match, line 651).
                if (sid and self._empirical_cast_samples.get(sid, 0) >= 5
                        and sid in self._empirical_cast_times):
                    empirical = self._empirical_cast_times[sid]
                    block_duration = max(empirical + latency, 0.5)
                else:
                    block_duration = max(cast_ms / 1000.0 * 2.0, 1.5) if cast_ms > 0 else 1.5
            else:
                # Fighter/physical: casting_complete fires, empirical profiler works
                block_duration = max(cast_ms / 1000.0 + latency, 0.3) if cast_ms > 0 else max(latency * 2.0, 0.3)
            self._skill_blocked_until = now + block_duration
            # Adaptive wake: instead of busy-looping at 200ms, sleep until
            # just before block expires. 85% of block = wake early enough
            # that by the time we reach _use_best_skill, block has expired
            # and we can fire the next skill immediately.
            self._next_action_time = now + block_duration * 0.85
            # Set per-skill cooldown: use server cooldown if available and >0,
            # otherwise use skill-type-aware fallback.
            # Critically: server starts cooldown timer when cast FINISHES,
            # not when command is sent. So effective cooldown = cast_time + server_cd.
            # For wizard/heal skills without completion events, we can't know
            # when the cast finishes, so we use castTimeMs + raw cooldown.
            raw_cd = 0
            if skill_info:
                raw_cd = skill_info.get('cooldownSeconds', 0) or 0
            if raw_cd > 0:
                # Server starts CD at cast completion = castTimeMs/1000 + raw_cd
                cd_sec = max(cast_ms / 1000.0 + raw_cd, 1.0)
            else:
                # No server cooldown data, use 1.5x cast time as fallback
                cd_sec = max(cast_ms / 1000.0 * 1.5, 1.5)
            self.skill_cooldowns[sid] = now + cd_sec
            # Track DoT application — use skill duration if available
            dot_duration = 8.0
            if skill_info:
                dot_duration = skill_info.get('duration', skill_info.get('effectTime', 8.0))
            if self._is_dot_skill(skill_info):
                if sid not in self._dot_skills:
                    self._dot_skills[sid] = {}
                self._dot_skills[sid][target_id] = now + dot_duration
            self.analytics.track_skill_use(self.char_id, sid)
            return  # One skill per tick

        # No skill was available — all on cooldown or filtered out.
        # Calculate staggered CD wake: find the shortest remaining cooldown
        # among all non-passive, non-filtered skills and set _next_action_time
        # so we wake up just before it expires. This eliminates 20+ wasteful
        # 200ms polling ticks waiting for a cooldown window.
        shortest_cd = None
        for c2 in self.auto_config:
            sid2 = c2.get('skillId')
            if not sid2: continue
            info2 = next((s for s in self.skills if s.get('id') == sid2), None)
            if info2 and info2.get('isPassive'): continue
            if not c2.get('autoEnabled'): continue
            if sid2 in self.skill_cooldowns and now < self.skill_cooldowns[sid2]:
                remaining = self.skill_cooldowns[sid2] - now
                if shortest_cd is None or remaining < shortest_cd:
                    shortest_cd = remaining
        if shortest_cd is not None:
            # Wake 100ms before the shortest CD expires, capped at 1s
            # to keep HP/death/monster checks responsive.
            wake_delay = max(shortest_cd - 0.1, 0.05)
            self._next_action_time = now + min(wake_delay, 1.0)

        # Log diagnostic info on first few occurrences to help debug
        # wizard zero-cast issue (Tick 52).
        diag_count = getattr(self, '_no_skill_diag_count', 0)
        if diag_count < 3:
            self._no_skill_diag_count = diag_count + 1
            # Count how many skills were skipped by each guard
            cd_count = 0
            weapon_count = 0
            gate_count = 0
            dot_count = 0
            for c2 in self.auto_config:
                if not c2.get('autoEnabled'): continue
                sid2 = c2.get('skillId')
                if not sid2: continue
                info2 = next((s for s in self.skills if s.get('id') == sid2), None)
                if info2 and info2.get('isPassive'): continue
                if sid2 in self.skill_cooldowns and now < self.skill_cooldowns[sid2]:
                    cd_count += 1; continue
                if info2 and not self._check_weapon_requirement(info2.get('requiredWeapons', []), current_weapon or ''):
                    weapon_count += 1; continue
                if self._is_skill_gated(c2, hp_pct, mp_pct):
                    gate_count += 1; continue
                if self._is_dot_skill(info2):
                    dot_active = (sid2 in self._dot_skills and target_id in self._dot_skills[sid2] and now < self._dot_skills[sid2][target_id])
                    if dot_active:
                        dot_count += 1; continue
            self.analytics.log(f"[{self.name}] ⚠️ No usable skill: cd={cd_count} weapon={weapon_count} gate={gate_count} dot={dot_count} total={len(self.auto_config)} mon={len(self.monsters)} target={target_id}")
        # Stagger next wake to the exact moment the shortest CD expires
        now = time.time()
        shortest_cd = None
        for c in self.auto_config:
            if not c.get('autoEnabled'):
                continue
            sid = c.get('skillId')
            if not sid:
                continue
            cd = self.skill_cooldowns.get(sid, 0)
            if cd > now:
                remaining = cd - now
                if shortest_cd is None or remaining < shortest_cd:
                    shortest_cd = remaining
        if shortest_cd is not None and shortest_cd > 0.2:
            self._next_action_time = now + min(shortest_cd - 0.05, 1.0)  # 50ms early, max 1s for safety

    def _is_dot_skill(self, skill_info: dict) -> bool:
        if not skill_info:
            return False
        name = skill_info.get('name', '').lower()
        return any(kw in name for kw in ['poison', 'bleed', 'burn', 'curse'])

    def _get_current_weapon(self) -> str:
        """Get the name of the currently equipped weapon.
        Tries slot-based lookup first (main_hand/off_hand), falls back to
        name-based detection when API returns null for slot field.
        
        The game's inventory API returns slot=null for all equipped items,
        so slot-based lookup always fails. Name-based fallback detects
        weapons by common keywords in item names (sword, dagger, bow, etc.)."""
        # Slot-based lookup
        for gear in self.equipped_gear:
            if gear.get('slot') in ('main_hand', 'off_hand'):
                return gear.get('itemName', '') or ''
        # Fallback: API may return null for slot — detect by weapon name
        weapon_keywords = ['sword', 'dagger', 'bow', 'staff', 'wand', 'axe',
                           'mace', 'spear', 'hammer', 'club', 'polearm', 'scythe', 'blade']
        for gear in self.equipped_gear:
            name = (gear.get('itemName') or '')
            if name and any(kw in name.lower() for kw in weapon_keywords):
                return name
        return ''

    def _check_weapon_requirement(self, required_weapons: list, current_weapon: str) -> bool:
        if not required_weapons:
            return True
        if not current_weapon:
            # No weapon equipped: check if the requirement is purely exclusion-based
            # (e.g., ['-bow', '-dagger'] means "any weapon except bow/dagger" — no
            # weapon should also work). If there's any inclusion requirement, block.
            # This prevents a bug where all skills are blocked when the character
            # has no weapon equipped (empty equipped_gear from inventory API).
            has_inclusion = any(not rw.startswith('-') for rw in required_weapons)
            return not has_inclusion
        # Word-boundary matching: split weapon name into complete words.
        # 'broad sword' = {'broad', 'sword'} — 'bow' does NOT match.
        # 'short bow' = {'short', 'bow'} — 'bow' DOES match.
        # Without this, 'bow' in 'broad sword' was falsely matching as substring.
        weapon_words = set(current_weapon.lower().split())
        has_inclusion = False
        for rw in required_weapons:
            if rw.startswith('-'):
                if rw[1:] in weapon_words:
                    return False
            else:
                has_inclusion = True
                if rw in weapon_words:
                    return True
        if has_inclusion:
            return False
        return True

    def _is_skill_on_cooldown(self, skill_id: int, now: float = None) -> bool:
        if now is None:
            now = time.time()
        return skill_id in self.skill_cooldowns and now < self.skill_cooldowns[skill_id]

    def _is_skill_gated(self, config: dict, hp_pct: float, mp_pct: float) -> bool:
        if not config:
            return False
        gate_hp_min = config.get('gateSelfHpMin', 0)
        gate_hp_max = config.get('gateSelfHpMax', 100)
        if hp_pct < gate_hp_min / 100.0 or hp_pct > gate_hp_max / 100.0:
            return True
        gate_mp_min = config.get('gateSelfMpMin', 0)
        gate_mp_max = config.get('gateSelfMpMax', 100)
        if mp_pct < gate_mp_min / 100.0 or mp_pct > gate_mp_max / 100.0:
            return True
        return False

    def rest_get(self, path=None):
        return self.rest.get(path)

    
    def fetch_inventory(self):
        data = self.rest.get(f'''/api/inventory/{self.char_id}''')
        if isinstance(data, dict):
            self.inventory = data.get('bag', [])
            self.equipped_gear = data.get('equipped', [])
        return data

    
    def fetch_stats(self):
        return self.rest.get(f'''/api/characters/{self.char_id}/stats''')

    
    def fetch_skills(self):
        data = self.rest.get(f'''/api/skills/character/{self.char_id}''')
        if isinstance(data, list):
            self.skills = data
        return data

    
    async def _load_skills_from_rest(self):
        '''Fetch skills and autoConfig from REST API after connect.'''
        self.fetch_skills()
        conf_data = self.rest.get(f'/api/skills/config/{self.char_id}')
        # API returns {'configs': [...], 'rules': [...]} — extract configs array.
        # Old API may have returned flat list. Handle both.
        if isinstance(conf_data, dict) and 'configs' in conf_data:
            self.auto_config = conf_data['configs']
        elif isinstance(conf_data, list):
            self.auto_config = conf_data
        if self.auto_config:
            # Presort by uptime efficiency (fastest skills first) — avoids
            # O(n log n) sort on every _use_best_skill tick. Sorts once and
            # caches the order for the lifetime of the skill config.
            self.auto_config.sort(key=lambda c: self._skill_efficiency(c), reverse=True)

    def _filter_skills_by_weapon(self):
        """Remove skills from rotation that can't be used with current weapon.
        Checks the weapon requirement of each skill against equipped main_hand/off_hand.
        If the best skill needs a weapon we don't have, logs a recommendation."""
        if not self.auto_config:
            return
        # Find current weapon name
        current_weapon = self._get_current_weapon()
        if not current_weapon:
            return  # Can't filter without weapon data

        # Check each skill — skip passives (always usable) and filter by weapon
        kept = []
        removed = []
        for c in self.auto_config:
            sid = c.get('skillId')
            if not sid:
                kept.append(c)
                continue
            skill_info = next((s for s in self.skills if s.get('id') == sid), None)
            if not skill_info:
                kept.append(c)
                continue
            if skill_info.get('isPassive'):
                kept.append(c)
                continue
            req = skill_info.get('requiredWeapons', [])
            if not req:
                kept.append(c)
                continue
            # Check if current weapon satisfies requirement
            if self._check_weapon_requirement(req, current_weapon):
                kept.append(c)
            else:
                removed.append((c, req, current_weapon))

        self.auto_config = kept
        if removed:
            parts = []
            for c, req, _ in removed[:5]:
                sname = next((s.get("name","?") for s in self.skills if s.get("id")==c.get("skillId")), "?")
                parts.append(f'{sname} (needs {"/".join(req)})')
            names = ', '.join(parts)
            self.analytics.log(f'[{self.name}] Filtered {len(removed)} skills: {names} — current weapon: {current_weapon}')
            # Check if the best remaining skill is much worse than a gated one
            best_gated = None
            best_gated_power = 0
            for c, req, _ in removed:
                info = next((s for s in self.skills if s.get('id') == c.get('skillId')), None)
                if info:
                    pwr = info.get('power', 0)
                    if pwr > best_gated_power:
                        best_gated_power = pwr
                        best_gated = info.get('name', '?')
            if best_gated and best_gated_power > 0:
                # Find current best skill power
                current_best = 0
                for c in kept:
                    info = next((s for s in self.skills if s.get('id') == c.get('skillId')), None)
                    if info:
                        current_best = max(current_best, info.get('power', 0))
                if best_gated_power > current_best * 1.2:  # 20%+ better
                    self.analytics.log(f'[{self.name}] ⚠️ RECOMMENDATION: equip a weapon that enables "{best_gated}" (power {best_gated_power}) — would increase skill DPS significantly!')

    
    def equip_item(self, inventory_id=None):
        return self.rest.post(f'''/api/inventory/{self.char_id}/equip''', {
            'inventoryId': inventory_id })

    
    def unequip_slot(self, slot=None):
        return self.rest.post(f'''/api/inventory/{self.char_id}/unequip''', {
            'slot': slot })

    def _auto_equip_best_weapon(self):
        """Equip the highest-stat weapon from the bag by class stat (fighter/
        tank → p_atk, wizard → m_atk), respecting level requirements.

        Prevents leaving upgrades in the bag — 2026-08-04: ShieldBot farmed with
        Broad Sword (28) while Mithril Warhammer (82) sat in his bag; equipping
        it 5.3x'd the manual farm rate (2,440 → 12,976 g/hr). Runs at connect
        (first game_state) before skill filtering so dagger/bow unlocks are
        reflected in the rotation."""
        try:
            inv = self.fetch_inventory()
            if not isinstance(inv, dict):
                return None
            stat_idx = 1 if getattr(self, 'char_class', '') == 'wizard' else 0
            cur_items = inv.get('equipped', []) or []
            cur_best = 0
            for it in cur_items:
                st = WEAPON_CATALOG.get(it.get('itemName'))
                if st:
                    cur_best = max(cur_best, st[stat_idx])
            best, best_val = None, cur_best
            for it in inv.get('bag', []) or []:
                if (it.get('itemType') or '').lower() != 'weapon':
                    continue
                st = WEAPON_CATALOG.get(it.get('itemName'))
                if not st:
                    continue
                if (self.level or 0) < st[2]:
                    continue  # level-gated
                if st[stat_idx] > best_val:
                    best, best_val = it, st[stat_idx]
            if best:
                res = self.equip_item(best.get('id') or best.get('inventoryId'))
                self.analytics.log(f"[{self.name}] Auto-equipped {best.get('itemName')} "
                                   f"({'m_atk' if stat_idx else 'p_atk'}={best_val}) — was {cur_best}")
                return res
            return None
        except Exception as e:
            self.analytics.log(f"[{self.name}] auto-equip failed: {e}")
            return None

    
    def buy_item(self, npc_id = None, item_id = None, quantity = (1,)):
        return self.rest.post(f'''/api/shop/{npc_id}/buy''', {
            'characterId': self.char_id,
            'itemId': item_id,
            'quantity': quantity })

    
    def sell_item(self, npc_id = None, inventory_slot = None, quantity = (1,)):
        return self.rest.post(f'''/api/shop/{npc_id}/sell''', {
            'characterId': self.char_id,
            'inventorySlot': inventory_slot,
            'quantity': quantity })

    
    def auto_sell_junk(self, npc_id=None):
        '''Sell vendor trash items. Returns count sold.'''
        if not self.inventory:
            self.fetch_inventory()
        sold = 0
        for item in list(self.inventory):
            name = item.get('itemName', '').lower()
            item_type = item.get('itemType', '').lower()
            slot = item.get('slot', '')
            qty = item.get('quantity', 1)
            if item.get('isEquipped') or slot in GEAR_SLOTS:
                continue
            if item_type == 'material':
                # Crafting materials are the crafting economy (Mithril Alloy,
                # Magical Dust, Magic/Dark Crystal, Leather, Reinforced Bone...).
                # Never sell them as junk — dagger/gear recipes need them.
                continue
            is_junk = item_type in JUNK_TYPES
            if not is_junk:
                for kw in VENDOR_TRASH_KEYWORDS:
                    if kw in name:
                        is_junk = True
                    if not is_junk:
                        continue
            result = self.sell_item(npc_id, slot, qty)
            if isinstance(result, dict) and result.get('status') == 'ok':
                sold += qty
                continue
            inv_id = item.get('id', item.get('inventoryId'))
            if inv_id:
                result2 = self.rest.post(f'''/api/shop/{npc_id}/sell''', {
                    'characterId': self.char_id,
                    'inventorySlot': str(inv_id),
                    'quantity': qty })
                if isinstance(result2, dict) and result2.get('status') == 'ok':
                    sold += qty
            if sold > 0:
                self.fetch_inventory()
        return sold

    
    def get_bag_space(self):
        '''Get bag slots used/max.'''
        data = self.rest.get(f'''/api/inventory/{self.char_id}''')
        if isinstance(data, dict):
            slots = data.get('bagSlots', { })
            return {
                'used': slots.get('used', 0),
                'max': slots.get('max', 20) }
        return {
            'used': None,
            'max': 20 }

    
    def fetch_available_quests(self):
        '''Get available quests for this character.'''
        data = self.rest.get(f'''/api/quests/available?characterId={self.char_id}''')
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and 'quests' in data:
            return data['quests']

    
    def fetch_active_quests(self):
        '''Get active (in-progress) quests.'''
        data = self.rest.get(f'''/api/quests/active?characterId={self.char_id}''')
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and 'quests' in data:
            return data['quests']

    
    def accept_quest(self, quest_id=None):
        return self.rest.post(f'''/api/quests/{quest_id}/accept''', {
            'characterId': self.char_id })

    
    def advance_quest(self, quest_id=None):
        return self.rest.post(f'''/api/quests/{quest_id}/advance''', {
            'characterId': self.char_id })

    
    def complete_quest(self, quest_id=None):
        return self.rest.post(f'''/api/quests/{quest_id}/complete''', {
            'characterId': self.char_id })

    
    def claim_quest(self, quest_id=None):
        return self.rest.post(f'''/api/quests/{quest_id}/claim''', {
            'characterId': self.char_id })

    
    def ignore_quest(self, quest_id=None):
        return self.rest.post(f'''/api/quests/{quest_id}/ignore''', {
            'characterId': self.char_id })

    
    def warehouse_gold(self):
        '''Check warehouse gold balance.'''
        data = self.rest.get(f'''/api/warehouse/{self.char_id}/gold''')
        if isinstance(data, dict):
            return data.get('gold', 0)

    
    def warehouse_deposit_gold(self, amount=None):
        return self.rest.post(f'''/api/warehouse/{self.char_id}/deposit-gold''', {
            'characterId': self.char_id,
            'amount': amount })

    
    def warehouse_withdraw_gold(self, amount=None):
        return self.rest.post(f'''/api/warehouse/{self.char_id}/withdraw-gold''', {
            'characterId': self.char_id,
            'amount': amount })

    
    def warehouse_items(self):
        '''Get items stored in warehouse.'''
        data = self.rest.get(f'''/api/warehouse/{self.char_id}/items''')
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and 'items' in data:
            return data['items']

    
    def warehouse_deposit_item(self, inventory_slot=None, quantity=None):
        return self.rest.post(f'''/api/warehouse/{self.char_id}/deposit''', {
            'characterId': self.char_id,
            'inventorySlot': inventory_slot,
            'quantity': quantity })

    
    def warehouse_withdraw_item(self, inventory_slot=None, quantity=None):
        return self.rest.post(f'''/api/warehouse/{self.char_id}/withdraw''', {
            'characterId': self.char_id,
            'inventorySlot': inventory_slot,
            'quantity': quantity })

    
    def craft_recipe(self, recipe_id=None, quantity=None):
        return self.rest.post('/api/crafting/craft', {
            'characterId': self.char_id,
            'recipeId': recipe_id,
            'quantity': quantity })

    
    async def disconnect(self):
        self._keep_running = False
        self.combat_enabled = False
        self.connected = False
        for task_attr in ('_combat_task', '_ws_task', '_reconnect_task'):
            task = getattr(self, task_attr, None)
            if task and not task.done():
                task.cancel()
                setattr(self, task_attr, None)
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None



class Analytics:
    '''Tracks per-character and cross-character statistics.'''
    
    def __init__(self, db_conn):
        self.db = db_conn
        self.chars = { }
        self.errors = []
        self.logs = []
        self.skill_usage = defaultdict(Counter)

    
    def char_connected(self, char_id = None, name = None, zone_id = None, gold = ('char_id', int, 'name', str, 'zone_id', int, 'gold', int)):
        self.chars[char_id] = {
            'name': name,
            'damage_dealt': 0,
            'damage_taken': 0,
            'healing_done': 0,
            'mobs_killed': 0,
            'kills_by_monster': Counter(),
            'xp_gained': 0,
            'gold_gained': 0,
            'start_gold': gold,
            'start_zone': zone_id,
            'start_time': time.time() }

    
    def track_damage(self, char_id=None, amount=None):
        if char_id not in self.chars:
            self.chars[char_id] = {'damage_dealt': 0, 'healing_done': 0, 'mobs_killed': 0, 'xp_gained': 0, 'gold_gained': 0, 'start_time': time.time(), 'kills_by_monster': Counter()}
        self.chars[char_id]['damage_dealt'] += amount or 0

    
    def track_healing(self, char_id=None, amount=None):
        if char_id not in self.chars:
            self.chars[char_id] = {'damage_dealt': 0, 'healing_done': 0, 'mobs_killed': 0, 'xp_gained': 0, 'gold_gained': 0, 'start_time': time.time(), 'kills_by_monster': Counter()}
        self.chars[char_id]['healing_done'] += amount or 0

    
    def track_kill(self, char_id=None, monster_name=None):
        if char_id not in self.chars:
            self.chars[char_id] = {'damage_dealt': 0, 'healing_done': 0, 'mobs_killed': 0, 'xp_gained': 0, 'gold_gained': 0, 'start_time': time.time(), 'kills_by_monster': Counter()}
        self.chars[char_id]['mobs_killed'] += 1
        if monster_name:
            self.chars[char_id]['kills_by_monster'][monster_name] += 1

    
    def track_rewards(self, char_id = None, xp = 0, gold = 0):
        if char_id not in self.chars:
            self.chars[char_id] = {'damage_dealt': 0, 'healing_done': 0, 'mobs_killed': 0, 'xp_gained': 0, 'gold_gained': 0, 'start_time': time.time(), 'kills_by_monster': Counter()}
        self.chars[char_id]['xp_gained'] += xp or 0
        self.chars[char_id]['gold_gained'] += gold or 0

    
    def track_skill_use(self, char_id=None, skill_name=None):
        pass

    
    def track_loot(self, char_id = None, item_name = None, rarity = ('char_id', int, 'item_name', str, 'rarity', str)):
        if rarity in ('rare', 'epic', 'legendary'):
            self.log(f'''[{char_id}] Rare loot: {item_name} ({rarity})''')
            return None

    
    def track_level_up(self, char_id=None, new_level=None):
        self.log(f'''[{char_id}] LEVEL UP → Lv{new_level}!''')

    
    def track_error(self, name=None, msg=None):
        self.errors.append(f'''[{name}] {msg}''')

    
    def log(self, msg=None):
        self.logs.append(msg)
        print(msg)

    
    def compute_rates(self, char_id=None, now=None):
        '''Compute per-minute rates for a character's session.'''
        if char_id not in self.chars:
            return {}
        if now is None:
            now = time.time()
        c = self.chars[char_id]
        start = c.get('start_time', now)
        elapsed = max(now - start, 1)
        elapsed_min = elapsed / 60.0
        elapsed_hr = elapsed / 3600.0
        return {
            'elapsed_min': elapsed_min,
            'dmg_per_min': c['damage_dealt'] / elapsed_min,
            'heal_per_min': c['healing_done'] / elapsed_min,
            'kills_per_min': c['mobs_killed'] / elapsed_min,
            'xp_per_hr': c['xp_gained'] / elapsed_hr if elapsed_hr > 0 else 0,
            'gold_per_min': c['gold_gained'] / elapsed_min,
        }

    
    def report(self, force=None):
        now = time.time()
        start_times = [c.get('start_time', now) for c in self.chars.values()]
        elapsed = min(start_times, default=now)
        elapsed = now - elapsed  # How long since earliest char connected
        elapsed = max(elapsed, 1)
        lines = []
        lines.append('======================================================================')
        lines.append(f'''📊 GRIMEAGE2 AGENT REPORT — {elapsed:.0f}s ({elapsed / 60:.1f} min)''')
        lines.append('======================================================================')
        grand = {
            'damage': 0,
            'healing': 0,
            'kills': 0,
            'xp': 0,
            'gold': 0 }
        for cid in sorted(self.chars):
            c = self.chars[cid]
            if not c.get('start_time'):
                continue
            rates = self.compute_rates(cid, now)
            lines.append(f'''\n  [{c['name']}] Session: {rates.get('elapsed_min', 0):.0f}min''')
            lines.append(f'''  {'=================================================='}''')
            lines.append(f'''  Damage: {c['damage_dealt']:>8,}  ({rates.get('dmg_per_min', 0):>8.1f}/min)''')
            lines.append(f'''  Heals:  {c['healing_done']:>8,}  ({rates.get('heal_per_min', 0):>8.1f}/min)''')
            lines.append(f'''  Kills:  {c['mobs_killed']:>8}  ({rates.get('kills_per_min', 0):>8.2f}/min)''')
            lines.append(f'''  XP:     {c['xp_gained']:>8,}  ({rates.get('xp_per_hr', 0):>8,}/hr)''')
            lines.append(f'''  Gold:   {c['gold_gained']:>8,}  ({rates.get('gold_per_min', 0):>8.1f}/min)''')
            if c['kills_by_monster']:
                top = c['kills_by_monster'].most_common(3)
                lines.append(f'''  Top kills: {', '.join(f'{n}({k})' for n, k in top)}''')
            if cid in self.skill_usage and self.skill_usage[cid]:
                top_skills = self.skill_usage[cid].most_common(3)
                lines.append('  Skills: ' + ', '.join(f'{n}({k})' for n, k in top_skills))
            # Accumulate grand totals
            grand['damage'] += c['damage_dealt']
            grand['healing'] += c['healing_done']
            grand['kills'] += c['mobs_killed']
            grand['xp'] += c['xp_gained']
            grand['gold'] += c['gold_gained']

        # Party totals (after all chars processed)
        lines.append('\n' + '=' * 70)
        lines.append(f'''📊 PARTY TOTAL — {len(self.chars)} chars''')
        lines.append(f'''  Damage: {grand['damage']:>10,}  Healing: {grand['healing']:>10,}''')
        lines.append(f'''  Kills:  {grand['kills']:>10}  XP: {grand['xp']:>10,}''')
        lines.append(f'''  Gold:   {grand['gold']:>10,}''')
        if self.errors:
            lines.append(f'''\n  ⚠️ Errors ({len(self.errors)}):''')
            for err in self.errors[-5:]:
                lines.append(f'''     {err}''')
        return '\n'.join(lines)



class AgentCoordinator:
    """
    Top-level agent that coordinates all characters:
    - Connects all characters
    - Forms a party
    - Assesses each character's gear/level
    - Finds optimal farming zones
    - Manages health & safety
    - Reports periodically
    """
    
    def __init__(self):
        self.rest = RestClient(ACCOUNT_EMAIL, ACCOUNT_PASSWORD)
        self.db = init_db()
        self.analytics = Analytics(self.db)
        self.world = WorldData(self.rest)
        self.chars = { }
        self._running = False
        self._main_loop_task = None
        self._last_report_time = 0
        self._report_interval = 60
        self._progression_check_interval = 120
        self._last_progression_check = 0
        self.combat_enabled = False
        self.start_time = time.time()
        self._last_seed_time = 0
        self._last_reseed_check = 0
        self._reseed_interval = 90
        self._party_zone_id = None
        self._last_straggler_check = 0

    
    async def start(self):
        '''Login, create agents, connect all, start main loop.'''
        self.analytics.log('🚀 AgentCoordinator starting...')
        self.rest.login()
        await asyncio.sleep(0.5)
        self.world.load()

        # Create CharacterAgents
        for cid, config in CHARACTERS.items():
            agent = CharacterAgent(cid, config, self.rest, self.analytics)
            self.chars[cid] = agent
            self.analytics.char_connected(cid, config['name'], None, 0)

        # Connect all characters
        self.analytics.log('Connecting all characters...')
        for cid in sorted(self.chars):
            agent = self.chars[cid]
            ok = await agent.connect()
            if ok:
                self.analytics.log(f'  ✓ {agent.name} connected')
            else:
                self.analytics.log(f'  ✗ {agent.name} connection failed')
            await asyncio.sleep(1)

        # Link partner references for cross-character awareness
        for cid, agent in self.chars.items():
            partners = {ocid: oa for ocid, oa in self.chars.items() if ocid != cid}
            agent.link_partner_agents(partners)

        # Initial assessment
        await self._initial_assessment()

        # Start main loop
        self._running = True
        self._main_loop_task = asyncio.create_task(self._main_loop())
        self.analytics.log('✅ AgentCoordinator running')

    async def _initial_assessment(self):
        '''First-time setup: seed monsters, form party, enable combat.'''
        self.analytics.log('📋 Initial assessment...')
        # Wait for all characters to be ready
        for cid, agent in self.chars.items():
            if not agent.connected:
                self.analytics.log(f'  ⏳ Waiting for {agent.name}...')

        # Log initial levels and gold
        for cid, agent in self.chars.items():
            self.analytics.log(f'  [{agent.name}] Lv{agent.level} | {agent.gold} gold | Zone {agent.current_zone_id}')
            self.analytics.track_rewards(cid, 0, agent.gold)

        # World load if not already
        if not self.world._loaded:
            self.world.load()

        # Seed monsters first (party + auto-farm don't mix)
        self.analytics.log('🌱 Initial monster seeding...')
        await self._coord_reseed()

    async def _main_loop(self):
        '''Main agent loop — runs every 5 seconds.'''
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.analytics.track_error('Coordinator', f'Main loop: {e}')
            await asyncio.sleep(5)

    async def _tick(self):
        '''Single agent cycle.'''
        now = time.time()

        # Safety check
        await self._check_safety()

        # Party integrity
        if now - getattr(self, '_last_party_check', 0) > 30:
            self._last_party_check = now
            await self._ensure_party()

        # Party cohesion: pull stragglers back to the party zone so the party
        # can actually form / stay together (reconnects, respawns, scatter).
        await self._travel_stragglers()

        # Monster reseed check (only when combat is running)
        if self.combat_enabled and now - self._last_reseed_check > 10:
            self._last_reseed_check = now
            await self._check_monsters()

        # Progression
        if now - self._last_progression_check > self._progression_check_interval:
            self._last_progression_check = now
            await self._progression_check()

        # Report
        if now - self._last_report_time > self._report_interval:
            self._last_report_time = now
            report = self.analytics.report()
            if report:
                self.analytics.log(report)

    async def _check_safety(self):
        '''Ensure all characters are alive and healthy.
        When combat AI is running, it handles rest/respawn itself.
        This is a safety net for edge cases.'''
        for cid, agent in self.chars.items():
            if not agent.connected:
                continue
            # Respawn if dead and no combat AI running
            if agent.is_dead and not agent.combat_enabled:
                await agent.ws_send('respawn', {})
                await asyncio.sleep(2)

    async def _check_monsters(self):
        '''Check monster counts across all chars. If total pool is low or
        a char is stuck with the same 1 monster for too long, trigger reseed.'''
        if not self.chars:
            return
        now = time.time()

        # Skip if we reseeded recently
        if now - self._last_seed_time < self._reseed_interval:
            return

        total_monsters = 0
        all_low = True
        stale_target = None

        for cid, agent in self.chars.items():
            if not agent.connected:
                continue
            agent._clean_monsters()
            mcount = len(agent.monsters)
            total_monsters += mcount

            # If any char has 2+ monsters, the zone is alive — don't reseed
            if mcount >= 2:
                all_low = False

            # Stale single-monster detection: same 1 monster for >45s
            if mcount == 1:
                stale_key = f'{cid}_mon_count'
                prev = getattr(self, stale_key, None)
                if prev == 1:
                    stale_since = getattr(self, f'{cid}_mon_stale_since', now)
                    if now - stale_since > 45:
                        stale_target = (cid, agent)
                        self.analytics.log(f'  🐌 {agent.name}: same 1 monster for >45s — forcing reseed')
                else:
                    setattr(self, f'{cid}_mon_stale_since', now)
                setattr(self, stale_key, mcount)

        # Trigger reseed if total pool is tiny OR a char is stale
        if total_monsters < 2 or stale_target or (total_monsters < 3 and all_low):
            self.analytics.log(f'🌀 Low monster pool ({total_monsters} total across all chars) — coordinated reseed...')
            await self._coord_reseed()

    async def _coord_reseed(self):
        '''Disband party → travel to common zone → seed monsters → re-form party → re-enable combat.'''
        if not self.chars:
            return

        # 1. Disable combat on all chars first
        for cid, agent in self.chars.items():
            if agent.combat_enabled:
                await agent.disable_combat()

        # 2. Disband party: lets leave on all chars
        sorted_ids = sorted(self.chars.keys())
        # Non-leaders leave first, then leader
        for cid in sorted_ids[1:]:
            agent = self.chars[cid]
            if agent.connected and agent.is_in_party:
                await agent.ws_send('party:leave', {})
                await asyncio.sleep(1)
        leader = self.chars[sorted_ids[0]]
        if leader.connected and leader.is_in_party:
            await leader.ws_send('party:leave', {})
            await asyncio.sleep(2)
        # Reset party state on all
        for cid, agent in self.chars.items():
            agent.is_in_party = False
            agent.party_members = {}

        # 3. Travel all chars to the SAME hunting zone (never a city).
        #    Old code picked the first char's _hunting_zone_id or current zone
        #    — usually zone 149 (Gludios city) at startup — then seeded in the
        #    city (0 monsters) and re-enabled combat, letting each agent's own
        #    zone finder scatter to different hunting grounds (no party, no
        #    shared gold, reseed ping-pong back to the city). Pick a real
        #    hunting_ground that every connected char can reach and that
        #    covers the lowest level in the party.
        min_level = None
        for cid in sorted_ids:
            agent = self.chars[cid]
            if agent.connected and agent.level:
                if min_level is None or agent.level < min_level:
                    min_level = agent.level
        target_zone = None
        # Preferred: a char's existing hunting zone that is a valid hunting
        # ground covering the whole party (lowest level included).
        for cid in sorted_ids:
            agent = self.chars[cid]
            if not agent.connected:
                continue
            hz = agent._hunting_zone_id or agent.current_zone_id
            zi = self.world.zones.get(hz)
            if (hz and zi and zi.zone_type == 'hunting_ground'
                    and min_level is not None
                    and zi.level_min <= min_level <= zi.level_max):
                target_zone = hz
                break
        if not target_zone:
            target_zone = self._pick_common_hunting_zone(sorted_ids, min_level)
        # Last resort: any non-city zone a connected char is in.
        if not target_zone:
            for cid in sorted_ids:
                agent = self.chars[cid]
                if agent.connected and agent.current_zone_id != 1:
                    zi = self.world.zones.get(agent.current_zone_id)
                    if zi and zi.zone_type != 'city':
                        target_zone = agent.current_zone_id
                        break
        if not target_zone:
            self.analytics.log('⚠️ No reachable hunting zone found — staying put')
        else:
            zi = self.world.zones.get(target_zone)
            self.analytics.log(f'📍 Party hunting zone: {target_zone} ({zi.name if zi else "?"})')
        # Pin every agent to the common zone so enable_combat's zone finder
        # doesn't scatter them to individual choices after re-enable.
        if target_zone:
            for cid in sorted_ids:
                agent = self.chars[cid]
                if agent.connected:
                    agent._hunting_zone_id = target_zone

        if target_zone:
            self._party_zone_id = target_zone  # _travel_stragglers keeps the party together on the main tick
            self.analytics.log(f'📍 Traveling all chars to zone {target_zone}...')
            # Round-up passes: chars mid-reconnect get skipped on the first
            # pass (the old code traveled once and gave up — stragglers sat in
            # the city forever, so no party could ever form). Re-travel every
            # connected char until all are in the party zone.
            for _pass in range(4):
                stragglers = []
                for cid in sorted_ids:
                    agent = self.chars[cid]
                    if agent.connected and agent.current_zone_id != target_zone:
                        stragglers.append(agent)
                if not stragglers:
                    break
                for agent in stragglers:
                    await self._travel_agent_to(agent, target_zone)
                await asyncio.sleep(8)
            # 3b. Bounded wait for every connected char to reach the party
            #     zone. Party invites require same zone, and enable_combat on a
            #     char that isn't there yet lets its own zone finder scatter it
            #     elsewhere (the old flow enabled combat immediately, so the
            #     party never formed and the tank died without heals).
            waited = 0
            while waited < 150:
                missing = [self.chars[cid] for cid in sorted_ids
                           if self.chars[cid].connected
                           and self.chars[cid].current_zone_id != target_zone]
                if not missing:
                    break
                for agent in missing:
                    await self._travel_agent_to(agent, target_zone)
                await asyncio.sleep(15)
                waited += 15

        # 4. Pick seed char that's ALREADY in the target zone
        seed_char = None
        for cid in sorted_ids:
            c = self.chars[cid]
            if c.connected and c.current_zone_id == target_zone:
                seed_char = c
                break
        # Fallback to first connected char
        if not seed_char and sorted_ids:
            seed_char = self.chars[sorted_ids[0]]

        if seed_char and seed_char.connected:
            # Defensive: never seed in a city — the server spawns no monsters
            # there, so a city seed always fails and wastes the 25s window.
            seed_zi = self.world.zones.get(seed_char.current_zone_id) if self.world.zones else None
            if seed_zi and seed_zi.zone_type == 'city':
                self.analytics.log(f'  ⚠️ {seed_char.name} still in city {seed_char.current_zone_id} — skipping seed (no monsters spawn in cities)')
            else:
                self.analytics.log(f'🌱 Seeding monsters on {seed_char.name} (zone {seed_char.current_zone_id})...')
                await seed_char.start_autofarm()
                await asyncio.sleep(0.5)
                if seed_char.is_autofarming:
                    # Await monster_spawned event — no polling
                    seed_char.monster_spawned.clear()
                    try:
                        await asyncio.wait_for(seed_char.monster_spawned.wait(), timeout=25)
                        self.analytics.log(f'  ✅ {seed_char.name}: {len(seed_char.monsters)} monsters appeared')
                    except asyncio.TimeoutError:
                        self.analytics.log(f'  ⚠️ {seed_char.name}: no monsters after 25s')
                    await seed_char.stop_autofarm()
                    seed_char.is_autofarming = False
                    self.analytics.log(f'  📊 Seeded {len(seed_char.monsters)} monsters on {seed_char.name}')
                else:
                    self.analytics.log(f'  ⚠️ Auto-farm rejected on {seed_char.name}')

        self._last_seed_time = time.time()

        # 5. Brief wait for zone spawns to propagate
        await asyncio.sleep(2)

        # 6. Re-form party (chars must be in same zone)
        await self._ensure_party()
        await asyncio.sleep(2)

        # 7. Re-enable combat on all chars
        for cid, agent in self.chars.items():
            if agent.connected and not agent.combat_enabled:
                await agent.enable_combat()
        self.analytics.log('✅ Coordinated reseed complete')

    
    def _pick_common_hunting_zone(self, sorted_ids, min_level):
        '''Choose a hunting ground reachable by the most connected chars that
        covers the party's lowest level (so every member can fight there).
        Scores:
          +100 per connected char that can BFS-reach the zone
          +40  per char that can reach it in a single hop (fast travel)
          -200 if it's a city (never selected)
        Returns a zone id, or None when nothing qualifies.'''
        if min_level is None:
            return None
        candidates = []
        for zid, zi in self.world.zones.items():
            if zi.zone_type != 'hunting_ground':
                continue
            if not (zi.level_min <= min_level <= zi.level_max):
                continue
            candidates.append((zid, zi))
        if not candidates:
            return None
        best = None
        best_score = -1
        for zid, zi in candidates:
            reach = 0
            direct = 0
            for cid in sorted_ids:
                agent = self.chars[cid]
                if not agent.connected or not agent.current_zone_id:
                    continue
                path = self.world.find_path(agent.current_zone_id, zid)
                if path:
                    reach += 1
                    if len(path) == 2:  # [from, to] == single hop
                        direct += 1
            score = reach * 100 + direct * 40
            if best is None or score > best_score:
                best = zid
                best_score = score
        return best

    async def _travel_agent_to(self, agent, target_zone):
        '''Travel a single agent to target_zone hop-by-hop (the server only
        accepts single-hop paths). Force-exits combat first (pitfall #45).
        Returns True if the agent is in the target zone when done.'''
        if agent.current_zone_id == target_zone:
            return True
        path = None
        if self.world._loaded and self.world.adjacency:
            path = self.world.find_path(agent.current_zone_id, target_zone)
        if not (path and len(path) >= 2):
            self.analytics.log(f'  ⚠️ {agent.name}: no path found from {agent.current_zone_id} to {target_zone}')
            return False
        self.analytics.log(f'  🗺️ {agent.name}: {agent.current_zone_id} → {target_zone} ({len(path)-1} hops)')
        if agent.is_in_combat or agent._target_attack_initiated:
            await agent.ws_send('combat:stop_attack', {})
            agent._target_attack_initiated = False
            agent.is_in_combat = False
            await asyncio.sleep(2.0)
        agent.combat_state = 'TRAVELING'
        for hop_idx in range(1, len(path)):
            hop = path[hop_idx]
            agent.travel_complete.clear()
            await agent.ws_send('start_travel', {'path': [hop]})
            try:
                await asyncio.wait_for(agent.travel_complete.wait(), timeout=40)
            except asyncio.TimeoutError:
                self.analytics.log(f'  ⚠️ {agent.name} travel timeout at hop {hop} (stuck at {agent.current_zone_id})')
                break
        if agent.current_zone_id != target_zone:
            self.analytics.log(f'  ⚠️ {agent.name} arrived at {agent.current_zone_id} (target {target_zone})')
            # Fallback: the agent's own finder, with the hunting zone pinned
            # back to the party zone afterwards so it doesn't scatter.
            agent.travel_complete.clear()
            await agent._find_and_travel_hunting_zone()
            try:
                await asyncio.wait_for(agent.travel_complete.wait(), timeout=40)
            except asyncio.TimeoutError:
                pass
            agent._hunting_zone_id = target_zone
        return agent.current_zone_id == target_zone

    async def _travel_stragglers(self):
        '''Round up any connected char that drifted out of the party zone
        (reconnects, respawn-to-town, individual zone-finder scatter). Runs on
        the main tick so the party stays together — without it a char that
        reconnects after the reseed's travel pass sits in the city forever.'''
        tz = getattr(self, '_party_zone_id', None)
        if not tz or not self.chars:
            return
        now = time.time()
        if now - getattr(self, '_last_straggler_check', 0) < 15:
            return
        self._last_straggler_check = now
        sorted_ids = sorted(self.chars.keys())
        for cid in sorted_ids:
            agent = self.chars[cid]
            if not agent.connected or agent.is_dead:
                continue
            if agent.combat_state == 'TRAVELING':
                continue  # already moving
            if agent.current_zone_id == tz:
                agent._hunting_zone_id = tz  # keep pinned
                continue
            # Don't drag a char out of a fight mid-engagement.
            if agent.is_in_combat or agent._target_attack_initiated:
                continue
            self.analytics.log(f'🚚 {agent.name}: pulling back to party zone {tz} (at {agent.current_zone_id})')
            agent._hunting_zone_id = tz
            await self._travel_agent_to(agent, tz)

    async def _ensure_party(self):
        '''Check party status and reform if needed.'''
        # Find the party leader (first character)
        if not self.chars:
            return
        sorted_ids = sorted(self.chars.keys())
        leader_id = sorted_ids[0]
        leader = self.chars[leader_id]

        # If leader is disconnected, skip
        if not leader.connected:
            return

        # If leader is in a party, assume it's fine
        if leader.is_in_party:
            return

        # Try to form party: leader invites others
        for cid in sorted_ids[1:]:
            member = self.chars[cid]
            if not member.connected:
                continue
            # Create invite_received event for this member if needed
            if not hasattr(member, '_invite_received_event'):
                member._invite_received_event = asyncio.Event()
            member._invite_received_event.clear()
            member._pending_invite_from = None
            member.party_joined.clear()
            
            # Send invite
            await leader.party_invite(member.name)
            
            # Wait for invite_received event with timeout
            try:
                await asyncio.wait_for(member._invite_received_event.wait(), timeout=3)
            except asyncio.TimeoutError:
                self.analytics.log(f'  ⚠️ {member.name} invite timed out')
                continue
            
            # Accept if invite was received
            if getattr(member, '_pending_invite_from', None) == leader_id:
                await member.party_accept(leader_id)
                # Wait for party state to confirm join (poll is_in_party)
                self.analytics.log(f'  Waiting for {member.name} to join party...')
                joined = False
                for attempt in range(10):  # 5s total
                    await asyncio.sleep(0.5)
                    if member.is_in_party or leader.is_in_party:
                        joined = True
                        break
                if joined:
                    self.analytics.log(f'  ✓ {member.name} joined party')
                else:
                    # Accept may have failed (expired) — retry once
                    self.analytics.log(f'  ⚠️ {member.name} party join timed out, retrying...')
                    member._invite_received_event.clear()
                    member._pending_invite_from = None
                    member.party_joined.clear()
                    await leader.party_invite(member.name)
                    try:
                        await asyncio.wait_for(member._invite_received_event.wait(), timeout=3)
                    except asyncio.TimeoutError:
                        continue
                    if getattr(member, '_pending_invite_from', None) == leader_id:
                        await member.party_accept(leader_id)
                        for attempt in range(10):
                            await asyncio.sleep(0.5)
                            if member.is_in_party or leader.is_in_party:
                                self.analytics.log(f'  ✓ {member.name} joined party (retry)')
                                break

    async def _progression_check(self):
        '''Check gear, zones, and suggest improvements.
        Only recommends directly-reachable zones (server only supports single-hop travel).'''
        for cid, agent in self.chars.items():
            if not agent.connected:
                continue
            # Refresh stats
            stats = agent.fetch_stats()
            if stats:
                # Check if zone needs updating
                if agent.current_zone_id and agent.level:
                    # Get zones directly connected to current zone
                    nearby = self.world.get_nearby_zones(agent.current_zone_id, max_hops=1)
                    if not nearby:
                        continue
                    connected_ids = set(nearby.keys())
                    # Filter best zones to only directly reachable ones
                    best_all = self.world.find_best_zones(agent.level, 'hunting_ground', 10)
                    reachable_best = [z for z in best_all if z['id'] in connected_ids]
                    if reachable_best and reachable_best[0]['id'] != agent.current_zone_id:
                        self.analytics.log(f'[{agent.name}] Better zone available: {reachable_best[0]["id"]} (currently {agent.current_zone_id})')

    async def stop(self):
        '''Graceful shutdown.'''
        self.analytics.log('🛑 AgentCoordinator shutting down...')
        self._running = False
        if self._main_loop_task and not self._main_loop_task.done():
            self._main_loop_task.cancel()
            self._main_loop_task = None
        for cid, agent in self.chars.items():
            await agent.disconnect()
        self.analytics.log('✅ AgentCoordinator stopped')

    
    async def cmd_zones(self):
        '''Show zone recommendations for all chars.'''
        for cid, agent in self.chars.items():
            if agent.level:
                best = self.world.find_best_zones(agent.level, 'hunting_ground', 3)
                if best:
                    zones = ', '.join('{} ({})'.format(z['id'], z['name']) for z in best)
                    self.analytics.log(f'[{agent.name}] Lv{agent.level} best zones: {zones}')

    async def cmd_gear(self, char_id=None):
        '''Show gear status.'''
        targets = [char_id] if char_id else list(self.chars.keys())
        for cid in targets:
            agent = self.chars.get(cid)
            if not agent:
                continue
            inv = agent.fetch_inventory()
            if inv:
                equipped = inv.get('equippedItems', [])
                self.analytics.log(f'[{agent.name}] Equipped:')
                for item in equipped:
                    slot = item.get('slot', '?')
                    name = item.get('itemName', '?')
                    self.analytics.log(f'  {slot}: {name}')

    async def cmd_report(self):
        '''Show full analytics report.'''
        report = self.analytics.report()
        if report:
            self.analytics.log(report)

    async def cmd_inventory(self, char_id=None):
        '''Show inventory for a character.'''
        if char_id not in self.chars:
            return
        agent = self.chars[char_id]
        inv = agent.fetch_inventory()
        if inv:
            items = inv.get('items', inv.get('bagItems', []))
            self.analytics.log(f'[{agent.name}] Inventory ({len(items)} items):')
            for item in items[:20]:
                name = item.get('itemName', '?')
                qty = item.get('quantity', 1)
                self.analytics.log(f'  {name} x{qty}')

    async def cmd_rest_config(self, hp_pct=None, mp_pct=None):
        '''Configure auto-rest for all characters.'''
        for cid, agent in self.chars.items():
            if hp_pct is not None:
                agent.rest_hp_threshold = hp_pct / 100.0
            if mp_pct is not None:
                agent.rest_mp_threshold = mp_pct / 100.0
        self.analytics.log(f'Rest thresholds: HP<={hp_pct}% MP<={mp_pct}%')

    async def cmd_buy(self, char_id=None, item_id=None, npc_id=8, quantity=1):
        '''Buy item from shop.'''
        if char_id in self.chars:
            result = self.chars[char_id].buy_item(npc_id, item_id, quantity)
            self.analytics.log(f'Buy result: {result}')

    async def cmd_quests(self, char_id=None):
        '''Show available and active quests for a character.'''
        if char_id not in self.chars:
            return
        agent = self.chars[char_id]
        active = agent.fetch_active_quests()
        if active:
            self.analytics.log(f'[{agent.name}] Active quests:')
            for q in active:
                self.analytics.log('  {} ({})'.format(q.get('name', '?'), q.get('status', '?')))
        available = agent.fetch_available_quests()
        if available:
            self.analytics.log(f'[{agent.name}] Available quests:')
            for q in available[:5]:
                self.analytics.log('  {}'.format(q.get('name', '?')))

    async def cmd_accept_quest(self, char_id=None, quest_id=None):
        if char_id in self.chars and quest_id:
            result = self.chars[char_id].accept_quest(quest_id)
            self.analytics.log(f'Accept quest {quest_id}: {result}')

    async def cmd_claim_quest(self, char_id=None, quest_id=None):
        if char_id in self.chars and quest_id:
            result = self.chars[char_id].claim_quest(quest_id)
            self.analytics.log(f'Claim quest {quest_id}: {result}')

    async def cmd_sell_junk(self, char_id=None):
        '''Auto-sell vendor trash.'''
        targets = [char_id] if char_id else list(self.chars.keys())
        for cid in targets:
            agent = self.chars.get(cid)
            if not agent:
                continue
            agent.fetch_inventory()
            sold = agent.auto_sell_junk(8)
            if sold:
                self.analytics.log(f'[{agent.name}] Sold {sold} junk items')

    async def cmd_warehouse(self, char_id=None):
        '''Show warehouse status.'''
        if char_id in self.chars:
            gold = self.chars[char_id].warehouse_gold()
            self.analytics.log(f'[{self.chars[char_id].name}] Warehouse gold: {gold:,}')

    async def cmd_warehouse_deposit_gold(self, char_id=None, amount=None):
        if char_id in self.chars and amount:
            result = self.chars[char_id].warehouse_deposit_gold(amount)
            self.analytics.log(f'Deposit {amount} gold: {result}')

    async def cmd_warehouse_withdraw_gold(self, char_id=None, amount=None):
        if char_id in self.chars and amount:
            result = self.chars[char_id].warehouse_withdraw_gold(amount)
            self.analytics.log(f'Withdraw {amount} gold: {result}')

    async def cmd_transfer_gold(self, from_id=None, to_id=None, amount=None):
        '''Transfer gold from one char to another via warehouse (both need to be in a city).'''
        if from_id in self.chars and to_id in self.chars and amount:
            # Withdraw from source, deposit to target via warehouse
            result = self.chars[from_id].warehouse_withdraw_gold(amount)
            self.analytics.log(f'Transfer {amount} gold from {self.chars[from_id].name}: {result}')
            # Note: target needs to be in same city to withdraw

    async def cmd_craft(self, char_id=None, recipe_id=None, quantity=1):
        if char_id in self.chars and recipe_id:
            result = self.chars[char_id].craft_recipe(recipe_id, quantity)
            self.analytics.log(f'Craft {recipe_id} x{quantity}: {result}')

    async def cmd_combat(self, action=None, char_id=None):
        '''Enable/disable combat AI for specific character or all.'''
        if action == 'enable':
            targets = [char_id] if char_id else list(self.chars.keys())
            for cid in targets:
                if cid in self.chars:
                    await self.chars[cid].enable_combat()
            if not char_id:
                self.combat_enabled = True
        elif action == 'disable':
            targets = [char_id] if char_id else list(self.chars.keys())
            for cid in targets:
                if cid in self.chars:
                    await self.chars[cid].disable_combat()
            if not char_id:
                self.combat_enabled = False

    async def cmd_combat_status(self):
        '''Show combat AI status for all characters.'''
        for cid, agent in self.chars.items():
            state = agent.combat_state if agent.combat_enabled else 'DISABLED'
            self.analytics.log(f'[{agent.name}] Combat: {state} | HP:{agent.hp}/{agent.max_hp} MP:{agent.mp}/{agent.max_mp}')



async def main():
    '''Main entry point — start AgentCoordinator and handle CLI input.'''
    coord = AgentCoordinator()
    try:
        await coord.start()
        # CLI input loop
        while coord._running:
            cmd = await _async_input()
            if not cmd:
                continue
            parts = cmd.strip().split()
            if not parts:
                continue
            command = parts[0]
            args = parts[1:]

            if command == 'combat' and len(args) >= 1:
                action = args[0]
                char_id = int(args[1]) if len(args) > 1 else None
                await coord.cmd_combat(action, char_id)
            elif command == 'status':
                await coord.cmd_combat_status()
            elif command == 'report':
                await coord.cmd_report()
            elif command == 'quit' or command == 'exit':
                break
            elif command == 'help':
                print('Commands: combat enable/disable [char_id], status, report, quit')
    finally:
        await coord.stop()


async def _async_input():
    '''Read line from stdin in a thread pool (non-blocking in async context).'''
    import sys
    loop = asyncio.get_event_loop()
    line = await loop.run_in_executor(None, sys.stdin.readline)
    return line.strip()

if __name__ == '__main__':
    asyncio.run(main())
