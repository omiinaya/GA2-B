#!/usr/bin/env python3
"""
GrimeAge2 Brain v3 — Consolidated automation supervisor.
Runs as cron job (every 5min). Handles:
  - Status reporting (always on)
  - Auto-equip missing/better weapons
  - Zone progression with BFS pathfinding
  - Gear check + upgrade suggestions
  - Quest status + auto-accept
  - Party quest notification
"""
import json, sys, time, os
import urllib.request
import asyncio
from collections import deque
import subprocess

# === CONFIG ===
# Credentials loaded in priority order:
# 1. GR2_EMAIL / GR2_PASSWORD environment variables
# 2. .env file in the same directory (KEY=VALUE format, not committed)
CREDENTIALS = {}
email = os.environ.get('GR2_EMAIL')
password = os.environ.get('GR2_PASSWORD')
if email and password:
    CREDENTIALS = {"email": email, "password": password}
else:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        k, v = line.split('=', 1)
                        if k == 'GR2_EMAIL':
                            email = v
                        elif k == 'GR2_PASSWORD':
                            password = v
    if email and password:
        CREDENTIALS = {"email": email, "password": password}
    else:
        print("CREDENTIAL LOAD FAILED")
        print("Set GR2_EMAIL and GR2_PASSWORD env vars, or create .env file")
        sys.exit(1)
API_BASE = "https://grimeage2.com"
WS_BASE = "wss://grimeage2.com"
PID_FILE = os.path.expanduser('~/.hermes/gr2-combat-daemon.pid')
LOG_FILE = os.path.expanduser('~/.hermes/gr2-combat-daemon.log')

# Zone progression tiers: (level_min, level_max, [best_zone, ok_zone, fallback_zone])
PROGRESSION = [
    (5, 10,  [44318, 44213, 44221]),
    (10, 15, [44388, 44293, 44372]),
    (15, 20, [44341, 44402, 44251]),
    (20, 22, [53, 58, 63]),
    (20, 30, [50107, 50094, 50176]),
    (21, 24, [52817, 52715, 52832]),
    (23, 25, [69, 44, 132]),
    (26, 28, [23, 117, 152]),
    (28, 30, [38, 50, 82]),
    (30, 35, [50076, 39, 30968]),
    (30, 40, [44957, 52771, 52901]),
    (31, 39, [24453, 24438, 24458]),
    (33, 35, [92, 32, 76]),
    (35, 40, [30967]),
    (36, 38, [26, 88, 115]),
    (36, 42, [52901, 52784, 52842]),
    (38, 40, [18, 130, 46373]),
]

# Recommended weapon upgrades per class
WEAPON_TREE = {
    "wizard": [
        {"name": "Wooden Staff",       "matk": 14,  "price": 11472,   "source": "shop",           "min_lv": 0},
        {"name": "Oak Staff",          "matk": 32,  "price": 137659,  "source": "shop",           "min_lv": 5},
        {"name": "Arcane Staff",       "matk": 55,  "price": 275318,  "source": "shop/old pirate", "min_lv": 15},
        {"name": "Crystal-Woven Staff","matk": 80,  "price": 250000,  "source": "craft/marshland toad", "min_lv": 20},
        {"name": "Archmage's Staff",   "matk": 110, "price": 500000,  "source": "craft",           "min_lv": 30},
        {"name": "Eldritch Staff",     "matk": 143, "price": 8000000, "source": "craft (8M)",       "min_lv": 40},
        {"name": "Abyssal Staff",      "matk": 180, "price": 15000000,"source": "craft (15M)",      "min_lv": 50},
    ],
    "fighter": [
        {"name": "Short Sword",        "patk": 12,  "price": 12964,   "source": "shop",           "min_lv": 0},
        {"name": "Broad Sword",        "patk": 28,  "price": 151242,  "source": "shop",           "min_lv": 5},
        {"name": "Knight's Sword",     "patk": 48,  "price": 302484,  "source": "shop",           "min_lv": 15},
        {"name": "Mithril Longsword",  "patk": 72,  "price": 250000,  "source": "craft/bandit scout",   "min_lv": 23},
        {"name": "Runic Blade",        "patk": 96,  "price": 500000,  "source": "craft",           "min_lv": 28},
        {"name": "Eldritch Blade",     "patk": 125, "price": 8000000, "source": "craft (8M)",       "min_lv": 40},
        {"name": "Abyssal Blade",      "patk": 158, "price": 15000000,"source": "craft (15M)",      "min_lv": 50},
    ],
}

# Armor progression by class — tracks equipped set vs recommended upgrades
ARMOR_TREE = {
    "wizard": [
        {"name": "Apprentice Set",     "mdef": 6,  "pdef": 5,  "price": 0,     "source": "starter",      "min_lv": 0},
        {"name": "Silk Set",           "mdef": 16, "pdef": 23, "price": 120000,"source": "shop/drops",    "min_lv": 5},
        {"name": "Mithril Robe Set",   "mdef": 31, "pdef": 36, "price": 150000,"source": "craft/raids",  "min_lv": 20, "bonus": "+300 MP, +1 INT, +10% M.Atk"},
        {"name": "Karmian Set",        "mdef": 45, "pdef": 50, "price": 3000000,"source": "craft/ Sylvara","min_lv": 40, "bonus": "+600 MP, +2 INT, +10% M.Def"},
        {"name": "Demon Set",          "mdef": 45, "pdef": 50, "price": 3000000,"source": "craft/ Sylvara","min_lv": 40, "bonus": "+15% M.Atk, +3 INT, +2 WIT"},
    ],
    "fighter": [
        {"name": "Leather Set",        "pdef": 8,  "mdef": 6,  "price": 0,     "source": "starter",      "min_lv": 0},
        {"name": "Hardened Set",       "pdef": 31, "mdef": 16, "price": 120000,"source": "shop/drops",    "min_lv": 5},
        {"name": "Manticore Set",      "pdef": 49, "mdef": 31, "price": 150000,"source": "craft/raids",  "min_lv": 20, "bonus": "+200 MP, +1 DEX, +5% Eva, +5% Atk.Spd"},
        {"name": "Plated Leather Set", "pdef": 67, "mdef": 45, "price": 3000000,"source": "craft/ Sylvara","min_lv": 40, "bonus": "+300 HP, +2 STR, +10% P.Atk, +5% P.Def"},
        {"name": "Theca Set",          "pdef": 67, "mdef": 45, "price": 3000000,"source": "craft/ Sylvara","min_lv": 40, "bonus": "+400 MP, +2 DEX, +10% Eva, +10% Atk.Spd"},
    ],
    "tank": [
        {"name": "Steel Set",          "pdef": 37, "mdef": 16, "price": 120000,"source": "shop/drops",    "min_lv": 5},
        {"name": "Brigandine Set",     "pdef": 67, "mdef": 31, "price": 460000,"source": "craft",         "min_lv": 20},
        {"name": "Chain Mail Set",     "pdef": 95, "mdef": 45, "price": 9200000,"source": "craft",        "min_lv": 40},
        {"name": "Composite Set",      "pdef": 95, "mdef": 45, "price": 9200000,"source": "craft",        "min_lv": 40},
    ],
}

# Shop IDs with cheapest Oak Staff
BEST_STAFF_SHOP = 8  # Oak Staff 137,659g
BEST_ARCANE_SHOP = 8  # Arcane Staff 275,318g

# Item IDs for shop buys
STAFF_ITEM_IDS = {
    "oak": 86,
    "arcane": 87,
    "wooden": 85,
}

# Accessory slots each character can equip
ACCESSORY_SLOTS = ["ring1", "ring2", "amulet"]
ACCESSORY_ITEM_IDS = {
    "silver_ring": 111,
    "silver_amulet": 110,
}
ACCESSORY_TREE = [
    {"name": "Silver Ring",  "slot": "ring1", "matk": 3, "patk": 3, "mdef": 0, "pdef": 0, "price": 19034, "min_lv": 5},
    {"name": "Silver Amulet", "slot": "amulet", "matk": 0, "patk": 0, "mdef": 3, "pdef": 3, "price": 18072, "min_lv": 5},
]

