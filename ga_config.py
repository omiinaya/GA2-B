"""Module ga_config — extracted from grimeage_agent.py (behavior-preserving split)."""
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
