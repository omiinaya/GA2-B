# GrimeAge2 Progression API Reference

Reverse-engineered 2026-08-04 from the game client
(`/tmp/gr2chunks/` — ThreatMeter-wfSt4aDJ.js is the giant module holding the
panels/API). All endpoints are relative to `https://grimeage2.com`; auth via
`Authorization: Bearer <token>`. `cid` = characterId.

## Character / account
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/characters` | list chars (id, name, level, class, gold, hp, currentZoneId, state) |
| GET | `/api/characters/{cid}/stats` | per-char stats |
| GET | `/api/characters/{cid}/public` | public profile |
| GET | `/api/account/settings` / PUT | account settings |

## Game / world
| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/game/enter/{cid}` | enter game |
| GET | `/api/game/state/{cid}` | character/zone/players/deathInfo runSpeed |
| GET | `/api/world/map` | zones(516), connections, crossLinks, labels, images |
| GET | `/api/world/map/dungeon/{cid}` | dungeon map |
| GET | `/api/world/zones/{zid}` | zone detail |
| GET | `/api/combat/monsters/{zid}` | monster spawns in zone |
| GET | `/api/combat/loot-table/{zid}` | loot table |

## Skills & training  (TRAINER NPC = 9, "advanced combat techniques")
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/skills/character/{cid}` | skills with `skillLevel`, `trainingCostGold`, `levelRequired`, `type`, `power`, classes/races |
| GET | `/api/skills/{skillId}` | skill detail |
| GET | `/api/skills/config/{cid}` | autoConfig: `{configs:[...], rules:[...], petControl}` |
| PUT | `/api/skills/config/{cid}` | body `{skills, rules, petControl}` (NOT autoConfig!) |
| GET | `/api/skills/config/rule-catalog/{cid}` | rule options |
| GET | `/api/skills/config/feedback/{cid}` | config feedback |
| POST | `/api/skills/config/dry-run/{cid}` | validate config |
| GET | `/api/training/{npc}/skills?characterId={cid}` | **trainable skills**: `canLearn`, `trainingCostGold`, `trainingCostGold` |
| POST | `/api/training/{npc}/train` | body `{characterId, skillId}` → `{status: ok}` |

Training verified working 2026-08-04 (ShieldBot 5 skills to Lv3). No proximity
gate — works from any zone. Skill rotations are applied via the config PUT.

## Items / inventory
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/inventory/{cid}` | `{equipped, bag, bagSlots, weight, effectiveHp/Mp}` |
| POST | `/api/inventory/{cid}/equip` | `{inventoryId}` (bag item `id`) → `{status, unequipped:[slot]}` |
| POST | `/api/inventory/{cid}/unequip` | `{slot}` |
| POST | `/api/inventory/{cid}/{invId}/use` | use consumable |
| DELETE | `/api/inventory/{cid}/{invId}` | discard |

Stats live in `statsJson` (JSON string), e.g. `{"p_def": 37, "max_hp": 70}`.

## Shop  (SHOP NPC = 8)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/shop/{npc}/inventory` | buyable items: `itemId`, `name`, `buyPrice`, `slot`, `statsJson`, `levelRequired` |
| POST | `/api/shop/{npc}/buy` | `{characterId, itemId, quantity}` → `{status: ok}` |
| POST | `/api/shop/{npc}/sell` | `{characterId, inventorySlotId, quantity}` |
| POST | `/api/shop/{npc}/sell-prices` | `{characterId, inventorySlotIds}` → prices |
| GET | `/api/npcs/{npc}/dialogue` | NPC role text + options (trainer='advanced combat techniques') |

Buy→equip flow verified: buy → item lands in bag → equip by bag entry `id`.

## Ascendancy  (class change, Lv20+)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/ascendancy/options?characterId={cid}` | options: `id`, `baseClass`, `parentClass`, `ascendedClass`, `hpGainAtCurrentLevel`, `mpGainAtCurrentLevel` |
| POST | `/api/ascendancy/ascend` | body `{characterId, ascendedClass}` — **class slug**, NOT ascendancyId |

