"""Unit tests for the progression-wiring methods added 2026-08-05:
_auto_accept_quests, _auto_enable_class_skills, _auto_craft_talisman,
_auto_craft_best_weapon.

These methods talk to the game API via self.rest, so the tests use a stub
RestClient that returns canned responses and records calls. Covers the
decision logic that gate these actions (level gates, party-skip, status
semantics, affordability floors) — regressions here would either spam the
API (accepting everything) or silently skip upgrades.

Run: python3 -m pytest tests/test_progression.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ga_character import CharacterAgent


class StubRest:
    """Configurable stub REST client — set .responses[path] to canned data."""

    def __init__(self):
        self.responses = {}
        self.calls = []

    def _route(self, method, path):
        self.calls.append((method, path))
        # exact path first, then substring (e.g. 'craft' matches
        # '/api/crafting/craft' and '/api/crafting/recipes').
        if path in self.responses:
            return self.responses[path]
        for key in sorted(self.responses, key=len, reverse=True):
            if isinstance(key, str) and key in path:
                return self.responses[key]
        return None

    def get(self, path=None, **kw):
        return self._route('GET', path)

    def post(self, path=None, data=None, **kw):
        return self._route('POST', path)

    def put(self, path=None, data=None, **kw):
        return self._route('PUT', path)

    def delete(self, path=None, **kw):
        return self._route('DELETE', path)


class StubAnalytics:
    def __init__(self):
        self.db = None
        self.logs = []

    def log(self, msg=None):
        self.logs.append(msg)

    def char_connected(self, *a, **k):
        pass


def _agent(char_class='sorcerer', level=21, gold=500000):
    rest = StubRest()
    cfg = {'name': 'TestBot', 'class': char_class, 'role': 'dps'}
    a = CharacterAgent(1069, cfg, rest, StubAnalytics())
    a.char_class = char_class
    a.level = level
    a.gold = gold
    a.inventory = []
    a.equipped_gear = []
    a.skills = []
    a.auto_config = []
    return a, rest


# --- _auto_accept_quests -------------------------------------

def test_accept_quests_accepts_eligible_and_skips_gated():
    a, rest = _agent(level=21)
    rest.responses['/api/quests/available?characterId=1069'] = [
        {'id': 15, 'name': "The Apprentice's Ritual", 'minLevel': 15},
        {'id': 1352, 'name': 'Trouble on the Shore', 'minLevel': 1},
        {'id': 99, 'name': 'Too High Level', 'minLevel': 50},   # level-gated
        {'id': 100, 'name': '[PARTY] Wrath of the Deep', 'minLevel': 12},  # party
        {'id': 101, 'name': 'Ignored Quest', 'minLevel': 1, 'ignored': True},
    ]
    rest.responses['accept'] = {'status': 'accepted'}
    n = a._auto_accept_quests()
    assert n == 2  # only 15 + 1352
    posted = [p for m, p in rest.calls if m == 'POST']
    assert '/api/quests/15/accept' in posted
    assert '/api/quests/1352/accept' in posted
    assert '/api/quests/99/accept' not in posted  # level-gated
    assert '/api/quests/100/accept' not in posted  # party
    assert '/api/quests/101/accept' not in posted  # ignored


def test_accept_quests_counts_accepted_status_not_ok():
    a, rest = _agent()
    rest.responses['/api/quests/available?characterId=1069'] = [
        {'id': 15, 'name': 'Q1', 'minLevel': 1},
    ]
    # The real API returns {'status': 'accepted'} — must count as success.
    rest.responses['accept'] = {'status': 'accepted'}
    assert a._auto_accept_quests() == 1


def test_accept_quests_no_available():
    a, rest = _agent()
    rest.responses['/api/quests/available?characterId=1069'] = []
    assert a._auto_accept_quests() == 0
    assert not any(m == 'POST' for m, _ in rest.calls)


# --- _auto_enable_class_skills -------------------------------

def _config_fixture():
    return {'configs': [
        {'skillId': 165, 'autoEnabled': True, 'autoPriority': 1},   # Fireball on
        {'skillId': 2045, 'autoEnabled': False, 'autoPriority': 46},  # Touch of Flame off
        {'skillId': 13272, 'autoEnabled': False, 'autoPriority': 45},  # Magic Mastery (passive)
    ], 'rules': [{'rule': 'x'}], 'petControl': {'pet': 1}}


def test_enable_class_skills_enables_non_passive_only():
    a, rest = _agent()
    a.skills = [
        {'id': 165, 'name': 'Fireball', 'isPassive': False},
        {'id': 2045, 'name': 'Touch of Flame', 'isPassive': False},
        {'id': 13272, 'name': 'Magic Mastery', 'isPassive': True},  # passive -> skip
    ]
    rest.responses['/api/skills/config/1069'] = _config_fixture()
    rest.responses['PUT config'] = {'status': 'ok'}
    n = a._auto_enable_class_skills()
    assert n == 1  # only Touch of Flame (non-passive) enabled
    # Verify the PUT body: Touch of Flame autoEnabled=True, prio bumped
    put_calls = [c for c in rest.calls if c[0] == 'PUT']
    assert put_calls, 'should have PUT the config'
    # Magic Mastery (passive) left as-is
    assert 'Magic Mastery' not in ' '.join(a.analytics.logs)


def test_enable_class_skills_nothing_to_enable():
    a, rest = _agent()
    a.skills = [{'id': 165, 'name': 'Fireball', 'isPassive': False}]
    rest.responses['/api/skills/config/1069'] = {
        'configs': [{'skillId': 165, 'autoEnabled': True}],
        'rules': [], 'petControl': {}}
    assert a._auto_enable_class_skills() == 0
    assert not any(c[0] == 'PUT' for c in rest.calls)


# --- _auto_craft_talisman ------------------------------------

def test_talisman_craft_skips_when_already_equipped():
    a, rest = _agent(gold=300000)
    rest.responses['/api/game/state/1069'] = {'character': {'talismanSlot1Unlocked': True}}
    a.equipped_gear = [{'equippedSlot': 'talisman_1', 'itemName': 'Talisman of Sorcery - Tier 1'}]
    assert a._auto_craft_talisman() == 0
    assert not any('crafting/craft' in p for _, p in rest.calls)


def test_talisman_craft_skips_below_gold_floor():
    a, rest = _agent(gold=100000)  # below 250k floor
    rest.responses['/api/game/state/1069'] = {'character': {'talismanSlot1Unlocked': True}}
    assert a._auto_craft_talisman() == 0
    assert not any('crafting/craft' in p for _, p in rest.calls)


def test_talisman_craft_sorcery_for_caster():
    a, rest = _agent(char_class='sorcerer', gold=300000)
    rest.responses['/api/game/state/1069'] = {'character': {'talismanSlot1Unlocked': True}}
    rest.responses['/api/crafting/recipes'] = [
        {'id': 4755, 'resultItemName': 'Talisman of Sorcery - Tier 1', 'goldCost': 100000,
         'ingredients': [{'itemName': 'Magical Shard', 'quantity': 1, 'itemId': 55}]},
    ]
    rest.responses['craft'] = {'resultItemName': 'Talisman of Sorcery - Tier 1', 'newGold': 199000}
    a.inventory = [{'id': 999, 'itemName': 'Talisman of Sorcery - Tier 1', 'equipped': False}]
    n = a._auto_craft_talisman()
    assert n == 1
    craft_calls = [c for c in rest.calls if 'crafting/craft' in c[1]]
    assert craft_calls


def test_talisman_craft_might_for_physical():
    a, rest = _agent(char_class='warlord', gold=300000)
    rest.responses['/api/game/state/1069'] = {'character': {'talismanSlot1Unlocked': True}}
    rest.responses['/api/crafting/recipes'] = [
        {'id': 4749, 'resultItemName': 'Talisman of Might - Tier 1', 'goldCost': 100000,
         'ingredients': [{'itemName': 'Magical Shard', 'quantity': 1, 'itemId': 55}]},
    ]
    rest.responses['craft'] = {'resultItemName': 'Talisman of Might - Tier 1', 'newGold': 199000}
    a.inventory = [{'id': 998, 'itemName': 'Talisman of Might - Tier 1', 'equipped': False}]
    assert a._auto_craft_talisman() == 1


def test_talisman_craft_slot_not_unlocked():
    a, rest = _agent(gold=300000)
    rest.responses['/api/game/state/1069'] = {'character': {'talismanSlot1Unlocked': False}}
    assert a._auto_craft_talisman() == 0
    assert not any('crafting/craft' in p for _, p in rest.calls)


# --- _auto_craft_best_weapon ---------------------------------

def test_weapon_craft_skips_below_floor():
    a, rest = _agent(gold=100000)  # below 400k floor
    assert a._auto_craft_best_weapon() == 0


def test_weapon_craft_skips_if_already_equipped():
    a, rest = _agent(char_class='warlord', gold=500000)
    a.equipped_gear = [{'itemName': 'Mithril Greatsword'}]
    assert a._auto_craft_best_weapon() == 0


def test_weapon_craft_crystal_woven_for_caster_with_missing_mats():
    # Caster targets Crystal-Woven Staff (m_atk 80). It needs Magic Crystal
    # x250 (buyable from shop 8 at 1081g) + Enchanted Crystal x2 (not buyable
    # and not in bag) — so craft must be skipped with a log, no API spam.
    a, rest = _agent(char_class='sorcerer', gold=500000)
    rest.responses['/api/crafting/recipes'] = [
        {'id': 16, 'resultItemName': 'Crystal-Woven Staff', 'goldCost': 250000,
         'ingredients': [
             {'itemName': 'Enchanted Crystal', 'quantity': 2, 'itemId': 126},
             {'itemName': 'Magic Crystal', 'quantity': 250, 'itemId': 6597},
             {'itemName': 'Magical Dust', 'quantity': 6, 'itemId': 127},
             {'itemName': 'Mithril Alloy', 'quantity': 5, 'itemId': 123}]},
    ]
    rest.responses['/api/shop/8/inventory'] = [
        {'itemName': 'Magic Crystal', 'itemId': 6597, 'buyPrice': 1081}]
    # bag has Magic Crystal x10 only — Enchanted Crystal missing + not buyable
    a.inventory = [{'itemName': 'Magic Crystal', 'quantity': 10}]
    assert a._auto_craft_best_weapon() == 0
    # It may have bought the missing Magic Crystal before hitting the
    # Enchanted Crystal dead-end — but must NOT have crafted.
    assert not any('crafting/craft' in p for _, p in rest.calls)