"""Unit tests for pure-logic rotation methods in ga_character.py.

These methods have no network dependency (no live-game calls), so they can be
unit-tested standalone by instantiating CharacterAgent with a stub REST client
and a fake Analytics. Covers the rotation-critical logic that determines
whether skills are usable + gated — regressions here silently nerf (or flail)
the character's combat rotation.

Run: python3 -m pytest tests/test_character_logic.py -q
"""
import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ga_character import CharacterAgent


class _StubRest:
    """Minimal stand-in so CharacterAgent can be constructed without network."""

    def __init__(self):
        self.calls = []

    def get(self, path=None, **kw):
        self.calls.append(('get', path))
        return None

    def post(self, path=None, data=None, **kw):
        self.calls.append(('post', path))
        return None

    def put(self, path=None, data=None, **kw):
        self.calls.append(('put', path))
        return None

    def delete(self, path=None, **kw):
        self.calls.append(('delete', path))
        return None


class _StubAnalytics:
    def __init__(self):
        self.db = None
        self.logs = []

    def log(self, msg=None):
        self.logs.append(msg)

    def char_connected(self, *a, **k):
        pass


def _agent(char_class='fighter', equipped_gear=None, level=20):
    rest = _StubRest()
    cfg = {'name': 'TestBot', 'class': char_class, 'role': 'dps'}
    a = CharacterAgent(1069, cfg, rest, _StubAnalytics())
    a.char_class = char_class
    a.equipped_gear = equipped_gear or []
    a.skills = []
    a.auto_config = []
    a.inventory = []
    a.level = level
    a.gold = 0
    return a, rest


# --- _check_weapon_requirement -------------------------------

def test_weapon_requirement_no_requirement():
    a, _ = _agent()
    assert a._check_weapon_requirement([], 'no weapon is always True')


def test_weapon_requirement_exact_match():
    a, _ = _agent()
    # 'bow' in {'short', 'bow'} -> inclusion matched
    assert a._check_weapon_requirement(['bow'], 'short bow') is True
    assert a._check_weapon_requirement(['dagger'], 'short bow') is False


def test_weapon_requirement_not_bow_does_not_match_broad_sword():
    a, _ = _agent()
    # 'bow' must NOT match 'broad sword' (word-boundary, not substring)
    assert a._check_weapon_requirement(['bow'], 'broad sword') is False


def test_weapon_requirement_exclusion():
    a, _ = _agent()
    # any weapon except bow/dagger; a sword satisfies it
    assert a._check_weapon_requirement(['-bow', '-dagger'], 'broad sword') is True
    # a dagger violates the exclusion
    assert a._check_weapon_requirement(['-bow', '-dagger'], 'assassins dagger') is False


def test_weapon_requirement_no_weapon_inclusion_only():
    a, _ = _agent()
    # no weapon + an inclusion requirement (['daggger']) -> blocked (needs a dagger)
    assert a._check_weapon_requirement(['dagger'], '') is False


def test_weapon_requirement_no_weapon_exclusion_only():
    a, _ = _agent()
    # no weapon + exclusion-only (['-bow','-dagger']) -> allowed (any weapon ok)
    assert a._check_weapon_requirement(['-bow', '-dagger'], '') is True


# --- _is_skill_gated ------------------------------------------

def test_skill_gated_no_config():
    a, _ = _agent()
    assert a._is_skill_gated(None, 0.5, 0.5) is False


def test_skill_gated_hp_threshold():
    a, _ = _agent()
    # heal gated to fire when HP < 75%
    cfg = {'gateSelfHpMin': 0, 'gateSelfHpMax': 75}
    assert a._is_skill_gated(cfg, 0.5, 0.5) is False  # 50% < 75% -> allowed
    assert a._is_skill_gated(cfg, 0.9, 0.5) is True   # 90% > 75% -> blocked


def test_skill_gated_mp_threshold():
    a, _ = _agent()
    # mp-gated skill usable only below 30% MP
    cfg = {'gateSelfMpMin': 0, 'gateSelfMpMax': 30}
    assert a._is_skill_gated(cfg, 0.5, 0.2) is False  # 20% < 30% -> allowed
    assert a._is_skill_gated(cfg, 0.5, 0.8) is True   # 80% > 30% -> blocked


def test_skill_gated_both_bounds():
    a, _ = _agent()
    cfg = {'gateSelfHpMin': 20, 'gateSelfHpMax': 80, 'gateSelfMpMin': 0, 'gateSelfMpMax': 100}
    assert a._is_skill_gated(cfg, 0.5, 0.5) is False  # within bounds
    assert a._is_skill_gated(cfg, 0.1, 0.5) is True   # too low HP
    assert a._is_skill_gated(cfg, 0.9, 0.5) is True   # too high HP


# --- _skill_efficiency ----------------------------------------

def test_skill_efficiency_higher_for_faster_cycle():
    a, _ = _agent()
    fast = {'skillId': 1, 'autoPriority': 5}
    slow = {'skillId': 2, 'autoPriority': 6}
    a.skills = [
        {'id': 1, 'castTimeMs': 500, 'cooldownSeconds': 2},
        {'id': 2, 'castTimeMs': 2000, 'cooldownSeconds': 10},
    ]
    eff_fast = a._skill_efficiency(fast)
    eff_slow = a._skill_efficiency(slow)
    assert eff_fast > eff_slow
    # cycle = cast_s + cd; freq = 1/cycle
    assert math.isclose(eff_fast, 1.0 / 2.5, rel_tol=1e-6)


def test_skill_efficiency_unknown_skill():
    a, _ = _agent()
    assert a._skill_efficiency({'skillId': 999}) < 0.02  # ~0.01 fallback


# --- _get_current_weapon -------------------------------------

def test_current_weapon_slot_based():
    a, _ = _agent(equipped_gear=[{'slot': 'main_hand', 'itemName': 'Mithril Greatsword'}])
    assert a._get_current_weapon() == 'Mithril Greatsword'


def test_current_weapon_name_keyword_fallback():
    a, _ = _agent(equipped_gear=[
        {'slot': None, 'itemName': 'Arcane Staff'},  # slot is null
    ])
    assert a._get_current_weapon() == 'Arcane Staff'


def test_current_weapon_none_equipped():
    a, _ = _agent(equipped_gear=[])
    assert a._get_current_weapon() == ''