# Crafting recipes for material upgrades
MATERIAL_RECIPES = [
    {"name": "Reinforced Bone",    "recipeId": 7,    "cost": 500,   "input": "Bone Fragment",  "input_qty": 10},
    {"name": "Mithril Alloy",      "recipeId": 6,    "cost": 1000,  "input": "Iron Ore",       "input_qty": 10},
    {"name": "Hardened Stem",      "recipeId": 9180, "cost": 1000,  "input": "Stem",           "input_qty": 10},
    {"name": "Leather",            "recipeId": 4,    "cost": 1500,  "input": "Animal Skin",    "input_qty": 15},
    {"name": "Magical Dust",       "recipeId": 5,    "cost": 20000, "input": "Magical Shard",  "input_qty": 2},
    {"name": "Enchanted Crystal",  "recipeId": 3,    "cost": 15000, "input": "Dark Crystal",   "input_qty": 2},
]

# Gear recipes worth tracking at low-mid levels
GEAR_RECIPES = {
    "wizard": [
        {"name": "Crystal-Woven Staff", "recipeId": 16, "cost": 250000, "matk": 80,
         "mats": {"Enchanted Crystal": 2, "Magical Dust": 6, "Mithril Alloy": 5, "Magic Crystal": 250}},
        {"name": "Mithril Robe", "recipeId": 1376, "cost": 150000, "desc": "+10% M.Atk, +300 MP, +1 INT",
         "mats": {"Dark Crystal": 4, "Mithril Alloy": 5, "Magical Dust": 8, "Magic Crystal": 200}},
    ],
    "fighter": [
        {"name": "Mithril Stiletto", "recipeId": 26, "cost": 250000, "patk": 54,
         "mats": {"Enchanted Crystal": 1, "Leather": 2, "Magical Dust": 5, "Mithril Alloy": 6, "Magic Crystal": 250}},
        {"name": "Manticore Tunic", "recipeId": 1367, "cost": 150000, "desc": "+200 MP, +1 DEX, +5% Evasion, +5% Atk.Spd",
         "mats": {"Enchanted Crystal": 2, "Leather": 8, "Magical Shard": 6, "Magic Crystal": 200}},
    ],
}

# Tracked material names for inventory scanning
MATERIAL_NAMES = [
    "Animal Skin", "Bone Fragment", "Iron Ore", "Stem",
    "Magical Shard", "Dark Crystal", "Magic Crystal",
    "Reinforced Bone", "Mithril Alloy", "Hardened Stem", "Leather",
    "Magical Dust", "Enchanted Crystal", "Stone of Purity",
]


