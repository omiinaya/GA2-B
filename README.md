# GA2-B — GrimeAge2 Automation Bot

Automation bot for the [GrimeAge2](https://grimeage2.com) browser MMORPG.

**Goal:** make party-based **manual combat AI** farming more efficient than the
server's built-in **auto-farm** mode.

## Files

| File | Role |
|------|------|
| `grimeage_agent.py` (~5000 lines) | Main agent. `CharacterAgent` (WebSocket/REST client, combat AI, empirical skill profiler, rest/regen management, threat-based tank targeting) + `AgentCoordinator` (3-char party orchestration) |
| `gr2-combat-daemon.py` | Headless party daemon — connects all 3 chars, forms party, enables manual combat AI, manages monster reseeds. Supervised by the brain. |
| `gr2-brain.py` | Cron supervisor (every 5 min): zone progression, gear, quests, skill rotations; auto-starts/restarts the combat daemon; clears stale cron lock. |

## Architecture

- **REST + WebSocket client** against `https://grimeage2.com` / `wss://grimeage2.com/ws?token=…&characterId=…`
- **Party manual farm**: daemon coordinates tank / healer / DPS. Tank picks targets by threat + HP-weighting (focus fire), healer gates heals at HP thresholds (conserves mana vs auto-farm which burns all MP on Group Heal), DPS runs efficiency-sorted skill rotation.
- **Empirical profiler**: cast times, server latency, GCD, regen rates, and cooldown drift are measured from server events — never hardcoded.
- **Monster seeding**: the server only spawns monsters for recent auto-farm activity. The agent pre-seeds on start (25s party window) and re-seeds on a timer.
- **Rest system**: role-based HP/MP thresholds with force-exit from stale combat state and dynamic rest timeouts from measured regen.

## Efficiency Status

| Mode | Gold/hr (Lv17-23, zone 44341 era) | Notes |
|------|----------------------------------|-------|
| Auto-farm (solo, server AI) | ~30,000 (very stable) | No WS dependency; auto-loot is server-side |
| Manual AI (party of 3) | ~37,800 (session test: +15%) | Gold shared in party; healer mana management is the big win (+209% healer gold/min vs auto-farm) |
| Manual AI (solo) | 0–23,500 | Solo manual gets no auto-loot — party mode is REQUIRED for income |

The project iterates on closing this gap with live 15-min H2H tests.

## Deployment

Canonical live-box layout:

```bash
cp grimeage_agent.py     /home/hindsight/grimeage_agent.py
cp gr2-combat-daemon.py ~/.hermes/scripts/gr2-combat-daemon.py
cp gr2-brain.py         ~/.hermes/scripts/gr2-brain.py
```

Credentials (never committed): `GR2_EMAIL` / `GR2_PASSWORD` env vars, or a
`.env` file next to the scripts (`KEY=VALUE` lines).

Daemon (manual):
```bash
python3 -u ~/.hermes/scripts/gr2-combat-daemon.py
```
Writes `~/.hermes/gr2-combat-daemon.pid` / `~/.hermes/gr2-combat-daemon.log`.
Supervised automatically by `gr2-brain.py` under cron.

Brain (cron, every 5 min):
```
*/5 * * * * cd ~/.hermes/scripts && python3 gr2-brain.py >> ~/.hermes/gr2-brain.log 2>&1
```

## Testing

Live-game test harnesses (in `~/.hermes/skills/grimeage2-agent/scripts/`):
- `gr2-char-status.py` — REST status snapshot (gold is the reliable metric)
- `gr2-solo-h2h.py` — 15-min auto-farm vs manual AI head-to-head
- `gr2-compare-test.py` — 5-min auto vs manual on one char

Comparison rules: keep both modes in the SAME zone, run 15+ min, use API gold
snapshots, log WS drops, same WS stack for both phases.
