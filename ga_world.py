"""Module ga_world — extracted from grimeage_agent.py (behavior-preserving split)."""
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