# === API HELPERS ===
def api_post(path, data, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(
        f'{API_BASE}{path}',
        data=json.dumps(data).encode() if data else None,
        headers=headers,
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def api_get(path, token):
    req = urllib.request.Request(
        f'{API_BASE}{path}',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def api_put(path, data, token):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(
        f'{API_BASE}{path}',
        data=json.dumps(data).encode(),
        headers=headers,
        method='PUT',
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        return json.loads(raw) if raw.strip() else {}


# === STATE ===
class State:
    def __init__(self):
        self.token = None
        self.chars = []
        self.zones = {}      # id -> zone object
        self.adj = {}        # zone adjacency graph
        self.lines = []      # report buffer
        self.total_gold = 0

    def log(self, msg):
        self.lines.append(msg)

    def login(self):
        resp = api_post('/api/auth/login', CREDENTIALS)
        self.token = resp.get('accessToken', '')
        if not self.token:
            self.log("LOGIN FAILED")
            return False
        return True

    def load_world(self):
        map_data = api_get('/api/world/map', self.token)
        self.zones = {z['id']: z for z in map_data.get('zones', [])}
        for c in map_data.get('connections', []):
            a, b = c['zoneAId'], c['zoneBId']
            self.adj.setdefault(a, set()).add(b)
            self.adj.setdefault(b, set()).add(a)

    def load_chars(self):
        self.chars = api_get('/api/characters', self.token)
        self.total_gold = sum(c.get('gold', 0) for c in self.chars)
        return self.chars

    def get_zone_name(self, zid):
        z = self.zones.get(zid, {})
        return z.get('name', f'Zone#{zid}')

    def get_zone_level_range(self, zid):
        z = self.zones.get(zid, {})
        return z.get('levelRangeMin', 0), z.get('levelRangeMax', 99)

    def bfs_path(self, start, end, max_hops=20):
        """BFS shortest path through zone connections."""
        if start == end:
            return [start]
        q = deque([(start, [start])])
        visited = {start}
        while q:
            nid, path = q.popleft()
            if nid == end:
                return path
            for nb in self.adj.get(nid, []):
                if nb not in visited and len(path) < max_hops:
                    visited.add(nb)
                    q.append((nb, path + [nb]))
        return None

    def get_best_zone_ids(self, level):
        """Find the best zone IDs for a given level (best -> fallback)."""
        for lmin, lmax, zone_ids in PROGRESSION:
            if lmin <= level <= lmax:
                return zone_ids
        return None

    def find_weapon_upgrade(self, char_class, current_matk=0, current_patk=0, min_lv=0):
        """Find next weapon upgrade for a character."""
        tree = WEAPON_TREE.get(char_class, [])
        if char_class == "wizard":
            return [w for w in tree if w.get('matk', 0) > current_matk and w['min_lv'] <= min_lv]
        else:
            return [w for w in tree if w.get('patk', 0) > current_patk and w['min_lv'] <= min_lv]

    def find_armor_upgrade(self, char_class, current_pdef=0, current_mdef=0, min_lv=0):
        """Find next armor set upgrade. Returns list of upgrades sorted by pdef."""
        tree = ARMOR_TREE.get(char_class, [])
        if char_class == 'tank':
            return [a for a in tree if a.get('pdef', 0) > current_pdef and a['min_lv'] <= min_lv]
        else:
            return [a for a in tree if a.get('pdef', 0) > current_pdef and a['min_lv'] <= min_lv]


# === WS COMMAND ===
async def ws_travel(token, char_id, target_zone, timeout=45):
    """Travel to target zone via WebSocket. Returns True/False/error string."""
    try:
        import websockets
    except ImportError:
        return "no websockets library"

    # Use destination-only approach: server knows current location
    ws_url = f"{WS_BASE}/ws?token={token}&characterId={char_id}"
    try:
        async with asyncio.timeout(timeout):
            async with websockets.connect(ws_url, ping_interval=10, ping_timeout=5) as ws:
                # Drain init messages
                for _ in range(10):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=0.5)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        break

                # Stop combat first (blocks travel)
                await ws.send(json.dumps({
                    "type": "combat:stop_attack",
                    "payload": {},
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
                }))
                await asyncio.sleep(0.5)

                # Send travel
                await ws.send(json.dumps({
                    "type": "start_travel",
                    "payload": {"path": [target_zone]},
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
                }))

                # Wait for arrival
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=60)
                    data = json.loads(msg)
                    if data.get('type') == 'travel_complete':
                        return True
                    elif data.get('type') == 'error':
                        return f"travel error: {data.get('payload', {}).get('message', 'unknown')}"

    except asyncio.TimeoutError:
        return "timed out"
    except Exception as e:
        return str(e)


# === MAIN ===
async def main():
    # ─────────────────────────────────────────────────
    # 0a. CRON LOCK WATCHDOG — Remove stale .tick.lock
    #     Prevents cron scheduler deadlock (pitfall #22).
    #     The lock file blocks ALL cron jobs, including this brain.
    # ─────────────────────────────────────────────────
    lockfile = os.path.expanduser('~/.hermes/cron/.tick.lock')
    if os.path.exists(lockfile):
        try:
            age = time.time() - os.path.getmtime(lockfile)
            if age > 300:  # 5 min stale
                os.remove(lockfile)
                print(f"  🐕 Removed stale .tick.lock (age: {int(age)}s)")
        except OSError:
            pass

    state = State()

    # Login
    if not state.login():
        print("LOGIN FAILED")
        sys.exit(1)

    # Load world data
    try:
        state.load_world()
    except Exception as e:
        print(f"WORLD LOAD FAILED: {e}")
        sys.exit(1)

    # Load characters
    try:
        chars = state.load_chars()
    except Exception as e:
        print(f"CHAR LOAD FAILED: {e}")
        sys.exit(1)

    # Build zone name lookup
    znames = {}
    for c in chars:
        znames[c['currentZoneId']] = state.get_zone_name(c['currentZoneId'])

    # ─────────────────────────────────────────────────
    # 0. SUPERVISE COMBAT DAEMON
    # ─────────────────────────────────────────────────
    daemon_pid_file = os.path.expanduser('~/.hermes/gr2-combat-daemon.pid')
    daemon_script = os.path.expanduser('~/.hermes/scripts/gr2-combat-daemon.py')
    daemon_running = False
    if os.path.exists(daemon_pid_file):
        try:
            with open(daemon_pid_file) as f:
                pid = int(f.read().strip())
            # Check if pid is alive and is our daemon
            os.kill(pid, 0)  # signal 0 = check existence
            daemon_running = True
        except (OSError, ValueError):
            # PID stale — remove stale file
            try:
                os.remove(daemon_pid_file)
            except OSError:
                pass
    if not daemon_running:
        print(f"  🔧 Combat daemon not running — starting it...")
        subprocess.Popen(
            [sys.executable, daemon_script],
            stdout=open(LOG_FILE, 'a'),
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True
        )
        print(f"  ✅ Combat daemon launched (check logs: {LOG_FILE})")
    else:
        pid = int(open(daemon_pid_file).read().strip())
        print(f"  ✅ Combat daemon running (PID {pid})")

    # ─────────────────────────────────────────────────
    # 1. CHARACTER STATUS REPORT
    # ─────────────────────────────────────────────────
    state.log("═" * 50)
    state.log("CHARACTER STATUS")
    state.log("─" * 50)

    # Enrich with inventory data
    for c in chars:
        cid = c['id']
        name = c['name']
        lv = c['level']
        cls = c.get('class', '?')
        hp = c.get('hp', 0)
        mhp = c.get('maxHp', 1)
        mp = c.get('mp', 0)
        mmp = c.get('maxMp', 1)
        gold = c.get('gold', 0)
        xp = c.get('xp', 0)
        zid = c['currentZoneId']
        zn = state.get_zone_name(zid)
        af = c.get('isAutoFarming', False)
        st = c.get('state', '?')
        dead = c.get('state') == 'dead' or hp <= 0

        # Get inventory for gear checks
        try:
            inv = api_get(f'/api/inventory/{cid}', state.token)
            c['_inv'] = inv
        except Exception:
            c['_inv'] = {'equipped': [], 'bag': []}

        equipped = c['_inv'].get('equipped', [])
        equipped_slots = {e.get('equippedSlot', e.get('slot', '?')): e for e in equipped}

        # Get equipped weapon
        weapon_item = (equipped_slots.get('main_hand') or
                       equipped_slots.get('two_hand') or {})
        wpn_name = weapon_item.get('itemName', 'NONE')
        wpn_stats = {}
        if weapon_item.get('statsJson'):
            try:
                wpn_stats = json.loads(weapon_item['statsJson'])
            except Exception:
                pass

        c['_equipped'] = equipped_slots
        c['_weapon'] = wpn_name
        c['_weapon_stats'] = wpn_stats

        # Compute armor stats from equipped pieces
        armor_stats = {"pdef": 0, "mdef": 0, "count": 0}
        for slot_name in ['body', 'legs', 'head', 'gloves', 'boots']:
            piece = equipped_slots.get(slot_name, {})
            if piece and piece.get('statsJson'):
                try:
                    ps = json.loads(piece['statsJson'])
                    armor_stats['pdef'] += ps.get('p_def', 0)
                    armor_stats['mdef'] += ps.get('m_def', 0)
                    armor_stats['count'] += 1
                except Exception:
                    pass
        c['_armor_stats'] = armor_stats

        # Determine effective armor set name
        body_piece = equipped_slots.get('body', {})
        body_name = body_piece.get('itemName', '')
        if 'apprentice' in body_name.lower():
            c['_armor_set'] = 'Apprentice'
        elif 'silk' in body_name.lower():
            c['_armor_set'] = 'Silk'
        elif 'mithril' in body_name.lower() and 'robe' in body_name.lower():
            c['_armor_set'] = 'Mithril Robe'
        elif 'hardened' in body_name.lower():
            c['_armor_set'] = 'Hardened'
        elif 'manticore' in body_name.lower():
            c['_armor_set'] = 'Manticore'
        elif 'steel' in body_name.lower():
            c['_armor_set'] = 'Steel'
        elif 'brigandine' in body_name.lower():
            c['_armor_set'] = 'Brigandine'
        elif 'chain mail' in body_name.lower() or 'chain' in body_name.lower():
            c['_armor_set'] = 'Chain Mail'
        elif 'leather' in body_name.lower():
            c['_armor_set'] = 'Leather'
        else:
            c['_armor_set'] = body_name.split(' ')[0] if body_name else 'Mixed'

        # Status line
        status_icon = '☠️' if dead else ('⚙️' if af else '🛑')
        hp_str = f"{hp}/{mhp}"
        mp_str = f"{mp}/{mmp}"
        state.log(f"{status_icon} {name} — Lv{lv} {cls}  HP:{hp_str} MP:{mp_str}  💰{gold:,}g  📍{zn}  {'AutoFarm' if af else st}")
        if not af and not dead and st != 'combat':
            state.log(f"     ⚠️ Not auto-farming (state: {st})")

        # Gear line
        if cls == 'wizard':
            matk = wpn_stats.get('m_atk', 0)
            state.log(f"     🗡️ {wpn_name} (M.Atk: {matk})")
        elif cls == 'fighter':
            patk = wpn_stats.get('p_atk', 0)
            state.log(f"     🗡️ {wpn_name} (P.Atk: {patk})")
        else:
            state.log(f"     🗡️ {wpn_name}")

        # Accessory line
        acc_parts = []
        ring1 = equipped_slots.get('ring1', {})
        ring2 = equipped_slots.get('ring2', {})
        amulet = equipped_slots.get('amulet', {})
        if ring1:
            rs = json.loads(ring1.get('statsJson', '{}')) if ring1.get('statsJson') else {}
            acc_parts.append(f"💍{ring1.get('itemName','?')}")
        if ring2:
            rs2 = json.loads(ring2.get('statsJson', '{}')) if ring2.get('statsJson') else {}
            acc_parts.append(f"💍{ring2.get('itemName','?')}")
        if amulet:
            acc_parts.append(f"📿{amulet.get('itemName','?')}")
        if acc_parts:
            state.log(f"     {' '.join(acc_parts)}")

        # Armor line
        armor_set = c.get('_armor_set', '?')
        astats = c.get('_armor_stats', {})
        state.log(f"     🛡️ {armor_set} set (P.Def {astats.get('pdef',0)}, M.Def {astats.get('mdef',0)})")

    state.log(f"\n💰 TOTAL GOLD: {state.total_gold:,}g")

    # ─────────────────────────────────────────────────
    # 2. AUTO-EQUIP MISSING/BETTER WEAPONS
    # ─────────────────────────────────────────────────
    state.log("")
    state.log("═" * 50)
    state.log("GEAR CHECKS")
    state.log("─" * 50)

    for c in chars:
        cid = c['id']
        name = c['name']
        cls = c.get('class', '?')
        lv = c['level']
        equipped = c.get('_equipped', {})
        weapon = c.get('_weapon', 'NONE')
        wpn_stats = c.get('_weapon_stats', {})
        inv_data = c.get('_inv', {})

        weapon_slot = equipped.get('main_hand') or equipped.get('two_hand')
        has_weapon = weapon_slot is not None and weapon != 'NONE'

        # Check bag for better weapons
        bag = inv_data.get('bag', [])
        bag_staves = []
        bag_swords = []

        for item in bag:
            iname = item.get('itemName', '').lower()
            if 'staff' in iname and cls == 'wizard':
                stats = {}
                try:
                    stats = json.loads(item.get('statsJson', '{}'))
                except Exception:
                    pass
                bag_staves.append((stats.get('m_atk', 0), item))
            elif ('sword' in iname or 'dagger' in iname) and cls == 'fighter':
                stats = {}
                try:
                    stats = json.loads(item.get('statsJson', '{}'))
                except Exception:
                    pass
                bag_swords.append((stats.get('p_atk', 0), item))

        current_matk = wpn_stats.get('m_atk', 0)
        current_patk = wpn_stats.get('p_atk', 0)

        # Check if weapon is in bag and better than equipped
        if cls == 'wizard':
            if bag_staves:
                # Find best staff in bag
                best = max(bag_staves, key=lambda x: x[0])
                if best[0] > current_matk:
                    inv_id = best[1]['id']
                    state.log(f"  ⚡ {name}: equipping {best[1]['itemName']} (M.Atk {best[0]} > {current_matk}) from bag")
                    try:
                        result = api_post(f'/api/inventory/{cid}/equip', {"inventoryId": inv_id}, state.token)
                        state.log(f"     → {result.get('status', 'failed')}")
                        # Update current matk
                        current_matk = best[0]
                    except Exception as e:
                        state.log(f"     → equip failed: {e}")

            if not has_weapon and not bag_staves:
                state.log(f"  ⚠️ {name}: NO WEAPON EQUIPPED")

            # Weapon mismatch check
            if 'greatsword' in weapon.lower() or 'sword' in weapon.lower():
                state.log(f"  ⚠️ {name}: using {weapon}! Needs a staff (wizard)")

        elif cls == 'fighter':
            if bag_swords:
                best = max(bag_swords, key=lambda x: x[0])
                if best[0] > current_patk:
                    inv_id = best[1]['id']
                    state.log(f"  ⚡ {name}: equipping {best[1]['itemName']} (P.Atk {best[0]} > {current_patk}) from bag")
                    try:
                        result = api_post(f'/api/inventory/{cid}/equip', {"inventoryId": inv_id}, state.token)
                        state.log(f"     → {result.get('status', 'failed')}")
                        current_patk = best[0]
                    except Exception as e:
                        state.log(f"     → equip failed: {e}")

        # Weapon upgrade suggestions
        char_gold = c.get('gold', 0)
        if cls == 'wizard':
            upgrades = state.find_weapon_upgrade(cls, current_matk, 0, lv)
            if upgrades:
                next_wpn = upgrades[0]
                if next_wpn['price'] > 0:
                    pct = char_gold / next_wpn['price'] * 100
                    if char_gold >= next_wpn['price']:
                        status = f"✅ can buy ({char_gold:,}g available)"
                    else:
                        short = next_wpn['price'] - char_gold
                        status = f"💰 {pct:.0f}% ({short:,}g more needed)"
                    state.log(f"  💡 Next upgrade: {next_wpn['name']} (M.Atk {next_wpn['matk']}, {next_wpn['price']:,}g) — {status}")
            else:
                state.log(f"  ✅ Best-in-slot weapon for current level")

        elif cls == 'fighter':
            upgrades = state.find_weapon_upgrade(cls, 0, current_patk, lv)
            if upgrades:
                next_wpn = upgrades[0]
                if next_wpn['price'] > 0:
                    pct = char_gold / next_wpn['price'] * 100
                    if char_gold >= next_wpn['price']:
                        status = f"✅ can buy ({char_gold:,}g available)"
                    else:
                        short = next_wpn['price'] - char_gold
                        status = f"💰 {pct:.0f}% ({short:,}g more needed)"
                    state.log(f"  💡 Next upgrade: {next_wpn['name']} (P.Atk {next_wpn['patk']}, {next_wpn['price']:,}g) — {status}")
            else:
                state.log(f"  ✅ Best-in-slot weapon for current level")

        # ──────────────────────────────────
        # ACCESSORY AUTO-EQUIP
        # ──────────────────────────────────
        bag_rings = []
        bag_amulets = []
        for item in bag:
            iname = item.get('itemName', '').lower()
            if 'ring' in iname:
                bag_rings.append(item)
            elif 'amulet' in iname:
                bag_amulets.append(item)

        acc_slots = {'ring1': equipped.get('ring1'), 'ring2': equipped.get('ring2'), 'amulet': equipped.get('amulet')}
        empty_slots = [s for s, v in acc_slots.items() if not v]
        filled_slots = [s for s, v in acc_slots.items() if v]

        # Equip rings to empty ring slots
        ring_slots_empty = [s for s in ['ring1', 'ring2'] if s in empty_slots]
        for ring in bag_rings:
            if not ring_slots_empty:
                break
            slot = ring_slots_empty.pop(0)
            inv_id = ring['id']
            rname = ring.get('itemName', 'Ring')
            state.log(f"  💍 {name}: equipping {rname} to {slot}")
            try:
                result = api_post(f'/api/inventory/{cid}/equip', {"inventoryId": inv_id}, state.token)
                state.log(f"     → {result.get('status', 'failed')}")
            except Exception as e:
                state.log(f"     → equip failed: {e}")

        # Equip amulet to empty amulet slot
        if 'amulet' in empty_slots:
            for amulet in bag_amulets:
                inv_id = amulet['id']
                aname = amulet.get('itemName', 'Amulet')
                state.log(f"  📿 {name}: equipping {aname} to amulet")
                try:
                    result = api_post(f'/api/inventory/{cid}/equip', {"inventoryId": inv_id}, state.token)
                    state.log(f"     → {result.get('status', 'failed')}")
                except Exception as e:
                    state.log(f"     → equip failed: {e}")
                break

        # Accessory slot suggestions
        ring_filled = any(s in filled_slots for s in ['ring1', 'ring2'])
        amulet_filled = 'amulet' in filled_slots

        if not ring_filled:
            bonus = "+3 M.Atk" if cls == 'wizard' else "+3 P.Atk"
            state.log(f"  💡 Silver Ring ({bonus}, ~19K) — open ring slot")
        if not amulet_filled:
            state.log(f"  💡 Silver Amulet (+3 M.Def/P.Def, ~18K) — open amulet slot")

        # ──────────────────────────────────
        # ARMOR PROGRESSION SUGGESTIONS
        # ──────────────────────────────────
        armor_set = c.get('_armor_set', '')
        astats = c.get('_armor_stats', {})
        current_pdef = astats.get('pdef', 0)
        armor_class = cls
        # Fighters using heavy armor are tanks
        if cls == 'fighter':
            body = equipped.get('body', {})
            body_armor_class = body.get('armorClass', '')
            if body_armor_class == 'heavy':
                armor_class = 'tank'

        upgrades = state.find_armor_upgrade(armor_class, current_pdef, 0, lv)
        if upgrades:
            next_set = upgrades[0]
            pdef_gain = next_set.get('pdef', 0) - current_pdef
            bonus = next_set.get('bonus', '')
            bonus_str = f" — {bonus}" if bonus else ""
            char_gold = c.get('gold', 0)
            if char_gold >= next_set['price']:
                state.log(f"  🛡️ Next armor: {next_set['name']} (P.Def +{pdef_gain}, {next_set['price']:,}g) — ✅ can buy{bonus_str}")
            else:
                short = next_set['price'] - char_gold
                pct = int(char_gold / next_set['price'] * 100) if next_set['price'] else 0
                state.log(f"  🛡️ Next armor: {next_set['name']} (P.Def +{pdef_gain}, {next_set['price']:,}g) — 💰 {pct}% ({short:,}g more){bonus_str}")

    # ─────────────────────────────────────────────────
    # 2b. WAREHOUSE & GOLD POOLING
    # ─────────────────────────────────────────────────
    state.log("")
    state.log("═" * 50)
    state.log("GOLD & SHOP")
    state.log("─" * 50)

    # Check if any character is in a city (can access warehouse)
    in_city = [c for c in chars if state.zones.get(c['currentZoneId'], {}).get('type') == 'city']
    if in_city:
        city_names = [f"{c['name']} ({state.get_zone_name(c['currentZoneId'])})" for c in in_city]
        state.log(f"  🏛️ Warehouse available: {', '.join(city_names)} can deposit/withdraw")
        state.log(f"     Pool gold from all chars to buy gear for anyone")
    else:
        state.log(f"  🏛️ No characters in city — warehouse inaccessible")
        state.log(f"     Travel to a city to pool gold via warehouse")

    state.log(f"  💰 Total across chars: {state.total_gold:,}g")
    for c in chars:
        cname = c['name']
        cgold = c.get('gold', 0)
        state.log(f"     {cname}: {cgold:,}g")

    # Auto-buy Oak Staff if any wizard has enough personal gold
    wizards = [c for c in chars if c.get('class') == 'wizard']
    for wiz in wizards:
        wpn_stats = wiz.get('_weapon_stats', {})
        current_matk = wpn_stats.get('m_atk', 0)
        cid = wiz['id']
        cname = wiz['name']
        wiz_gold = wiz.get('gold', 0)

        if current_matk < 32 and wiz_gold >= 137659:
            state.log(f"\n  🛒 Buying Oak Staff (M.Atk 32, 137,659g) for {cname}")
            try:
                result = api_post(f'/api/shop/{BEST_STAFF_SHOP}/buy',
                    {"characterId": cid, "itemId": STAFF_ITEM_IDS['oak'], "quantity": 1},
                    state.token)
                state.log(f"     → {json.dumps(result)}")
                inv = api_get(f'/api/inventory/{cid}', state.token)
                for item in inv.get('bag', []):
                    if 'oak staff' in item.get('itemName', '').lower():
                        equip_result = api_post(f'/api/inventory/{cid}/equip',
                            {"inventoryId": item['id']}, state.token)
                        state.log(f"     → Equipped: {equip_result.get('status', 'failed')}")
                        break
            except urllib.request.HTTPError as e:
                body = e.read().decode()[:200]
                state.log(f"     → FAILED: {e.code} {body}")

        if current_matk < 55 and wiz_gold >= 275318:
            state.log(f"\n  🛒 Buying Arcane Staff (M.Atk 55, 275,318g) for {cname}")
            try:
                result = api_post(f'/api/shop/{BEST_ARCANE_SHOP}/buy',
                    {"characterId": cid, "itemId": STAFF_ITEM_IDS['arcane'], "quantity": 1},
                    state.token)
                state.log(f"     → {json.dumps(result)}")
                inv = api_get(f'/api/inventory/{cid}', state.token)
                for item in inv.get('bag', []):
                    if 'arcane staff' in item.get('itemName', '').lower():
                        equip_result = api_post(f'/api/inventory/{cid}/equip',
                            {"inventoryId": item['id']}, state.token)
                        state.log(f"     → Equipped: {equip_result.get('status', 'failed')}")
                        break
            except urllib.request.HTTPError as e:
                body = e.read().decode()[:200]
                state.log(f"     → FAILED: {e.code} {body}")

    # Auto-buy accessories for characters with enough gold
    for c in chars:
        cid = c['id']
        cname = c['name']
        cgold = c.get('gold', 0)
        equipped = c.get('_equipped', {})
        bag = c.get('_inv', {}).get('bag', [])

        # Count rings in bag and equipped
        bag_ring_count = sum(1 for i in bag if 'ring' in i.get('itemName', '').lower())
        has_ring1 = bool(equipped.get('ring1'))
        has_ring2 = bool(equipped.get('ring2'))
        has_amulet = bool(equipped.get('amulet'))

        # Cheapest shops for accessories
        RING_SHOP = 10   # 19,034g
        AMULET_SHOP = 10 # 18,072g

        # Buy Silver Ring if one slot empty and affordable
        if not has_ring1 or not has_ring2:
            if cgold >= 19034 and bag_ring_count == 0:
                state.log(f"  🛒 Buying Silver Ring (+3 M.Atk/P.Atk, {19034:,}g) for {cname}")
                try:
                    result = api_post(f'/api/shop/{RING_SHOP}/buy',
                        {"characterId": cid, "itemId": ACCESSORY_ITEM_IDS['silver_ring'], "quantity": 1},
                        state.token)
                    state.log(f"     → {json.dumps(result)}")
                    # Reload inventory and equip
                    inv = api_get(f'/api/inventory/{cid}', state.token)
                    target_slot = 'ring1' if not has_ring1 else 'ring2'
                    for item in inv.get('bag', []):
                        if ACCESSORY_ITEM_IDS['silver_ring'] == item.get('itemId'):
                            equipr = api_post(f'/api/inventory/{cid}/equip',
                                {"inventoryId": item['id']}, state.token)
                            state.log(f"     → Equipped to {target_slot}: {equipr.get('status', 'failed')}")
                            break
                except urllib.request.HTTPError as e:
                    body = e.read().decode()[:200]
                    state.log(f"     → FAILED: {e.code} {body}")

        # Buy Silver Amulet if slot empty and affordable
        if not has_amulet and cgold >= 18072:
            bag_amulet_count = sum(1 for i in bag if 'amulet' in i.get('itemName', '').lower())
            if bag_amulet_count == 0:
                state.log(f"  🛒 Buying Silver Amulet (+3 M.Def/P.Def, {18072:,}g) for {cname}")
                try:
                    result = api_post(f'/api/shop/{AMULET_SHOP}/buy',
                        {"characterId": cid, "itemId": ACCESSORY_ITEM_IDS['silver_amulet'], "quantity": 1},
                        state.token)
                    state.log(f"     → {json.dumps(result)}")
                    inv = api_get(f'/api/inventory/{cid}', state.token)
                    for item in inv.get('bag', []):
                        if ACCESSORY_ITEM_IDS['silver_amulet'] == item.get('itemId'):
                            equipr = api_post(f'/api/inventory/{cid}/equip',
                                {"inventoryId": item['id']}, state.token)
                            state.log(f"     → Equipped: {equipr.get('status', 'failed')}")
                            break
                except urllib.request.HTTPError as e:
                    body = e.read().decode()[:200]
                    state.log(f"     → FAILED: {e.code} {body}")

    # ─────────────────────────────────────────────────
    # 2c. AUCTION HOUSE
    # ─────────────────────────────────────────────────
    state.log("")
    state.log("═" * 50)
    state.log("AUCTION HOUSE")
    state.log("─" * 50)

    # Fetch active listings
    ah_listings = []
    try:
        ah_data = api_get('/api/auction/listings', state.token)
        ah_listings = ah_data.get('listings', ah_data if isinstance(ah_data, list) else [])
    except Exception:
        pass

    # Check AH prices for items we care about
    tracked_items = {
        "Oak Staff": {"itemId": 86,  "shop_price": 137659, "slot": "weapon"},
        "Arcane Staff": {"itemId": 87, "shop_price": 275318, "slot": "weapon"},
        "Silver Ring": {"itemId": 111, "shop_price": 19034, "slot": "ring1"},
        "Silver Amulet": {"itemId": 110, "shop_price": 18072, "slot": "amulet"},
        "Iron Shield": {"itemId": 94, "shop_price": 27800, "slot": "shield"},
        "Steel Plate": {"itemId": None, "shop_price": 37000, "slot": "armor"},
        "Hardened Boots": {"itemId": 104, "shop_price": 22000, "slot": "boots"},
        "Hardened Tunic": {"itemId": 101, "shop_price": 37000, "slot": "body"},
    }

    ah_deals = []
    for l in ah_listings:
        iname = l.get('itemName', '')
        price = l.get('pricePerUnit', 0)
        listing_id = l['id']
        qty = l.get('quantity', 1)
        seller = l.get('characterName', '?')

        tracked = tracked_items.get(iname)
        if tracked and tracked['shop_price']:
            savings = tracked['shop_price'] - price
            pct = int((1 - price / tracked['shop_price']) * 100)
            if savings > 0:
                ah_deals.append({
                    "name": iname, "price": price, "listing_id": listing_id,
                    "savings": savings, "pct": pct, "qty": qty, "seller": seller,
                    "shop_price": tracked['shop_price'], "item_id": tracked['itemId']
                })

    if ah_deals:
        ah_deals.sort(key=lambda x: -x['savings'])
        state.log(f"  🏷️  Deals found (cheaper than NPC shop):")
        for d in ah_deals[:5]:
            state.log(f"     {d['name']} — {d['price']:,}g ({d['pct']}% off NPC, save {d['savings']:,}g) — {d['seller']}")
            # Auto-buy if >30% off NPC and we need it (check which chars could use it)
            if d['pct'] >= 30:
                for c in chars:
                    cid = c['id']
                    cname = c['name']
                    cgold = c.get('gold', 0)
                    cls = c.get('class', '?')
                    if cgold >= d['price']:
                        # Check if char would benefit
                        benefit = False
                        if d['name'] == 'Oak Staff' and cls == 'wizard':
                            wpn = c.get('_weapon_stats', {})
                            if wpn.get('m_atk', 0) < 32:
                                benefit = True
                        elif d['name'] == 'Arcane Staff' and cls == 'wizard':
                            wpn = c.get('_weapon_stats', {})
                            if wpn.get('m_atk', 0) < 55 and wpn.get('m_atk', 0) >= 14:
                                benefit = True
                        elif d['name'] in ['Silver Ring', 'Silver Amulet']:
                            benefit = True  # Everyone can use accessories

                        if benefit:
                            state.log(f"       → Buying for {cname} ({d['price']:,}g)!")
                            try:
                                result = api_post('/api/auction/buy',
                                    {"characterId": cid, "listingId": d['listing_id'], "quantity": 1},
                                    state.token)
                                state.log(f"       → {json.dumps(result)}")
                            except urllib.request.HTTPError as e:
                                state.log(f"       → FAILED: {e.code} {e.read().decode()[:100]}")
                            break  # Buy 1 per cycle
    else:
        state.log(f"  No tracked items on AH cheaper than NPC shop")

    # Collect pickups for all characters
    state.log("  ─")
    for c in chars:
        cid = c['id']
        cname = c['name']
        try:
            picks = api_get(f'/api/auction/pickups?characterId={cid}', state.token)
            if picks:
                for p in picks:
                    pid = p.get('id', p.get('pickupId'))
                    iname = p.get('itemName', 'item')
                    qty = p.get('quantity', 1)
                    if not p.get('collected', False):
                        state.log(f"  📦 {cname}: Collecting {iname} x{qty} from AH")
                        try:
                            result = api_post(f'/api/auction/collect/{pid}', {"characterId": cid}, state.token)
                            state.log(f"     → {json.dumps(result)[:100]}")
                        except urllib.request.HTTPError as e:
                            state.log(f"     → FAILED: {e.code}")
        except Exception:
            pass

    # ─────────────────────────────────────────────────
    # 2d. CRAFTING & MATERIALS
    # ─────────────────────────────────────────────────
    state.log("")
    state.log("═" * 50)
    state.log("CRAFTING & MATERIALS")
    state.log("─" * 50)

    # Scan materials per character
    for c in chars:
        cid = c['id']
        cname = c['name']
        cgold = c.get('gold', 0)
        bag = c.get('_inv', {}).get('bag', [])

        # Count materials in this character's bag
        mats = {}
        for item in bag:
            iname = item.get('itemName', '')
            qty = item.get('quantity', 1)
            if iname in MATERIAL_NAMES:
                mats[iname] = mats.get(iname, 0) + qty

        if not mats:
            continue

        c['_mats'] = mats
        mat_list = [f"{v}× {k}" for k, v in sorted(mats.items(), key=lambda x: -x[1])]
        state.log(f"  📦 {cname}: {', '.join(mat_list)}")

        # Auto-craft base materials
        for recipe in MATERIAL_RECIPES:
            rname = recipe['name']
            iname = recipe['input']
            iqty = recipe['input_qty']
            cost = recipe['cost']
            have = mats.get(iname, 0)
            can_craft = have // iqty

            if can_craft >= 1 and cgold >= cost:
                # Don't craft if it would empty all of a useful base mat
                if iname == 'Iron Ore' and have - iqty < 20:
                    continue  # Keep a reserve of Iron Ore

                state.log(f"     🔧 Crafting {rname} ({iname} {iqty}→{rname}, {cost:,}g)")
                try:
                    result = api_post('/api/crafting/craft',
                        {"characterId": cid, "recipeId": recipe['recipeId'], "quantity": 1},
                        state.token)
                    if result.get('resultItemId') or result.get('status') == 'ok':
                        state.log(f"        ✅ Crafted {result.get('resultItemName', rname)}! (gold: {result.get('newGold', '?')})")
                        mats[iname] = mats.get(iname, 0) - iqty
                        cgold -= cost
                    else:
                        state.log(f"        ❌ {json.dumps(result)}")
                except urllib.request.HTTPError as e:
                    body = e.read().decode()[:200]
                    state.log(f"        ❌ {e.code} {body}")
                break  # 1 craft per char per cycle

    # Show account-wide material totals
    all_mats = {}
    for c in chars:
        for iname, qty in c.get('_mats', {}).items():
            all_mats[iname] = all_mats.get(iname, 0) + qty

    if all_mats:
        state.log("  ─")
        items_str = " | ".join([f"{k}: {v}" for k, v in sorted(all_mats.items(), key=lambda x: -x[1])])
        state.log(f"  📊 Account total: {items_str}")

    # Gear crafting readiness for each character
    state.log("  ─")
    for c in chars:
        cls = c.get('class', '?')
        cname = c['name']
        cgold = c.get('gold', 0)
        c_mats = c.get('_mats', {})
        all_c_mats = dict(all_mats)  # account-wide for warehouse-enabled crafting

        for recipe in GEAR_RECIPES.get(cls, []):
            rname = recipe['name']
            rcost = recipe['cost']
            needed = recipe['mats']
            stat_info = recipe.get('matk', recipe.get('patk', recipe.get('desc', '')))
            if isinstance(stat_info, int):
                key = 'M.Atk' if 'matk' in recipe else 'P.Atk'
                stat_info = f"{key} {stat_info}"

            # Check if mats are available (account-wide, assuming warehouse)
            missing = []
            for mat_name, mat_qty in needed.items():
                avail = all_c_mats.get(mat_name, 0)
                if avail < mat_qty:
                    missing.append(f"{mat_name} {avail}/{mat_qty}")

            gold_status = "💰" if cgold >= rcost else "❌"
            if not missing and cgold >= rcost:
                state.log(f"  ✅ {cname}: «{rname}» ({stat_info}) — {rcost:,}g — ALL MATS READY, craft when in city!")
            elif not missing:
                state.log(f"  🟡 {cname}: «{rname}» ({stat_info}) — mats ready, need {rcost-cgold:,}g more gold")
            else:
                # Show highest completion
                pcts = []
                for mat_name, mat_qty in needed.items():
                    avail = all_c_mats.get(mat_name, 0)
                    pcts.append(f"{mat_name} {avail}/{mat_qty}")
                state.log(f"  🔘 {cname}: «{rname}» ({stat_info}) — missing: {', '.join(missing)}")

    if not any(c.get('_mats') for c in chars):
        state.log("  No crafting materials found (keep farming!)")

    # ─────────────────────────────────────────────────
    # 3. ZONE PROGRESSION
    # ─────────────────────────────────────────────────
    state.log("")
    state.log("═" * 50)
    state.log("ZONE PROGRESSION")
    state.log("─" * 50)

    travels = []
    for c in chars:
        try:
            name = c['name']
            lv = c['level']
            zid = c['currentZoneId']
            zn = state.get_zone_name(zid)
            zone_obj = state.zones.get(zid, {})
            zone_type = zone_obj.get('type', 'unknown')

            zmin, zmax = state.get_zone_level_range(zid)

            # Determine best zone
            target_ids = state.get_best_zone_ids(lv)
            if not target_ids:
                state.log(f"  {name}: No progression tier for Lv{lv} (endgame?)")
                continue

            # Find first valid target zone that exists in world map
            target_zid = None
            for tid in target_ids:
                if tid in state.zones:
                    target_zid = tid
                    break

            if target_zid is None:
                state.log(f"  {name}: No valid zone found in tier for Lv{lv}")
                continue

            target_name = state.get_zone_name(target_zid)

            # Check if outleveled (lv >= zmax means ready to move up)
            outleveled = lv >= zmax
            in_city = zone_type == 'city'
            already_at_target = zid == target_zid

            if already_at_target:
                state.log(f"  ✅ {name} Lv{lv} — {zn} (correct zone)")
            elif outleveled or in_city:
                reason = 'outleveled' if outleveled else 'in city'
                state.log(f"  📍 {name} Lv{lv} — {reason} {zn} (Lv{zmin}-{zmax}, type:{zone_type})")
                path = state.bfs_path(zid, target_zid)
                if path and len(path) <= 15:
                    next_hop = path[1] if len(path) > 1 else target_zid
                    next_name = state.get_zone_name(next_hop)
                    hops_left = len(path) - 1
                    state.log(f"     → Target: {target_name} ({hops_left} hop{'s' if hops_left>1 else ''}, next: {next_name})")
                    travels.append({"char_id": c['id'], "char_name": name, "path": path, "target": target_zid})
                else:
                    reason2 = "no path found" if not path else f"too far ({len(path)-1} hops)"
                    state.log(f"     → Wanted: {target_name} ({reason2})")
            else:
                # In valid zone range, but check if there's a strictly better zone
                tzmin, tzmax = state.get_zone_level_range(target_zid)
                if lv >= tzmin and lv <= tzmax and zid != target_zid and zmax < tzmax:
                    path = state.bfs_path(zid, target_zid)
                    if path and len(path) <= 3:
                        next_hop = path[1] if len(path) > 1 else target_zid
                        state.log(f"  ⬆️ {name} Lv{lv} — {zn} → upgrade to {target_name}")
                        travels.append({"char_id": c['id'], "char_name": name, "path": path, "target": target_zid})
                    else:
                        state.log(f"  ✅ {name} Lv{lv} — {zn} (Lv{zmin}-{zmax}, valid)")
                else:
                    state.log(f"  ✅ {name} Lv{lv} — {zn} (Lv{zmin}-{zmax}, valid)")
        except Exception as e:
            cname = c.get('name', f'#{c.get("id", "?")}')
            state.log(f"  ⚠️ Error checking {cname}: {e}")
            continue

    # ══════════════════════════════════════════════
    # FLUSH REPORT BEFORE TRAVEL (in case travel blocks)
    # ══════════════════════════════════════════════
    print("\n".join(state.lines))
    sys.stdout.flush()
    state.lines = []

    # Execute travels (1 hop per cycle, 1 char per cycle, max 20s timeout)
    if travels:
        try:
            import websockets
            has_ws = True
        except ImportError:
            has_ws = False
            print("  ⚠️ websockets not installed — can't travel")

        travel = travels[0]
        char_id = travel['char_id']
        char_name = travel['char_name']
        path = travel['path']
        target_zid = travel['target']

        if len(path) > 1:
            next_hop = path[1]  # First hop from current position
            next_name = state.get_zone_name(next_hop)
            hop_name = state.get_zone_name(target_zid)
            print(f"\n  🚀 Travel: {char_name} → {next_name} (hop 1/{len(path)-1} to {hop_name})")
            sys.stdout.flush()
            if has_ws:
                result = await ws_travel(state.token, char_id, next_hop)
                if result is True:
                    print(f"     ✅ Arrived at {next_name}")
                elif isinstance(result, str) and "timed out" in result:
                    print(f"     ⚠️ Travel timed out, retry next cycle")
                elif isinstance(result, str):
                    print(f"     ⚠️ {result}")
                elif result is False:
                    print(f"     ⚠️ Travel failed (unknown), retry next cycle")
            else:
                print(f"     ⚠️ websockets not installed")
            sys.stdout.flush()

        if len(travels) > 1:
            print(f"  ⏳ {len(travels)-1} more character(s) queued for travel next cycles")
            sys.stdout.flush()
    else:
        print("")

    # ─────────────────────────────────────────────────
    # 4. QUEST STATUS
    # ─────────────────────────────────────────────────
    state.log("")
    state.log("═" * 50)
    state.log("QUESTS")
    state.log("─" * 50)

    for c in chars:
        cid = c['id']
        name = c['name']
        lv = c['level']
        zid = c['currentZoneId']
        try:
            active = api_get(f'/api/quests/active?characterId={cid}', state.token)
            available = api_get(f'/api/quests/available?characterId={cid}', state.token)
        except Exception:
            state.log(f"  {name}: quest API error")
            continue

        # Report active quests
        if active:
            for entry in active:
                qd = entry.get('quest', entry)
                pg = entry.get('progress', {})
                si = entry.get('stageInfo', {})
                qname = qd.get('name', '?')
                qid = qd.get('id')
                qstate = pg.get('state', 0)
                stage = si.get('label', 'Unknown stage')
                target_zones = si.get('targetZoneIds', [])
                tz_names = [state.get_zone_name(z) for z in target_zones]
                state.log(f"  📋 {name}: «{qname}» — {stage}")
                if tz_names:
                    state.log(f"       Zone: {', '.join(tz_names)}")

                # Auto-advance quest if in target zone
                if target_zones and zid in target_zones and 'party' not in qname.lower():
                    state.log(f"     🎯 In target zone! Advancing quest...")
                    try:
                        adv = api_post(f'/api/quests/{qid}/advance', {"characterId": cid}, state.token)
                        state.log(f"     → {json.dumps(adv)[:200]}")
                        if adv.get('status') == 'ok' or adv.get('completed'):
                            # Try to complete
                            comp = api_post(f'/api/quests/{qid}/complete', {"characterId": cid}, state.token)
                            state.log(f"     → Complete: {json.dumps(comp)[:200]}")
                            if comp.get('status') == 'ok':
                                claim = api_post(f'/api/quests/{qid}/claim', {"characterId": cid}, state.token)
                                state.log(f"     → Reward: {json.dumps(claim)[:200]}")
                    except urllib.request.HTTPError as e:
                        body = e.read().decode()[:100]
                        state.log(f"     → {e.code}: {body}")
        else:
            state.log(f"  {name}: no active quests")

        # Auto-accept available quests
        newly_accepted = False
        for quest in available:
            # completionState: 1=not started/available, 2=completed/ignored
            if quest.get('completionState') == 1 and not quest.get('ignored', True):
                qid = quest['id']
                qname = quest['name']
                try:
                    result = api_post(f'/api/quests/{qid}/accept', {"characterId": cid}, state.token)
                    if result.get('status') == 'accepted':
                        state.log(f"  ✅ {name}: Accepted quest «{qname}»")
                        newly_accepted = True
                except Exception as e:
                    state.log(f"  ⚠️ {name}: Failed to accept «{qname}»: {e}")

        if not newly_accepted and not active:
            av_names = [q['name'] for q in available if not q.get('ignored', True)]
            if av_names:
                state.log(f"     Available: {', '.join(av_names)}")

    # ─────────────────────────────────────────────────
    # 5. PARTY QUEST NOTIFICATION
    # ─────────────────────────────────────────────────
    state.log("")
    state.log("═" * 50)
    state.log("PARTY")
    state.log("─" * 50)

    # Check if the party quest is active on any character
    party_quest_active = False
    party_quest_name = None
    party_quest_stage = None
    for c in chars:
        cid = c['id']
        try:
            active = api_get(f'/api/quests/active?characterId={cid}', state.token)
            for entry in active:
                qd = entry.get('quest', entry)
                if 'party' in qd.get('name', '').lower():
                    party_quest_active = True
                    party_quest_name = qd['name']
                    pg = entry.get('progress', {})
                    si = entry.get('stageInfo', {})
                    party_quest_stage = si.get('label', 'Unknown')
                    break
        except Exception:
            pass
        if party_quest_active:
            break

    if party_quest_active:
        state.log(f"  🎯 Party quest active for {len(chars)} chars: «{party_quest_name}»")
        state.log(f"     Stage: {party_quest_stage}")
    else:
        state.log(f"  No party quests active (all solo farming)")

    # ══════════════════════════════════════════════
    # 5b. SKILL ROTATION MANAGEMENT
    # ══════════════════════════════════════════════
    state.log("")
    state.log("═" * 50)
    state.log("SKILL ROTATIONS")
    state.log("─" * 50)

    # Optimal rotations per role
    ROTATIONS = {
        "tank": [  # ShieldBot — priority: damage > utility
            {"skillId": 42118, "autoPriority": 1, "autoEnabled": True, "name": "Mortal Blow"},
            {"skillId": 200,   "autoPriority": 2, "autoEnabled": True, "name": "Power Strike"},
            {"skillId": 13285, "autoPriority": 3, "autoEnabled": True, "name": "Power Shot"},
        ],
        "healer": [  # HermesHeal — priority: heals > damage
            {"skillId": 67344, "autoPriority": 1, "autoEnabled": True, "name": "Battle Heal"},
            {"skillId": 67493, "autoPriority": 2, "autoEnabled": True, "name": "Heal"},
            {"skillId": 38310, "autoPriority": 3, "autoEnabled": True, "name": "Group Heal"},
            {"skillId": 37042, "autoPriority": 4, "autoEnabled": True, "name": "Curse: Poison"},
            {"skillId": 232,   "autoPriority": 5, "autoEnabled": True, "name": "Wind Strike"},
        ],
        "dps": [  # BuffBot — priority: DoT > nuke > sustain (NO heal skills in rotation)
            # Heal skills removed from DPS rotation: _dps_tick calls _heal_party_members
            # directly for emergency self-heal (HP<25%). Having heal skills in the rotation
            # adds no value for manual DPS since _use_best_skill skips heal-type skills.
            {"skillId": 37042, "autoPriority": 1, "autoEnabled": True, "name": "Curse: Poison"},
            {"skillId": 232,   "autoPriority": 2, "autoEnabled": True, "name": "Wind Strike"},
        ],
    }

    # Role-to-character mapping from CHARACTERS config
    CHAR_ROLE = {
        1069: "dps",
        1070: "healer",
        1071: "tank",
    }

    for c in chars:
        cid = c['id']
        name = c['name']
        role = CHAR_ROLE.get(cid, "dps")
        optimal = ROTATIONS.get(role, [])

        # Fetch current config
        try:
            cfg = api_get(f'/api/skills/config/{cid}', state.token)
        except Exception as e:
            state.log(f"  ⚠️ {name}: couldn't fetch config: {e}")
            continue

        if not isinstance(cfg, list):
            state.log(f"  ⚠️ {name}: no config returned")
            continue

        # Check if current rotation matches optimal
        current_active = [s for s in cfg if s.get('skillId') in {r['skillId'] for r in optimal}]
        needs_update = False

        if len(current_active) < len(optimal):
            needs_update = True
            state.log(f"  🔄 {name}: missing skills in rotation (has {len(current_active)}/{len(optimal)})")
        else:
            for opt in optimal:
                found = next((s for s in current_active if s['skillId'] == opt['skillId']), None)
                if not found:
                    needs_update = True
                    state.log(f"  🔄 {name}: missing {opt['name']}")
                    break
                if found.get('autoPriority') != opt['autoPriority']:
                    needs_update = True
                    state.log(f"  🔄 {name}: {opt['name']} priority {found.get('autoPriority')}→{opt['autoPriority']}")
                    break

        if needs_update:
            # Build the full config preserving existing entries not in our rotation
            existing_map = {s['skillId']: s for s in cfg}
            new_config = []
            for opt in optimal:
                existing = existing_map.get(opt['skillId'], {})
                new_config.append({
                    "skillId": opt['skillId'],
                    "autoPriority": opt['autoPriority'],
                    "autoEnabled": opt.get('autoEnabled', existing.get('autoEnabled', True)),
                    "gateSelfHpMin": existing.get('gateSelfHpMin', 0),
                    "gateSelfHpMax": existing.get('gateSelfHpMax', 100),
                    "gateSelfMpMin": existing.get('gateSelfMpMin', 10),
                    "gateSelfMpMax": existing.get('gateSelfMpMax', 100),
                })
            # Keep any skills not in our rotation (passives, utility) at high priority
            for sid, s in existing_map.items():
                if sid not in {r['skillId'] for r in optimal}:
                    new_config.append({
                        "skillId": sid,
                        "autoPriority": 99,
                        "autoEnabled": s.get('autoEnabled', True),
                        "gateSelfHpMin": s.get('gateSelfHpMin', 0),
                        "gateSelfHpMax": s.get('gateSelfHpMax', 100),
                        "gateSelfMpMin": s.get('gateSelfMpMin', 10),
                        "gateSelfMpMax": s.get('gateSelfMpMax', 100),
                    })

            # Push updated config via PUT
            try:
                result = api_put(f'/api/skills/config/{cid}', {"autoConfig": new_config}, state.token)
                if isinstance(result, dict) and result.get('status') == 'ok':
                    state.log(f"  ✅ {name}: rotation updated ({len(optimal)} skills)")
                else:
                    state.log(f"  ⚠️ {name}: update returned: {result}")
                # Also update SpacetimeDB via collector (will pick up next cycle)
            except Exception as e:
                state.log(f"  ❌ {name}: update failed: {e}")
        else:
            state.log(f"  ✅ {name}: rotation optimal ({len(optimal)} skills)")

    # ══════════════════════════════════════════════
    # 6. BOSS & RAID TRACKING
    # ══════════════════════════════════════════════
    state.log("")
    state.log("═" * 50)
    state.log("BOSSES & RAIDS")
    state.log("─" * 50)
    state.log(f"  No boss tracking active (all chars below Lv20 raid thresholds)")
    state.log(f"  Key targets at Lv20+: Old Pirate → Arcane Staff (55 M.Atk, 0.25%)")
    state.log(f"  Vaeldris the Ruinbound → Mithril Stiletto (54 P.Atk, 12%)")
    state.log(f"  Need to form a party manually for raid bosses (auto-farm breaks in party)")

    # ══════════════════════════════════════════════
    # 7. ASCENDANCY CHECK (Lv20+)
    # ══════════════════════════════════════════════
    state.log("")
    state.log("═" * 50)
    state.log("ASCENDANCY")
    state.log("─" * 50)

    for c in chars:
        cid = c['id']
        name = c['name']
        lv = c['level']
        cls = c.get('class', '?')
        if lv >= 20:
            state.log(f"  ⬆️ {name} Lv{lv} {cls} — eligible for ascendancy!")
            try:
                options = api_get(f'/api/ascendancy/options?characterId={cid}', state.token)
                state.log(f"     Options: {json.dumps(options)[:300]}")
                # Auto-ascend to recommended path
                if isinstance(options, list) and options:
                    best = options[0]
                    aid = best.get('id', best.get('ascendancyId'))
                    aname = best.get('name', '?')
                    state.log(f"     Ascending to {aname}...")
                    result = api_post('/api/ascendancy/ascend', {"characterId": cid, "ascendancyId": aid}, state.token)
                    state.log(f"     → {json.dumps(result)[:200]}")
            except urllib.request.HTTPError as e:
                body = e.read().decode()[:100]
                state.log(f"     → {e.code}: {body}")
        else:
            state.log(f"  {name} Lv{lv} — needs {20-lv} more levels")

    # ══════════════════════════════════════════════
    # 8. BAG MANAGEMENT
    # ══════════════════════════════════════════════
    state.log("")
    state.log("═" * 50)
    state.log("BAG MANAGEMENT")
    state.log("─" * 50)

    for c in chars:
        cid = c['id']
        name = c['name']
        bag = c.get('_inv', {}).get('bag', [])
        equipped = c.get('_equipped', {})

        if len(bag) > 15:
            state.log(f"  📦 {name}: {len(bag)} items in bag (getting full)")
            # Find duplicates worth selling
            dupes = {}
            for item in bag:
                iname = item.get('itemName', '?')
                islot = item.get('itemSlot', '?')
                qty = item.get('quantity', 1)
                if qty > 1 and islot not in ['potion', 'scroll']:
                    dupes[iname] = dupes.get(iname, 0) + qty
                elif qty == 1:
                    # Single items — check if we already have one equipped or in another slot
                    key = f"{iname}_{islot}"
                    dupes[key] = dupes.get(key, 0) + 1

            for item_name, count in dupes.items():
                if count > 1:
                    sell_count = count - 1  # Keep 1
                    state.log(f"     💰 {sell_count}× duplicate {item_name} — could sell")
                    # Find the actual item to sell
                    for item in bag:
                        base_name = item.get('itemName', '?')
                        qty = item.get('quantity', 1)
                        if base_name == item_name.replace(f'_{item.get("itemSlot", "?")}', '') and qty > 1:
                            # Try to sell to NPC
                            try:
                                slot = item.get('equippedSlot', 'bag')
                                result = api_post(f'/api/shop/8/sell',
                                    {"characterId": cid, "inventorySlot": slot, "quantity": qty - 1},
                                    state.token)
                                state.log(f"       Sold {qty-1}× to NPC: {json.dumps(result)[:100]}")
                            except Exception:
                                pass
                            break
        else:
            state.log(f"  ✅ {name}: {len(bag)} items in bag (room available)")

    state.log("")
    state.log("═" * 50)

    # Flush report
    print("\n".join(state.lines))


if __name__ == '__main__':
    asyncio.run(main())