wizard → bishop(cleric)/necromancer(mage)/prophet(cleric)/sorcerer(mage).
fighter → dark_avenger(knight)/gladiator(warrior)/hawkeye(rogue)/paladin(knight)/
treasure_hunter(rogue)/warlord(warrior).
Quest gate: Trial of Ascendancy (quest 3) — kill 10 Bandit Scouts. Real progress
is in active-quest `stageInfo.current/target`; the quest template `completionState`
is NOT progress.

## Quests
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/quests/available?characterId={cid}` | available quests |
| GET | `/api/quests/active?characterId={cid}` | active quests incl `stageInfo{current,target}` |
| POST | `/api/quests/{qid}/accept` | `{characterId}` |
| POST | `/api/quests/{qid}/complete` | `{characterId}` |
| POST | `/api/quests/{qid}/advance` | `{characterId}` |
| POST | `/api/quests/{qid}/claim` | `{characterId, itemSlug}` |
| POST | `/api/quests/{qid}/ignore` | `{characterId}` |

## Crafting
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/crafting/recipes` | recipes: `resultItemName`, `resultStatsJson`, `goldCost`, `resultRarity` |
| GET | `/api/crafting/sets` | set bonuses |
| GET | `/api/crafting/context/{cid}` | crafting context |
| GET | `/api/crafting/items/{cid}/sources` | item sources |
| GET | `/api/crafting/favorites/{cid}` | favorites |
| POST | `/api/crafting/craft` | `{characterId, recipeId, quantity}` |
| POST | `/api/crafting/favorites/{cid}/{qid}` | toggle favorite |

## Enchanting
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/enchant/preview?characterId=&scrollInventoryId=&targetInventoryId=` | preview enchant result |
| POST | `/api/enchant` | body with characterId + scroll/target inventory ids |

## Banners / talismans / misc
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/clan-ritual/shop` | banner shop |
| POST | `/api/clan-ritual/shop/buy` | buy banner |
| GET | `/api/olympiad/shop` | olympiad shop |
| POST | `/api/olympiad/shop/buy` | buy olympiad item |
| GET | `/api/auction/*` | auction house (buy/buy-commodity/buyout) |

## Wiring (agent, 2026-08-04)
- `_auto_train_skills()` — all affordable `canLearn` skills from trainer NPC 9.
- `_auto_buy_gear_upgrades()` — armor/accessory upgrades from shop 8, 50% gold
  budget, equips via bag item id.
- `_claim_completed_quests()` — completes+claims quests whose `stageInfo.current`
  reached `target`.
- `ASCEND_PREF` (gr2_data) — role-aware ascendancy class per char.
- All wired into `_handle_game_state` first-connect path.
## Warehouse (2026-08-05 — CORRECTED)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/warehouse/{npcId}/gold` | **ACCOUNT-SHARED** balance; `{npcId}` = warehouse NPC id (Gludios clerk = 1051), NOT characterId |
| POST | `/api/warehouse/{npcId}/deposit-gold` | `{characterId, amount}` — works REMOTELY from hunting zones |
| POST | `/api/warehouse/{npcId}/withdraw-gold` | `{characterId, amount}` — works REMOTELY |
| GET | `/api/warehouse/{npcId}/items` | shared item vault (empty here) |

⚠️ Early code used `/api/warehouse/{cid}/gold` (character id) — that returns
None. The client JS (`ThreatMeter` WarehouseModal) passes the **warehouse NPC
id** and the subtitle reads "Shared across all your characters". Verified live
2026-08-05: deposit 223k (ShieldBot) → withdraw 200k (BuffBot) both ok from
hunting zones.

## Ascendancy / class change (2026-08-05 — verified live)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/ascendancy/options?characterId=` | 4 classes per base class, `minLevel: 20`, hp/mp gain at unlock |
| POST | `/api/ascendancy/ascend` | `{characterId, ascendedClass}` — **works without completing quest 3!** |

wizard → sorcerer/necromancer (mage), bishop/prophet (cleric)
fighter → warlord/gladiator (warrior), paladin/dark_avenger (knight),
hawkeye/treasure_hunter (rogue)
Core class skills unlock at Lv20 (Fireball, Holy Bolt, Smite, Power Smash,
Lightning Strike, Two Handed Weapon Master, ...) — trainable from trainer 9
after ascension. Config skillIds differ from character skill ids (e.g. Robe
Mastery config id 13299 ≠ char id 205); PUT full config with wrong id →
403 "skill not in character config".
