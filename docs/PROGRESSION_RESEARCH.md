# GrimeAge2 Progression Research (2026-08-05)

Deep-dive results from client JS (`/tmp/gr2chunks/`) + live API probes.

## Class Ascendancy — THE big lever
- All 3 chars ascended (API allows without finishing quest 3):
  - BuffBot → **sorcerer** (Fireball, Touch of Flame, Magic Mastery, Blink@48)
  - HermesHeal → **bishop** (Holy Bolt, Smite, Wrath of God@28, Greater Heal@40)
  - ShieldBot → **warlord** (Power Smash, Lightning Strike, Two Handed Weapon
    Master, Lion's Pride, Head First)
- POST /api/ascendancy/ascend {characterId, ascendedClass} — worked from
  hunting zone, no quest completion required.
- Ascension grants +HP/+MP at unlock (e.g. 170 HP / 99 MP for fighter paths).
- Class skills trainable from trainer 9 AFTER ascension (was None before).

## Skill rotations — critical gotcha
- Class skills are added to config with autoEnabled=FALSE after ascension.
  Must PUT /api/skills/config/{cid} {skills:[...]} to enable them.
- Config skillIds DIFFER from character skill ids (Robe Mastery config id
  13299 vs char skill id 205). PUT with wrong id → 403 "skill not in
  character config". Always read config first, reorder its own ids.
- Config PUT FAILS for dead characters (403/None). Apply while alive.
- Healer (bishop) must heal-first: Heal@75% > Battle Heal@65% > Group
  Heal@50% > Smite > Holy Bolt > Wind Strike. DPS-first kills her in 64188.

## Warehouse — ACCOUNT-SHARED, remote access works
- Path uses **warehouse NPC id**, not characterId:
  GET /api/warehouse/1051/gold (Gludios clerk)
  POST /api/warehouse/1051/deposit-gold {characterId, amount}
  POST /api/warehouse/1051/withdraw-gold {characterId, amount}
- Works REMOTELY from hunting zones. Client subtitle: "Shared across all
  your characters".
- Old code used /api/warehouse/{cid}/gold → returns None. WRONG.

## Shop buy works remotely
- POST /api/shop/8/buy {characterId, itemId, quantity} works from hunting
  zones. Item lands in bag, then equip via /api/inventory/{cid}/equip
  {inventoryId}.

## WS connection behavior
- Server closes idle WS connections within ~2s. Send commands immediately
  after connect (no settle sleep).
- Server caps 2 simultaneous farm sessions; a 3rd char's WS is evicted.
- To travel a char whose WS gets evicted: pause one farmer first
  (toggle AF off), then travel, then resume.

## Talismans (post Warchief's Gift quest)
- Quest 4 "The Warchief's Gift" (advance→complete→claim) unlocks
  talismanSlot1 on all chars. Reward action: unlock_talisman_slot.
- Tier 2 talismans: 250k gold, +6% stat (Might=p_atk, Sorcery=m_atk,
  Iron=p_def, Life=max_hp, Warding=m_def, Wisdom=max_mp, Restoration=regen).
- Timed buffs (remaining_seconds in instanceMetadata) — gold upkeep.

## Class skill trees (client JS, skills-D_hgiBUd.js)
- sorcerer: Fireball(20), Aura Flare(52), Blink(48), Overchannel(58), Sleep(25)
- bishop: Holy Bolt(20), Smite(20), Wrath of God(28), Greater Heal(40),
  Benediction(40), Purify(58), Sleep(25)
- warlord: Power Smash(20), Lightning Strike(20), Two Handed Weapon
  Master(20), Power Shout(20+), Lion's Shout, Anger Shout, Armor Crush
- dark_avenger: Life Drain(20), Summon Dark Panther(20), Life Scavenge(25),
  Reflect Damage(40)
- necromancer: Death Spike(20), Life Drain(20), Summon Corrupted Man(20),
  Fear, Soul Rupture(58)
- Level requirements are the key gating factor; core class DPS skills all
  unlock at Lv20.
