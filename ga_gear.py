"""Module ga_gear — extracted from grimeage_agent.py (behavior-preserving split)."""
from dataclasses import dataclass
from ga_catalog import ARMOR_TREE, WEAPON_TREE


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


