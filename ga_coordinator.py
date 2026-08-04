"""Module ga_coordinator — extracted from grimeage_agent.py (behavior-preserving split)."""
import asyncio
import sys
import time
from ga_config import ACCOUNT_EMAIL, ACCOUNT_PASSWORD, CHARACTERS
from ga_analytics import Analytics
from ga_db import init_db
from ga_rest import RestClient
from ga_world import WorldData
from ga_character import CharacterAgent


class AgentCoordinator:
    """
    Top-level agent that coordinates all characters:
    - Connects all characters
    - Forms a party
    - Assesses each character's gear/level
    - Finds optimal farming zones
    - Manages health & safety
    - Reports periodically
    """
    
    def __init__(self):
        self.rest = RestClient(ACCOUNT_EMAIL, ACCOUNT_PASSWORD)
        self.db = init_db()
        self.analytics = Analytics(self.db)
        self.world = WorldData(self.rest)
        self.chars = { }
        self._running = False
        self._main_loop_task = None
        self._last_report_time = 0
        self._report_interval = 60
        self._progression_check_interval = 120
        self._last_progression_check = 0
        self.combat_enabled = False
        self.start_time = time.time()
        self._last_seed_time = 0
        self._last_reseed_check = 0
        self._reseed_interval = 90
        self._party_zone_id = None
        self._last_straggler_check = 0

    
    async def start(self):
        '''Login, create agents, connect all, start main loop.'''
        self.analytics.log('🚀 AgentCoordinator starting...')
        self.rest.login()
        await asyncio.sleep(0.5)
        self.world.load()

        # Create CharacterAgents
        for cid, config in CHARACTERS.items():
            agent = CharacterAgent(cid, config, self.rest, self.analytics)
            self.chars[cid] = agent
            self.analytics.char_connected(cid, config['name'], None, 0)

        # Connect all characters
        self.analytics.log('Connecting all characters...')
        for cid in sorted(self.chars):
            agent = self.chars[cid]
            ok = await agent.connect()
            if ok:
                self.analytics.log(f'  ✓ {agent.name} connected')
            else:
                self.analytics.log(f'  ✗ {agent.name} connection failed')
            await asyncio.sleep(1)

        # Link partner references for cross-character awareness
        for cid, agent in self.chars.items():
            partners = {ocid: oa for ocid, oa in self.chars.items() if ocid != cid}
            agent.link_partner_agents(partners)

        # Initial assessment
        await self._initial_assessment()

        # Start main loop
        self._running = True
        self._main_loop_task = asyncio.create_task(self._main_loop())
        self.analytics.log('✅ AgentCoordinator running')

    async def _initial_assessment(self):
        '''First-time setup: seed monsters, form party, enable combat.'''
        self.analytics.log('📋 Initial assessment...')
        # Wait for all characters to be ready
        for cid, agent in self.chars.items():
            if not agent.connected:
                self.analytics.log(f'  ⏳ Waiting for {agent.name}...')

        # Log initial levels and gold
        for cid, agent in self.chars.items():
            self.analytics.log(f'  [{agent.name}] Lv{agent.level} | {agent.gold} gold | Zone {agent.current_zone_id}')
            self.analytics.track_rewards(cid, 0, agent.gold)

        # World load if not already
        if not self.world._loaded:
            self.world.load()

        # Seed monsters first (party + auto-farm don't mix)
        self.analytics.log('🌱 Initial monster seeding...')
        await self._coord_reseed()

    async def _main_loop(self):
        '''Main agent loop — runs every 5 seconds.'''
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.analytics.track_error('Coordinator', f'Main loop: {e}')
            await asyncio.sleep(5)

    async def _tick(self):
        '''Single agent cycle.'''
        now = time.time()

        # Safety check
        await self._check_safety()

        # Party integrity
        if now - getattr(self, '_last_party_check', 0) > 30:
            self._last_party_check = now
            await self._ensure_party()

        # Party cohesion: pull stragglers back to the party zone so the party
        # can actually form / stay together (reconnects, respawns, scatter).
        await self._travel_stragglers()

        # Monster reseed check (only when combat is running)
        if self.combat_enabled and now - self._last_reseed_check > 10:
            self._last_reseed_check = now
            await self._check_monsters()

        # Progression
        if now - self._last_progression_check > self._progression_check_interval:
            self._last_progression_check = now
            await self._progression_check()

        # Report
        if now - self._last_report_time > self._report_interval:
            self._last_report_time = now
            report = self.analytics.report()
            if report:
                self.analytics.log(report)

    async def _check_safety(self):
        '''Ensure all characters are alive and healthy.
        When combat AI is running, it handles rest/respawn itself.
        This is a safety net for edge cases.'''
        for cid, agent in self.chars.items():
            if not agent.connected:
                continue
            # Respawn if dead and no combat AI running
            if agent.is_dead and not agent.combat_enabled:
                await agent.ws_send('respawn', {})
                await asyncio.sleep(2)

    async def _check_monsters(self):
        '''Check monster counts across all chars. If total pool is low or
        a char is stuck with the same 1 monster for too long, trigger reseed.'''
        if not self.chars:
            return
        now = time.time()

        # Skip if we reseeded recently
        if now - self._last_seed_time < self._reseed_interval:
            return

        total_monsters = 0
        all_low = True
        stale_target = None

        for cid, agent in self.chars.items():
            if not agent.connected:
                continue
            agent._clean_monsters()
            mcount = len(agent.monsters)
            total_monsters += mcount

            # If any char has 2+ monsters, the zone is alive — don't reseed
            if mcount >= 2:
                all_low = False

            # Stale single-monster detection: same 1 monster for >45s
            if mcount == 1:
                stale_key = f'{cid}_mon_count'
                prev = getattr(self, stale_key, None)
                if prev == 1:
                    stale_since = getattr(self, f'{cid}_mon_stale_since', now)
                    if now - stale_since > 45:
                        stale_target = (cid, agent)
                        self.analytics.log(f'  🐌 {agent.name}: same 1 monster for >45s — forcing reseed')
                else:
                    setattr(self, f'{cid}_mon_stale_since', now)
                setattr(self, stale_key, mcount)

        # Trigger reseed if total pool is tiny OR a char is stale
        if total_monsters < 2 or stale_target or (total_monsters < 3 and all_low):
            self.analytics.log(f'🌀 Low monster pool ({total_monsters} total across all chars) — coordinated reseed...')
            await self._coord_reseed()

    async def _coord_reseed(self):
        '''Disband party → travel to common zone → seed monsters → re-form party → re-enable combat.'''
        if not self.chars:
            return

        # 1. Disable combat on all chars first
        for cid, agent in self.chars.items():
            if agent.combat_enabled:
                await agent.disable_combat()

        # 2. Disband party: lets leave on all chars
        sorted_ids = sorted(self.chars.keys())
        # Non-leaders leave first, then leader
        for cid in sorted_ids[1:]:
            agent = self.chars[cid]
            if agent.connected and agent.is_in_party:
                await agent.ws_send('party:leave', {})
                await asyncio.sleep(1)
        leader = self.chars[sorted_ids[0]]
        if leader.connected and leader.is_in_party:
            await leader.ws_send('party:leave', {})
            await asyncio.sleep(2)
        # Reset party state on all
        for cid, agent in self.chars.items():
            agent.is_in_party = False
            agent.party_members = {}

        # 3. Travel all chars to the SAME hunting zone (never a city).
        #    Old code picked the first char's _hunting_zone_id or current zone
        #    — usually zone 149 (Gludios city) at startup — then seeded in the
        #    city (0 monsters) and re-enabled combat, letting each agent's own
        #    zone finder scatter to different hunting grounds (no party, no
        #    shared gold, reseed ping-pong back to the city). Pick a real
        #    hunting_ground that every connected char can reach and that
        #    covers the lowest level in the party.
        min_level = None
        for cid in sorted_ids:
            agent = self.chars[cid]
            if agent.connected and agent.level:
                if min_level is None or agent.level < min_level:
                    min_level = agent.level
        target_zone = None
        # Preferred: a char's existing hunting zone that is a valid hunting
        # ground covering the whole party (lowest level included).
        for cid in sorted_ids:
            agent = self.chars[cid]
            if not agent.connected:
                continue
            hz = agent._hunting_zone_id or agent.current_zone_id
            zi = self.world.zones.get(hz)
            if (hz and zi and zi.zone_type == 'hunting_ground'
                    and min_level is not None
                    and zi.level_min <= min_level <= zi.level_max):
                target_zone = hz
                break
        if not target_zone:
            target_zone = self._pick_common_hunting_zone(sorted_ids, min_level)
        # Last resort: any non-city zone a connected char is in.
        if not target_zone:
            for cid in sorted_ids:
                agent = self.chars[cid]
                if agent.connected and agent.current_zone_id != 1:
                    zi = self.world.zones.get(agent.current_zone_id)
                    if zi and zi.zone_type != 'city':
                        target_zone = agent.current_zone_id
                        break
        if not target_zone:
            self.analytics.log('⚠️ No reachable hunting zone found — staying put')
        else:
            zi = self.world.zones.get(target_zone)
            self.analytics.log(f'📍 Party hunting zone: {target_zone} ({zi.name if zi else "?"})')
        # Pin every agent to the common zone so enable_combat's zone finder
        # doesn't scatter them to individual choices after re-enable.
        if target_zone:
            for cid in sorted_ids:
                agent = self.chars[cid]
                if agent.connected:
                    agent._hunting_zone_id = target_zone

        if target_zone:
            self._party_zone_id = target_zone  # _travel_stragglers keeps the party together on the main tick
            self.analytics.log(f'📍 Traveling all chars to zone {target_zone}...')
            # Round-up passes: chars mid-reconnect get skipped on the first
            # pass (the old code traveled once and gave up — stragglers sat in
            # the city forever, so no party could ever form). Re-travel every
            # connected char until all are in the party zone.
            for _pass in range(4):
                stragglers = []
                for cid in sorted_ids:
                    agent = self.chars[cid]
                    if agent.connected and agent.current_zone_id != target_zone:
                        stragglers.append(agent)
                if not stragglers:
                    break
                for agent in stragglers:
                    await self._travel_agent_to(agent, target_zone)
                await asyncio.sleep(8)
            # 3b. Bounded wait for every connected char to reach the party
            #     zone. Party invites require same zone, and enable_combat on a
            #     char that isn't there yet lets its own zone finder scatter it
            #     elsewhere (the old flow enabled combat immediately, so the
            #     party never formed and the tank died without heals).
            waited = 0
            while waited < 150:
                missing = [self.chars[cid] for cid in sorted_ids
                           if self.chars[cid].connected
                           and self.chars[cid].current_zone_id != target_zone]
                if not missing:
                    break
                for agent in missing:
                    await self._travel_agent_to(agent, target_zone)
                await asyncio.sleep(15)
                waited += 15

        # 4. Pick seed char that's ALREADY in the target zone
        seed_char = None
        for cid in sorted_ids:
            c = self.chars[cid]
            if c.connected and c.current_zone_id == target_zone:
                seed_char = c
                break
        # Fallback to first connected char
        if not seed_char and sorted_ids:
            seed_char = self.chars[sorted_ids[0]]

        if seed_char and seed_char.connected:
            # Defensive: never seed in a city — the server spawns no monsters
            # there, so a city seed always fails and wastes the 25s window.
            seed_zi = self.world.zones.get(seed_char.current_zone_id) if self.world.zones else None
            if seed_zi and seed_zi.zone_type == 'city':
                self.analytics.log(f'  ⚠️ {seed_char.name} still in city {seed_char.current_zone_id} — skipping seed (no monsters spawn in cities)')
            else:
                self.analytics.log(f'🌱 Seeding monsters on {seed_char.name} (zone {seed_char.current_zone_id})...')
                await seed_char.start_autofarm()
                await asyncio.sleep(0.5)
                if seed_char.is_autofarming:
                    # Await monster_spawned event — no polling
                    seed_char.monster_spawned.clear()
                    try:
                        await asyncio.wait_for(seed_char.monster_spawned.wait(), timeout=25)
                        self.analytics.log(f'  ✅ {seed_char.name}: {len(seed_char.monsters)} monsters appeared')
                    except asyncio.TimeoutError:
                        self.analytics.log(f'  ⚠️ {seed_char.name}: no monsters after 25s')
                    await seed_char.stop_autofarm()
                    seed_char.is_autofarming = False
                    self.analytics.log(f'  📊 Seeded {len(seed_char.monsters)} monsters on {seed_char.name}')
                else:
                    self.analytics.log(f'  ⚠️ Auto-farm rejected on {seed_char.name}')

        self._last_seed_time = time.time()

        # 5. Brief wait for zone spawns to propagate
        await asyncio.sleep(2)

        # 6. Re-form party (chars must be in same zone)
        await self._ensure_party()
        await asyncio.sleep(2)

        # 7. Re-enable combat on all chars
        for cid, agent in self.chars.items():
            if agent.connected and not agent.combat_enabled:
                await agent.enable_combat()
        self.analytics.log('✅ Coordinated reseed complete')

    
    def _pick_common_hunting_zone(self, sorted_ids, min_level):
        '''Choose a hunting ground reachable by the most connected chars that
        covers the party's lowest level (so every member can fight there).
        Scores:
          +100 per connected char that can BFS-reach the zone
          +40  per char that can reach it in a single hop (fast travel)
          -200 if it's a city (never selected)
        Returns a zone id, or None when nothing qualifies.'''
        if min_level is None:
            return None
        candidates = []
        for zid, zi in self.world.zones.items():
            if zi.zone_type != 'hunting_ground':
                continue
            if not (zi.level_min <= min_level <= zi.level_max):
                continue
            candidates.append((zid, zi))
        if not candidates:
            return None
        best = None
        best_score = -1
        for zid, zi in candidates:
            reach = 0
            direct = 0
            for cid in sorted_ids:
                agent = self.chars[cid]
                if not agent.connected or not agent.current_zone_id:
                    continue
                path = self.world.find_path(agent.current_zone_id, zid)
                if path:
                    reach += 1
                    if len(path) == 2:  # [from, to] == single hop
                        direct += 1
            score = reach * 100 + direct * 40
            if best is None or score > best_score:
                best = zid
                best_score = score
        return best

    async def _travel_agent_to(self, agent, target_zone):
        '''Travel a single agent to target_zone hop-by-hop (the server only
        accepts single-hop paths). Force-exits combat first (pitfall #45).
        Returns True if the agent is in the target zone when done.'''
        if agent.current_zone_id == target_zone:
            return True
        path = None
        if self.world._loaded and self.world.adjacency:
            path = self.world.find_path(agent.current_zone_id, target_zone)
        if not (path and len(path) >= 2):
            self.analytics.log(f'  ⚠️ {agent.name}: no path found from {agent.current_zone_id} to {target_zone}')
            return False
        self.analytics.log(f'  🗺️ {agent.name}: {agent.current_zone_id} → {target_zone} ({len(path)-1} hops)')
        if agent.is_in_combat or agent._target_attack_initiated:
            await agent.ws_send('combat:stop_attack', {})
            agent._target_attack_initiated = False
            agent.is_in_combat = False
            await asyncio.sleep(2.0)
        agent.combat_state = 'TRAVELING'
        for hop_idx in range(1, len(path)):
            hop = path[hop_idx]
            agent.travel_complete.clear()
            await agent.ws_send('start_travel', {'path': [hop]})
            try:
                await asyncio.wait_for(agent.travel_complete.wait(), timeout=40)
            except asyncio.TimeoutError:
                self.analytics.log(f'  ⚠️ {agent.name} travel timeout at hop {hop} (stuck at {agent.current_zone_id})')
                break
        if agent.current_zone_id != target_zone:
            self.analytics.log(f'  ⚠️ {agent.name} arrived at {agent.current_zone_id} (target {target_zone})')
            # Fallback: the agent's own finder, with the hunting zone pinned
            # back to the party zone afterwards so it doesn't scatter.
            agent.travel_complete.clear()
            await agent._find_and_travel_hunting_zone()
            try:
                await asyncio.wait_for(agent.travel_complete.wait(), timeout=40)
            except asyncio.TimeoutError:
                pass
            agent._hunting_zone_id = target_zone
        return agent.current_zone_id == target_zone

    async def _travel_stragglers(self):
        '''Round up any connected char that drifted out of the party zone
        (reconnects, respawn-to-town, individual zone-finder scatter). Runs on
        the main tick so the party stays together — without it a char that
        reconnects after the reseed's travel pass sits in the city forever.'''
        tz = getattr(self, '_party_zone_id', None)
        if not tz or not self.chars:
            return
        now = time.time()
        if now - getattr(self, '_last_straggler_check', 0) < 15:
            return
        self._last_straggler_check = now
        sorted_ids = sorted(self.chars.keys())
        for cid in sorted_ids:
            agent = self.chars[cid]
            if not agent.connected or agent.is_dead:
                continue
            if agent.combat_state == 'TRAVELING':
                continue  # already moving
            if agent.current_zone_id == tz:
                agent._hunting_zone_id = tz  # keep pinned
                continue
            # Don't drag a char out of a fight mid-engagement.
            if agent.is_in_combat or agent._target_attack_initiated:
                continue
            self.analytics.log(f'🚚 {agent.name}: pulling back to party zone {tz} (at {agent.current_zone_id})')
            agent._hunting_zone_id = tz
            await self._travel_agent_to(agent, tz)

    async def _ensure_party(self):
        '''Check party status and reform if needed.'''
        # Find the party leader (first character)
        if not self.chars:
            return
        sorted_ids = sorted(self.chars.keys())
        leader_id = sorted_ids[0]
        leader = self.chars[leader_id]

        # If leader is disconnected, skip
        if not leader.connected:
            return

        # If leader is in a party, assume it's fine
        if leader.is_in_party:
            return

        # Try to form party: leader invites others
        for cid in sorted_ids[1:]:
            member = self.chars[cid]
            if not member.connected:
                continue
            # Create invite_received event for this member if needed
            if not hasattr(member, '_invite_received_event'):
                member._invite_received_event = asyncio.Event()
            member._invite_received_event.clear()
            member._pending_invite_from = None
            member.party_joined.clear()
            
            # Send invite
            await leader.party_invite(member.name)
            
            # Wait for invite_received event with timeout
            try:
                await asyncio.wait_for(member._invite_received_event.wait(), timeout=3)
            except asyncio.TimeoutError:
                self.analytics.log(f'  ⚠️ {member.name} invite timed out')
                continue
            
            # Accept if invite was received
            if getattr(member, '_pending_invite_from', None) == leader_id:
                await member.party_accept(leader_id)
                # Wait for party state to confirm join (poll is_in_party)
                self.analytics.log(f'  Waiting for {member.name} to join party...')
                joined = False
                for attempt in range(10):  # 5s total
                    await asyncio.sleep(0.5)
                    if member.is_in_party or leader.is_in_party:
                        joined = True
                        break
                if joined:
                    self.analytics.log(f'  ✓ {member.name} joined party')
                else:
                    # Accept may have failed (expired) — retry once
                    self.analytics.log(f'  ⚠️ {member.name} party join timed out, retrying...')
                    member._invite_received_event.clear()
                    member._pending_invite_from = None
                    member.party_joined.clear()
                    await leader.party_invite(member.name)
                    try:
                        await asyncio.wait_for(member._invite_received_event.wait(), timeout=3)
                    except asyncio.TimeoutError:
                        continue
                    if getattr(member, '_pending_invite_from', None) == leader_id:
                        await member.party_accept(leader_id)
                        for attempt in range(10):
                            await asyncio.sleep(0.5)
                            if member.is_in_party or leader.is_in_party:
                                self.analytics.log(f'  ✓ {member.name} joined party (retry)')
                                break

    async def _progression_check(self):
        '''Check gear, zones, and suggest improvements.
        Only recommends directly-reachable zones (server only supports single-hop travel).'''
        for cid, agent in self.chars.items():
            if not agent.connected:
                continue
            # Refresh stats
            stats = agent.fetch_stats()
            if stats:
                # Check if zone needs updating
                if agent.current_zone_id and agent.level:
                    # Get zones directly connected to current zone
                    nearby = self.world.get_nearby_zones(agent.current_zone_id, max_hops=1)
                    if not nearby:
                        continue
                    connected_ids = set(nearby.keys())
                    # Filter best zones to only directly reachable ones
                    best_all = self.world.find_best_zones(agent.level, 'hunting_ground', 10)
                    reachable_best = [z for z in best_all if z['id'] in connected_ids]
                    if reachable_best and reachable_best[0]['id'] != agent.current_zone_id:
                        self.analytics.log(f'[{agent.name}] Better zone available: {reachable_best[0]["id"]} (currently {agent.current_zone_id})')

    async def stop(self):
        '''Graceful shutdown.'''
        self.analytics.log('🛑 AgentCoordinator shutting down...')
        self._running = False
        if self._main_loop_task and not self._main_loop_task.done():
            self._main_loop_task.cancel()
            self._main_loop_task = None
        for cid, agent in self.chars.items():
            await agent.disconnect()
        self.analytics.log('✅ AgentCoordinator stopped')

    
    async def cmd_zones(self):
        '''Show zone recommendations for all chars.'''
        for cid, agent in self.chars.items():
            if agent.level:
                best = self.world.find_best_zones(agent.level, 'hunting_ground', 3)
                if best:
                    zones = ', '.join('{} ({})'.format(z['id'], z['name']) for z in best)
                    self.analytics.log(f'[{agent.name}] Lv{agent.level} best zones: {zones}')

    async def cmd_gear(self, char_id=None):
        '''Show gear status.'''
        targets = [char_id] if char_id else list(self.chars.keys())
        for cid in targets:
            agent = self.chars.get(cid)
            if not agent:
                continue
            inv = agent.fetch_inventory()
            if inv:
                equipped = inv.get('equippedItems', [])
                self.analytics.log(f'[{agent.name}] Equipped:')
                for item in equipped:
                    slot = item.get('slot', '?')
                    name = item.get('itemName', '?')
                    self.analytics.log(f'  {slot}: {name}')

    async def cmd_report(self):
        '''Show full analytics report.'''
        report = self.analytics.report()
        if report:
            self.analytics.log(report)

    async def cmd_inventory(self, char_id=None):
        '''Show inventory for a character.'''
        if char_id not in self.chars:
            return
        agent = self.chars[char_id]
        inv = agent.fetch_inventory()
        if inv:
            items = inv.get('items', inv.get('bagItems', []))
            self.analytics.log(f'[{agent.name}] Inventory ({len(items)} items):')
            for item in items[:20]:
                name = item.get('itemName', '?')
                qty = item.get('quantity', 1)
                self.analytics.log(f'  {name} x{qty}')

    async def cmd_rest_config(self, hp_pct=None, mp_pct=None):
        '''Configure auto-rest for all characters.'''
        for cid, agent in self.chars.items():
            if hp_pct is not None:
                agent.rest_hp_threshold = hp_pct / 100.0
            if mp_pct is not None:
                agent.rest_mp_threshold = mp_pct / 100.0
        self.analytics.log(f'Rest thresholds: HP<={hp_pct}% MP<={mp_pct}%')

    async def cmd_buy(self, char_id=None, item_id=None, npc_id=8, quantity=1):
        '''Buy item from shop.'''
        if char_id in self.chars:
            result = self.chars[char_id].buy_item(npc_id, item_id, quantity)
            self.analytics.log(f'Buy result: {result}')

    async def cmd_quests(self, char_id=None):
        '''Show available and active quests for a character.'''
        if char_id not in self.chars:
            return
        agent = self.chars[char_id]
        active = agent.fetch_active_quests()
        if active:
            self.analytics.log(f'[{agent.name}] Active quests:')
            for q in active:
                self.analytics.log('  {} ({})'.format(q.get('name', '?'), q.get('status', '?')))
        available = agent.fetch_available_quests()
        if available:
            self.analytics.log(f'[{agent.name}] Available quests:')
            for q in available[:5]:
                self.analytics.log('  {}'.format(q.get('name', '?')))

    async def cmd_accept_quest(self, char_id=None, quest_id=None):
        if char_id in self.chars and quest_id:
            result = self.chars[char_id].accept_quest(quest_id)
            self.analytics.log(f'Accept quest {quest_id}: {result}')

    async def cmd_claim_quest(self, char_id=None, quest_id=None):
        if char_id in self.chars and quest_id:
            result = self.chars[char_id].claim_quest(quest_id)
            self.analytics.log(f'Claim quest {quest_id}: {result}')

    async def cmd_sell_junk(self, char_id=None):
        '''Auto-sell vendor trash.'''
        targets = [char_id] if char_id else list(self.chars.keys())
        for cid in targets:
            agent = self.chars.get(cid)
            if not agent:
                continue
            agent.fetch_inventory()
            sold = agent.auto_sell_junk(8)
            if sold:
                self.analytics.log(f'[{agent.name}] Sold {sold} junk items')

    async def cmd_warehouse(self, char_id=None):
        '''Show warehouse status.'''
        if char_id in self.chars:
            gold = self.chars[char_id].warehouse_gold()
            self.analytics.log(f'[{self.chars[char_id].name}] Warehouse gold: {gold:,}')

    async def cmd_warehouse_deposit_gold(self, char_id=None, amount=None):
        if char_id in self.chars and amount:
            result = self.chars[char_id].warehouse_deposit_gold(amount)
            self.analytics.log(f'Deposit {amount} gold: {result}')

    async def cmd_warehouse_withdraw_gold(self, char_id=None, amount=None):
        if char_id in self.chars and amount:
            result = self.chars[char_id].warehouse_withdraw_gold(amount)
            self.analytics.log(f'Withdraw {amount} gold: {result}')

    async def cmd_transfer_gold(self, from_id=None, to_id=None, amount=None):
        '''Transfer gold from one char to another via warehouse (both need to be in a city).'''
        if from_id in self.chars and to_id in self.chars and amount:
            # Withdraw from source, deposit to target via warehouse
            result = self.chars[from_id].warehouse_withdraw_gold(amount)
            self.analytics.log(f'Transfer {amount} gold from {self.chars[from_id].name}: {result}')
            # Note: target needs to be in same city to withdraw

    async def cmd_craft(self, char_id=None, recipe_id=None, quantity=1):
        if char_id in self.chars and recipe_id:
            result = self.chars[char_id].craft_recipe(recipe_id, quantity)
            self.analytics.log(f'Craft {recipe_id} x{quantity}: {result}')

    async def cmd_combat(self, action=None, char_id=None):
        '''Enable/disable combat AI for specific character or all.'''
        if action == 'enable':
            targets = [char_id] if char_id else list(self.chars.keys())
            for cid in targets:
                if cid in self.chars:
                    await self.chars[cid].enable_combat()
            if not char_id:
                self.combat_enabled = True
        elif action == 'disable':
            targets = [char_id] if char_id else list(self.chars.keys())
            for cid in targets:
                if cid in self.chars:
                    await self.chars[cid].disable_combat()
            if not char_id:
                self.combat_enabled = False

    async def cmd_combat_status(self):
        '''Show combat AI status for all characters.'''
        for cid, agent in self.chars.items():
            state = agent.combat_state if agent.combat_enabled else 'DISABLED'
            self.analytics.log(f'[{agent.name}] Combat: {state} | HP:{agent.hp}/{agent.max_hp} MP:{agent.mp}/{agent.max_mp}')



async def main():
    '''Main entry point — start AgentCoordinator and handle CLI input.'''
    coord = AgentCoordinator()
    try:
        await coord.start()
        # CLI input loop
        while coord._running:
            cmd = await _async_input()
            if not cmd:
                continue
            parts = cmd.strip().split()
            if not parts:
                continue
            command = parts[0]
            args = parts[1:]

            if command == 'combat' and len(args) >= 1:
                action = args[0]
                char_id = int(args[1]) if len(args) > 1 else None
                await coord.cmd_combat(action, char_id)
            elif command == 'status':
                await coord.cmd_combat_status()
            elif command == 'report':
                await coord.cmd_report()
            elif command == 'quit' or command == 'exit':
                break
            elif command == 'help':
                print('Commands: combat enable/disable [char_id], status, report, quit')
    finally:
        await coord.stop()


async def _async_input():
    '''Read line from stdin in a thread pool (non-blocking in async context).'''
    import sys
    loop = asyncio.get_event_loop()
    line = await loop.run_in_executor(None, sys.stdin.readline)
    return line.strip()

if __name__ == '__main__':
    asyncio.run(main())
