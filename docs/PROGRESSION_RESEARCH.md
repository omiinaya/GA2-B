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

## 2026-08-05 PM session — progression levers EXECUTED (all verified live)

### BuffBot death spiral — ROOT CAUSE FOUND + FIXED
- **Two compounding bugs** (not zone difficulty):
  1. Weapon mismatch: BuffBot (sorcerer, m_atk class) was wielding Mithril
     Stiletto (m_atk 36) while Arcane Staff (m_atk 55) sat in his bag —
     19-point m_atk loss on his damage stat. Auto-equip logic was sound but
     something had overridden the staff.
  2. Class skills DISABLED: after ascension the server adds class skills to
     the rotation config with autoEnabled=FALSE. BuffBot had Touch of Flame
     (power 80) + Magic Mastery disabled — his rotation lacked class DPS.
- Fix: equipped Arcane Staff (m_atk 55), enabled class skills, added
  `_auto_enable_class_skills()` to ga_character.py connect path (enables all
  disabled non-passive skills, PUT full config). Verified: all 3 chars now
  have 0 disabled non-passive skills. BuffBot went from dying repeatedly
  (negative gold) to full HP + farming.

### Talismans — CRAFTED 24h buffs, unlock via quest 3 chain
- talismanSlot1Unlocked=True on all chars after claiming Trial of Ascendancy
  (quest 3) with the CHAIN advance→complete→claim (multi-stage quests drop
  stageInfo to None + set awaitingRewardChoice=True — old complete→claim
  alone 403s).
- Craft recipes: Tier 1 = 100k + Magical Shard x1 (+3%); Tier 2 = 250k +
  Dark Crystal x1 + Magical Shard x1 (+6%); Tier 3 = 1M + Stone of Purity
  (+10%). 24h duration (remaining_seconds=86400), slot talisman_1.
- Stat mapping: Sorcery=m_atk, Might=p_atk, Life=max_hp, Iron=p_def,
  Warding=m_def, Wisdom=max_mp, Restoration=regen.
- Craft works REMOTELY from hunting zones. Verified live: HermesHeal crafted
  + equipped Talisman of Sorcery Tier 1 (+3% m_atk).

### 🔓 Magic Crystal IS SHOP-BUYABLE — crafting economy UNBLOCKED
- **The 2026-08-04 buy test returned null ONLY because the char was dead.**
  Live re-test: POST /api/shop/8/buy {characterId, itemId:6597, qty} →
  {status: ok}, 1,081 gold each. The ENTIRE Mithril-tier craft ladder is now
  reachable: Mithril Warhammer 82 / Mithril Greatsword 105 / Crystal-Woven
  Staff m_atk 80.
- Archmage's Staff (m_atk 110) + Runic weapons + Tier-3 talismans still need
  Stone of Purity x5 (drop-only, not in any shop or recipe).
- Dark Crystal (for Enchanted Crystal via recipe 3) is drop-only too.
- Reachable caster upgrade: Crystal-Woven Staff (250k + EnchCrystal x2 +
  Magic Crystal x250 + Dust x6 + Alloy x5) — m_atk 80 vs Arcane 55.

### Token shops (clan-ritual + olympiad) — grind-gated, not farmable here
- GET /api/clan-ritual/shop?characterId= and /api/olympiad/shop?characterId=
  both return {tokenBalance: 0, items: [...]}. Items need clan-ritual /
  olympiad PvP tokens, NOT gold — no path to earn them in the farm loop.
- Olympiad has Enchant Weapon/Armor Scrolls (would be huge) but token-gated.

### Continuous gold pooling (2026-08-05 16:50, verified live)
- Connect-level `_auto_pool_gold()` misses the PERMANENT farmer — BuffBot
  holds one of the 2 farm slots permanently (rotation only swaps the 3rd
  between HermesHeal and ShieldBot), so his connect never fires.
- Supervisor-level `pool_gold_cycle()` runs every GR2_POOL (default 300s)
  and balances ALL chars through the shared warehouse (NPC 1051):
  - gold > 80k keep  -> deposit surplus
  - gold < 80k keep  -> withdraw up to 150k fill (pool >= 10k min)
- Verified live: BuffBot 61,753 -> 150,387 (funded for Fireball Lv2 150k +
  Magic Mastery 60k at Lv24/25), ShieldBot 126,890 -> 80,000 (deposited),
  HermesHeal 24,154 -> 65,827, warehouse 129,050 -> 6,003. Pool fully
  redistributed. Gold economy is now self-balancing.

### Progression pass for the PERMANENT farmer (2026-08-05 17:10, root cause)
- DISCOVERY: BuffBot holds one of the 2 farm slots permanently (rotation only
  swaps the 3rd between HermesHeal and ShieldBot), so the supervisor NEVER
  WS-connects him → his connect-path progression NEVER ran: auto-equip
  (farmed with Mithril Stiletto m_atk 36 while Arcane Staff m_atk 55 sat in
  the bag — 53% m_atk loss), auto-train, talisman craft, quest accept/claim.
  Only rotated chars (ShieldBot) produced progression lines in the journal.
- FIX: supervisor-level `progression_pass()` briefly connects EVERY char
  (serial, ~3s each) on a timer (GR2_PROGRESSION, default 20 min), firing
  the connect-path wiring for all chars regardless of rotation status.
- connect() does NOT start manual combat (combat_enabled False) — safe to
  run during AF farming. Verified: manual Arcane Staff equip worked
  (m_atk 36 → 55); the 20-min pass makes it automatic going forward.
