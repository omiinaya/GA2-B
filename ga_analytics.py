"""Module ga_analytics — extracted from grimeage_agent.py (behavior-preserving split)."""
import time
from collections import Counter, defaultdict


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


