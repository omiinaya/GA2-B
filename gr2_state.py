"""gr2_state — State class: login, world graph, zone/gear reasoning."""
from collections import deque
from gr2_config import CREDENTIALS
from gr2_data import PROGRESSION, WEAPON_TREE, ARMOR_TREE
from gr2_api import api_get, api_post, api_put


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



