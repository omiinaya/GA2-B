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
        {"name": "Wooden Staff",  "matk": 14, "price": 11472,  "source": "shop",     "min_lv": 0},
        {"name": "Oak Staff",     "matk": 32, "price": 137659, "source": "shop",     "min_lv": 5},
        {"name": "Arcane Staff",  "matk": 55, "price": 275318, "source": "shop/old pirate", "min_lv": 15},
        {"name": "Crystal-Woven Staff", "matk": 80, "price": 250000, "source": "craft/marshland toad", "min_lv": 20},
        {"name": "Archmage's Staff",    "matk": 110, "price": 500000, "source": "craft", "min_lv": 30},
    ],
    "fighter": [
        {"name": "Short Sword",   "patk": 12, "price": 12964,  "source": "shop",     "min_lv": 0},
        {"name": "Broad Sword",   "patk": 28, "price": 151242, "source": "shop",     "min_lv": 5},
        {"name": "Knight's Sword", "patk": 48, "price": 302484, "source": "shop",    "min_lv": 15},
        {"name": "Mithril Longsword", "patk": 72, "price": 0,   "source": "bandit scout 0.03%", "min_lv": 23},
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
    # 2c. CRAFTING & MATERIALS
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
                stage = si.get('label', 'Unknown stage')
                target_zones = si.get('targetZoneIds', [])
                tz_names = [state.get_zone_name(z) for z in target_zones]
                state.log(f"  📋 {name}: «{qname}» — {stage}")
                if tz_names:
                    state.log(f"       Zone: {', '.join(tz_names)}")
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
        state.log(f"  🎯 Party quest active for all 3: «{party_quest_name}»")
        state.log(f"     Stage: {party_quest_stage}")
        state.log(f"     ⚠️ Auto-farm disabled while in party!")
        state.log(f"     💡 Form party when ready to boss together (WS commands: party:invite + party:accept)")
    else:
        state.log(f"  No party quests active (all solo farming)")

    state.log("")
    state.log("═" * 50)

    # Flush report
    print("\n".join(state.lines))


if __name__ == '__main__':
    asyncio.run(main())
