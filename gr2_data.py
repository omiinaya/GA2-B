"""gr2_data — zone progression tiers, weapon/armor/accessory trees, recipes."""
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

