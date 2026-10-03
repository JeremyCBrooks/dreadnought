"""Tactical (dungeon exploration) state."""

from __future__ import annotations

import hashlib
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from data.colors import DARK_GRAY, EQUIP_MSG, GRAY, PROMPT
from engine.game_state import State
from engine.keys import action_keys, cancel_keys, confirm_keys, is_action
from engine.keys import move_keys as _move_keys

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.actions import Action
    from game.entity import Entity
    from world.galaxy import Location

# Minimum map size so dungeons stay playable when console is small
MIN_MAP_W = 60
MIN_MAP_H = 42
STATS_PANEL_W = 20
LOG_PANEL_H = 8
MAX_INVENTORY_DISPLAY = 8


def _layout(engine: Engine) -> SimpleNamespace:
    """Compute layout from engine dimensions so UI adapts to CONSOLE_WIDTH/HEIGHT."""
    cw = engine.CONSOLE_WIDTH
    ch = engine.CONSOLE_HEIGHT
    # Stats panel: at least STATS_PANEL_W, up to 1/4 of width (capped at 40) so inventory/underfoot aren't cut off
    stats_w = min(40, max(STATS_PANEL_W, cw // 4))
    viewport_w = max(MIN_MAP_W, cw - stats_w)
    viewport_h = max(MIN_MAP_H, ch - LOG_PANEL_H)
    stats_w = cw - viewport_w  # actual width after viewport minimums
    return SimpleNamespace(
        viewport_w=viewport_w,
        viewport_h=viewport_h,
        stats_x=viewport_w,
        stats_w=stats_w,
        log_y=viewport_h,
        log_h=ch - viewport_h,
        map_w=max(viewport_w, MIN_MAP_W),
        map_h=max(viewport_h, MIN_MAP_H),
    )


Color = tuple[int, int, int]


def _area_key(location: Location | None, depth: int) -> tuple[str, int]:
    """Stable key for area cache: (location_name, depth)."""
    loc_name = location.name if location else "the dungeon"
    return (loc_name, depth)


def _area_seed(location_name: str, depth: int) -> int:
    """Deterministic seed for dungeon layout so the same area is always the same layout."""
    raw = hashlib.md5(f"{location_name}_{depth}".encode(), usedforsecurity=False).hexdigest()[:8]
    return int(raw, 16)


DRIFT_INTERVAL = 2.0  # seconds between automatic drift ticks
DEATH_FADE_DURATION = 1.0  # seconds to fade out tactical on player death


class TacticalState(State):
    def __init__(self, location: Location | None = None, depth: int = 0, explore_ship: bool = False) -> None:
        self.location = location
        self.depth = depth
        self.explore_ship = explore_ship
        self.exit_pos: tuple[int, int] | None = None
        self._look_cursor: tuple[int, int] | None = None
        self._ranged_cursor: tuple[int, int] | None = None
        self._interact_pending: bool = False
        self._scan_pending: list | None = None  # list of scanner entities when choosing
        self._visible_enemies: list = []
        self._enemy_cycle_index: int = 0
        self._ground_lines: list[tuple[str, Color]] = []
        self._layout: SimpleNamespace | None = None
        self._drift_timer: float = 0.0
        # Death fade-out state
        self._death_cause: str | None = None
        self._death_fade_start: float = 0.0

    def _max_enemies(self) -> int:
        return min(max(1, 1 + self.depth), 3)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_enter(self, engine: Engine) -> None:
        if self.explore_ship:
            self._enter_ship(engine)
            return

        from game.player_state import new_player
        from game.suit import EVA_SUIT
        from world.dungeon_gen import generate_dungeon, respawn_creatures

        loc_name = self.location.name if self.location else "the dungeon"
        key = _area_key(self.location, self.depth)
        seed = _area_seed(loc_name, self.depth)
        max_enemies = self._max_enemies()

        # Environment and suit: from location data (galaxy sets vacuum for
        # derelicts/asteroids; starbases are pressurised unless breached).
        env = getattr(self.location, "environment", None)
        engine.environment = dict(env) if env else {}
        engine.suit = getattr(engine, "suit", None) or EVA_SUIT.copy()
        engine.suit.refill_pools()

        engine.active_effects.clear()
        self._layout = _layout(engine)
        layout = self._layout
        loc_type = self.location.loc_type if self.location else "derelict"

        cached = engine.area_cache.get(key)
        wreck = getattr(self.location, "wreck", None)
        if wreck is not None:
            # A pirate wreck is one particular ship, rebuilt as the player left
            # it. It keeps its own size, and nothing lives aboard to respawn.
            if cached is None:
                from game.wreck import build_wreck_map

                game_map, rooms, exit_pos = build_wreck_map(wreck)
                cached = {"game_map": game_map, "rooms": rooms, "exit_pos": exit_pos, "seed": wreck.ship_seed}
                engine.area_cache[key] = cached
            game_map = cached["game_map"]
            rooms = cached["rooms"]
            self.exit_pos = cached["exit_pos"]
        elif cached and cached["game_map"].width == layout.map_w and cached["game_map"].height == layout.map_h:
            game_map = cached["game_map"]
            rooms = cached["rooms"]
            self.exit_pos = cached["exit_pos"]
            respawn_creatures(game_map, rooms, max_enemies=max_enemies, seed=None, loc_type=loc_type, depth=self.depth)
        else:
            game_map, rooms, exit_pos = generate_dungeon(
                width=layout.map_w,
                height=layout.map_h,
                max_enemies=max_enemies,
                max_items=1,
                seed=seed,
                loc_type=loc_type,
                has_nav_unit=getattr(self.location, "has_nav_unit", False),
                depth=self.depth,
            )
            self.exit_pos = exit_pos
            engine.area_cache[key] = {
                "game_map": game_map,
                "rooms": rooms,
                "exit_pos": exit_pos,
                "seed": seed,
            }

        if not rooms:
            engine.game_map = game_map
            engine.player = None
            if hasattr(engine, "galaxy") and engine.galaxy:
                engine.pop_state()
            return

        px, py = rooms[0].center
        player = new_player(px, py)
        self._restore_player_from_saved(player, engine)
        game_map.entities.append(player)

        # Seed for space starfield - matches strategic viewport when available
        system_name = getattr(self.location, "system_name", "") if self.location else ""
        if system_name:
            from game.helpers import stable_seed

            game_map.space_seed = stable_seed(system_name)

        engine.game_map = game_map
        engine.player = player

        # Sync environment with map: hull breaches/airlocks imply vacuum
        if game_map.hull_breaches or game_map.airlocks:
            engine.environment.setdefault("vacuum", 1)

        # Transfer mission loadout to player inventory on entry
        if hasattr(engine, "mission_loadout"):
            for item in engine.mission_loadout:
                player.inventory.append(item)
            engine.mission_loadout.clear()

        # Set carry capacity
        from game.entity import PLAYER_MAX_INVENTORY

        player.max_inventory = PLAYER_MAX_INVENTORY

        # Auto-equip: first weapon and first tool into loadout if not already set
        if not player.loadout:
            from game.loadout import Loadout, is_equippable

            player.loadout = Loadout()
            first_weapon = None
            first_tool = None
            for item in player.inventory:
                if not is_equippable(item):
                    continue
                if item.item.get("type") == "weapon" and first_weapon is None:
                    first_weapon = item
                elif item.item.get("type") == "scanner" and first_tool is None:
                    first_tool = item
            if first_weapon:
                player.loadout.equip(first_weapon)
            if first_tool:
                player.loadout.equip(first_tool)

        # Apply melee weapon power bonus
        from game.loadout import recalc_melee_power

        recalc_melee_power(player)

        game_map.update_fov(player.x, player.y)

        engine.message_log.add_message(f"You enter {loc_name}.", (200, 200, 255))
        self._update_ground_underfoot(engine)

    def on_exit(self, engine: Engine) -> None:
        from game.interdiction import (
            current_interdiction,
            detach_pirates,
            resolve_if_cleared,
            restore_original_ship_map,
        )
        from game.wreck import leave_wreck

        if engine.game_map and engine.player:
            p = engine.player

            if getattr(self, "explore_ship", False):
                # Detach surviving pirates from the map so they persist on the
                # Interdiction object across ship-explore sessions.
                detach_pirates(engine)
                # Collect floor items back into ship cargo.
                if engine.ship is not None:
                    engine.ship.collect_floor_items(engine.game_map)
                # What the player carries back to the bridge is salvage like any
                # other: a boarded pirate ship is a mission that came to them.
                self._bring_salvage_home(engine, p)
                if p in engine.game_map.entities:
                    engine.game_map.entities.remove(p)
                # Resolved interdiction: now safe to swap composite map back
                # to the original player ship (player has left ship interior).
                # Re-check first: the turn that brought the player here never
                # reached the end-of-turn resolution check.
                resolve_if_cleared(engine)
                interdiction = current_interdiction(engine)
                if interdiction is not None and interdiction.resolved:
                    # A craft with no crew left stays behind as a wreck; the
                    # composite is the only record of what was done aboard it.
                    leave_wreck(engine, interdiction)
                    restore_original_ship_map(interdiction, engine.ship)
            else:
                self._bring_salvage_home(engine, p)
                wreck = getattr(self.location, "wreck", None)
                if wreck is not None:
                    wreck.refresh(engine.game_map)
                key = _area_key(self.location, self.depth)
                if engine.player in engine.game_map.entities:
                    engine.game_map.entities.remove(engine.player)
                if key in engine.area_cache:
                    engine.area_cache[key]["game_map"] = engine.game_map
                    engine.area_cache[key]["exit_pos"] = self.exit_pos
        engine.game_map = None
        engine.player = None
        engine.scan_results = None
        engine.scan_glow = None

    @staticmethod
    def _bring_salvage_home(engine: Engine, player: Entity) -> None:
        """Snapshot *player* for the next outing and hand their salvage to the ship."""
        from game.player_state import snapshot_player
        from game.salvage import unload_mission_salvage

        engine.saved_player = snapshot_player(player)
        if engine.ship is not None:
            unload_mission_salvage(engine, engine.saved_player["inventory"])

    # ------------------------------------------------------------------
    # explore_ship helper
    # ------------------------------------------------------------------

    def _restore_player_from_saved(self, player: Entity, engine: Engine) -> None:
        """Apply saved player stats and inventory to a freshly created player entity."""
        from game.player_state import apply_snapshot

        apply_snapshot(player, engine.saved_player)

    def _enter_ship(self, engine: Engine) -> None:
        """Set up the engine to explore the player's own ship interior."""
        from game.entity import PLAYER_MAX_INVENTORY
        from game.interdiction import prepare_ship_entry
        from game.loadout import Loadout
        from game.player_state import new_player
        from game.suit import EVA_SUIT

        engine.active_effects.clear()
        self._layout = _layout(engine)

        # Pirate interdiction: may swap engine.ship.game_map to a composite
        # containing the pirate ship + airtight corridor. Read game_map AFTER.
        prepare_ship_entry(engine)

        game_map = engine.ship.game_map
        self.exit_pos = engine.ship.exit_pos

        # The interior is pressurized, but vacuum is spatial: it only bites
        # on tiles an opened airlock has actually vented.
        engine.environment = {"vacuum": 1} if game_map.airlocks else {}
        engine.suit = engine.suit or EVA_SUIT.copy()

        engine.ship.materialize_cargo(game_map, engine.ship.rooms)

        # Place / restore player at exit (docking hatch)
        px, py = self.exit_pos
        player = new_player(px, py)
        self._restore_player_from_saved(player, engine)
        if player.loadout is None:
            player.loadout = Loadout()
        player.max_inventory = PLAYER_MAX_INVENTORY

        game_map.entities.append(player)
        engine.game_map = game_map
        engine.player = player
        game_map.update_fov(player.x, player.y)
        engine.message_log.add_message("You explore your ship.", (200, 200, 255))
        self._update_ground_underfoot(engine)

    # ------------------------------------------------------------------
    # Saving mid-mission
    # ------------------------------------------------------------------

    def flush_for_save(self, engine: Engine) -> list[Entity]:
        """Snapshot live state into engine for a clean disconnect-style save.

        Called from ``engine_to_dict`` when this state is on the stack but
        the player is mid-mission (didn't go through ``on_exit``). Refreshes
        ``engine.saved_player`` so HP/inventory changes since the last clean
        exit aren't lost on reload - on any mission, or a disconnect would
        hand back the HP the player walked in with. Aboard the ship it also
        returns the floor items that ``on_exit`` would have swept into cargo
        so the save can include them.

        Must NOT mutate the live map: a reconnect within the idle TTL reuses
        this in-memory engine, so pirates and floor items have to stay put.
        """
        if engine.game_map is None or engine.player is None:
            return []
        from game.player_state import snapshot_player

        p = engine.player
        engine.saved_player = snapshot_player(p)
        if not getattr(self, "explore_ship", False) or engine.ship is None:
            return []
        return engine.ship.floor_items(engine.game_map)

    # ------------------------------------------------------------------
    # Player death
    # ------------------------------------------------------------------

    def _handle_player_death(self, engine: Engine, cause: str) -> None:
        if self._death_cause is not None:
            return  # already dying
        self._death_cause = cause
        self._death_fade_start = time.time()

    @property
    def needs_animation(self) -> bool:
        return self._death_cause is not None

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def ev_key(self, engine: Engine, event: Any) -> bool:
        if self._death_cause is not None:
            return True  # block all input during death fade

        import tcod.event

        key = event.sym

        if self._scan_pending is not None:
            return self._handle_scan_input(engine, key)

        if self._interact_pending:
            return self._handle_interact_input(engine, key)

        if self._ranged_cursor is not None:
            return self._handle_ranged_input(engine, key)

        if self._look_cursor is not None:
            return self._handle_look_input(engine, key)

        if key in cancel_keys():
            return True  # consumed - exit only via docking hatch

        if is_action("quit", key) and event.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT):
            from ui.confirm_quit_state import ConfirmQuitState

            engine.push_state(ConfirmQuitState(abandon=True))
            return True

        if self._handle_log_scroll(engine, key):
            return True

        if is_action("inventory", key):
            from ui.inventory_state import InventoryState

            engine.push_state(InventoryState())
            return True

        if is_action("look", key):
            self._enter_look(engine)
            return True

        # While drifting, block turn-consuming inputs - only UI actions above are allowed
        if engine.player.drifting:
            return True

        if is_action("fire", key):
            self._enter_ranged(engine)
            return True

        if is_action("interact", key):
            interact_dirs = self._adjacent_interact_dirs(engine)
            if len(interact_dirs) == 0:
                engine.message_log.add_message("Nothing to interact with here.", DARK_GRAY)
                consumed = 0
            elif len(interact_dirs) == 1:
                dx, dy, kind = interact_dirs[0]
                consumed = self._perform_interact(engine, dx, dy, kind)
            else:
                self._interact_pending = True
                engine.message_log.add_message("Which direction? (arrow/vi key)", PROMPT)
                return True
            moved = False
        elif is_action("scan", key):
            loadout = getattr(engine.player, "loadout", None)
            scanners = loadout.get_all_scanners() if loadout else []
            if len(scanners) == 0:
                engine.message_log.add_message("You need a scanner in your loadout.", GRAY)
                consumed = 0
            elif len(scanners) == 1:
                from game.actions import ScanAction

                consumed = ScanAction(scanner=scanners[0]).perform(engine, engine.player)
            else:
                labels = " ".join(f"({i + 1}) {s.name}" for i, s in enumerate(scanners))
                engine.message_log.add_message(f"Which scanner? {labels}", PROMPT)
                self._scan_pending = scanners
                return True
            moved = False
        else:
            action = self._get_action(key)
            if action is None:
                return False
            old_x, old_y = engine.player.x, engine.player.y
            consumed = action.perform(engine, engine.player)
            moved = (engine.player.x, engine.player.y) != (old_x, old_y)

        self._resolve_player_action(engine, consumed, moved=moved)
        return True

    def _resolve_player_action(self, engine: Engine, consumed: int, *, moved: bool = False) -> None:
        """Run everything that follows a player action that took *consumed* ticks.

        Every input mode ends here, so they all agree on the order: leave by
        the hatch, die, let the world take its turns, refresh what the player sees.
        """
        if not consumed:
            return

        # Only walking onto the hatch leaves: the player spawns on it, so
        # scanning or waiting there must not end the mission.
        if moved and self.exit_pos and (engine.player.x, engine.player.y) == self.exit_pos:
            msg = "You return to the bridge." if self.explore_ship else "You return to your ship."
            engine.message_log.add_message(msg, EQUIP_MSG)
            engine.pop_state()
            return

        if engine.player.fighter.hp <= 0:
            self._handle_player_death(engine, "Killed in action.")
            return

        position = (engine.player.x, engine.player.y)
        for _ in range(consumed):
            self._after_player_turn(engine)
            if engine.current_state is not self:
                return

        self._update_fov_with_scan(engine)
        if moved or (engine.player.x, engine.player.y) != position:
            self._update_ground_underfoot(engine)

    def _after_player_turn(self, engine: Engine) -> None:
        """Advance the world one tick; start the death fade if it killed the player."""
        from game.interdiction import resolve_if_cleared
        from game.turn import advance_turn

        cause = advance_turn(engine)
        if cause is not None:
            self._handle_player_death(engine, cause)
            return

        # Interdiction resolution: if we're aboard the player ship and every
        # pirate is dead, end the interdiction.
        if getattr(self, "explore_ship", False):
            resolve_if_cleared(engine)

    # ------------------------------------------------------------------
    # Look mode
    # ------------------------------------------------------------------

    def _enter_look(self, engine: Engine) -> None:
        self._look_cursor = (engine.player.x, engine.player.y)
        self._update_ground_look(engine)

    def _handle_look_input(self, engine: Engine, key: Any) -> bool:

        if key in cancel_keys() | confirm_keys() | action_keys()["look"][0]:
            self._look_cursor = None
            self._update_ground_underfoot(engine)
            return True

        move = _move_keys().get(key)
        if move:
            cx, cy = self._look_cursor
            nx, ny = cx + move[0], cy + move[1]
            if engine.game_map.in_bounds(nx, ny):
                self._look_cursor = (nx, ny)
                self._update_ground_look(engine)
            return True

        return True

    def _update_ground_look(self, engine: Engine) -> None:
        cx, cy = self._look_cursor
        self._ground_lines = engine.game_map.describe_at(cx, cy, visible_only=True)

    # ------------------------------------------------------------------
    # Ranged targeting mode
    # ------------------------------------------------------------------

    def _enter_ranged(self, engine: Engine) -> None:
        from game.helpers import get_equipped_ranged_weapon, has_ranged_weapon

        weapon = get_equipped_ranged_weapon(engine.player)
        if not weapon:
            if has_ranged_weapon(engine.player):
                engine.message_log.add_message("Out of ammo!", (255, 100, 100))
            else:
                engine.message_log.add_message("No ranged weapon equipped.", (255, 100, 100))
            return
        # Find visible enemies, sorted by distance (closest first)
        px, py = engine.player.x, engine.player.y
        self._visible_enemies = sorted(
            [
                e
                for e in engine.game_map.entities
                if e is not engine.player and e.fighter and e.fighter.hp > 0 and engine.game_map.visible[e.x, e.y]
            ],
            key=lambda e: max(abs(e.x - px), abs(e.y - py)),
        )
        if self._visible_enemies:
            self._enemy_cycle_index = 0
            e = self._visible_enemies[0]
            self._ranged_cursor = (e.x, e.y)
        else:
            engine.message_log.add_message("No visible targets.", (255, 100, 100))

    def _handle_ranged_input(self, engine: Engine, key: Any) -> bool:
        import tcod.event

        if key in cancel_keys():
            self._ranged_cursor = None
            self._update_ground_underfoot(engine)
            return True

        # Up/Down cycle through visible enemies
        if key in (
            tcod.event.KeySym.UP,
            tcod.event.KeySym.DOWN,
            tcod.event.KeySym.K,
            tcod.event.KeySym.J,
            tcod.event.KeySym.KP_8,
            tcod.event.KeySym.KP_2,
        ):
            if self._visible_enemies:
                if key in (tcod.event.KeySym.DOWN, tcod.event.KeySym.J, tcod.event.KeySym.KP_2):
                    self._enemy_cycle_index = (self._enemy_cycle_index + 1) % len(self._visible_enemies)
                else:
                    self._enemy_cycle_index = (self._enemy_cycle_index - 1) % len(self._visible_enemies)
                e = self._visible_enemies[self._enemy_cycle_index]
                self._ranged_cursor = (e.x, e.y)
            return True

        if key in confirm_keys():
            # Re-check ammo before firing (weapon may have been depleted)
            from game.helpers import get_equipped_ranged_weapon

            weapon = get_equipped_ranged_weapon(engine.player)
            if not weapon:
                from game.helpers import has_ranged_weapon

                if has_ranged_weapon(engine.player):
                    engine.message_log.add_message("Out of ammo!", (255, 100, 100))
                else:
                    engine.message_log.add_message("No ranged weapon equipped.", (255, 100, 100))
                self._ranged_cursor = None
                self._update_ground_underfoot(engine)
                return True
            # Fire at targeted enemy
            cx, cy = self._ranged_cursor
            target = engine.game_map.get_blocking_entity(cx, cy)
            if target and target.fighter and target is not engine.player:
                from game.actions import RangedAction

                consumed = RangedAction(target).perform(engine, engine.player)
                self._ranged_cursor = None
                self._resolve_player_action(engine, consumed)
            else:
                engine.message_log.add_message("No target at cursor.", GRAY)
            return True

        return True

    # ------------------------------------------------------------------
    @staticmethod
    def _perform_interact(engine: Engine, dx: int, dy: int, kind: str) -> int:
        """Dispatch an interact action based on kind."""
        from game.actions import (
            InteractAction,
            TakeReactorCoreAction,
            ToggleDoorAction,
            ToggleSwitchAction,
        )

        _INTERACT_ACTIONS: dict[str, type] = {
            "door": ToggleDoorAction,
            "switch": ToggleSwitchAction,
            "reactor": TakeReactorCoreAction,
        }
        action_cls = _INTERACT_ACTIONS.get(kind, InteractAction)
        return action_cls(dx, dy).perform(engine, engine.player)

    # ------------------------------------------------------------------
    # Interact direction prompt
    # ------------------------------------------------------------------

    @staticmethod
    def _adjacent_interact_dirs(engine: Engine) -> list[tuple[int, int, str]]:
        """Return list of (dx, dy, kind) for all 8-adjacent interactables.

        ``kind`` is ``"door"`` for door tiles and ``"entity"`` for
        interactable entities (consoles, crates, lockers, etc.).
        """
        from world import tile_types as tt

        door_ids = {
            int(tt.door_closed["tile_id"]),
            int(tt.door_open["tile_id"]),
            int(tt.airlock_ext_closed["tile_id"]),
            int(tt.airlock_ext_open["tile_id"]),
        }
        switch_ids = {
            int(tt.airlock_switch_off["tile_id"]),
            int(tt.airlock_switch_on["tile_id"]),
        }
        reactor_core_id = int(tt.reactor_core["tile_id"])
        px, py = engine.player.x, engine.player.y
        dirs: list[tuple[int, int, str]] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = px + dx, py + dy
                if not engine.game_map.in_bounds(nx, ny):
                    continue
                tid = int(engine.game_map.tiles["tile_id"][nx, ny])
                # A furnishing comes first: generation can put a locker on a
                # door or switch tile, and it blocks the tile until searched.
                if engine.game_map.get_interactable_at(nx, ny):
                    dirs.append((dx, dy, "entity"))
                elif tid in door_ids:
                    dirs.append((dx, dy, "door"))
                elif tid in switch_ids:
                    dirs.append((dx, dy, "switch"))
                elif tid == reactor_core_id:
                    dirs.append((dx, dy, "reactor"))
        return dirs

    def _handle_interact_input(self, engine: Engine, key: Any) -> bool:
        """Handle direction key after interact prompt."""
        if key in cancel_keys():
            self._interact_pending = False
            return True

        move = _move_keys().get(key)
        if move:
            dx, dy = move
            self._interact_pending = False

            # Determine what's at the chosen offset using the shared helper
            kind = None
            for adx, ady, akind in self._adjacent_interact_dirs(engine):
                if adx == dx and ady == dy:
                    kind = akind
                    break
            if kind is None:
                engine.message_log.add_message("Nothing there.", GRAY)
                return True
            consumed = self._perform_interact(engine, dx, dy, kind)
            self._resolve_player_action(engine, consumed)
            return True

        self._interact_pending = False
        return True

    def _handle_scan_input(self, engine: Engine, key: Any) -> bool:
        """Handle number key after multi-scanner prompt."""
        import tcod.event

        if key in cancel_keys():
            self._scan_pending = None
            return True

        # Map number keys 1-9 to scanner index
        num_keys = {
            tcod.event.KeySym.N1: 0,
            tcod.event.KeySym.N2: 1,
            tcod.event.KeySym.N3: 2,
            tcod.event.KeySym.N4: 3,
        }
        idx = num_keys.get(key)
        if idx is not None and idx < len(self._scan_pending):
            scanner = self._scan_pending[idx]
            self._scan_pending = None
            from game.actions import ScanAction

            consumed = ScanAction(scanner=scanner).perform(engine, engine.player)
            self._resolve_player_action(engine, consumed)
            return True

        self._scan_pending = None
        return True

    # ------------------------------------------------------------------
    # Ground text (non-persistent, replaces each move)
    # ------------------------------------------------------------------

    def _update_ground_underfoot(self, engine: Engine) -> None:
        """Replace the ground-text with a description of the player's tile."""
        gm = engine.game_map
        p = engine.player

        tid = int(gm.tiles["tile_id"][p.x, p.y])
        from world.tile_types import describe_tile

        _, flavor = describe_tile(tid, biome=gm.biome)

        lines: list[tuple[str, Color]] = [(flavor, (140, 140, 160))]
        for item in gm.get_items_at(p.x, p.y):
            lines.append((f"You see {item.name} ({item.char}) here.", (180, 200, 255)))
        self._ground_lines = lines

    # ------------------------------------------------------------------
    # Actions (shared key map for movement)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_action(key: Any) -> Action | None:
        from game.actions import BumpAction, PickupAction, WaitAction

        move = _move_keys().get(key)
        if move:
            return BumpAction(*move)
        if is_action("wait", key):
            return WaitAction()
        if is_action("get", key):
            return PickupAction()
        return None

    # ------------------------------------------------------------------
    # Scan glow lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def _update_fov_with_scan(engine: Engine) -> None:
        """Recompute FOV and re-apply scan glow visibility if active."""
        engine.game_map.update_fov(engine.player.x, engine.player.y)
        if engine.scan_glow:
            import time as _time

            elapsed = _time.time() - engine.scan_glow["start_time"]
            from world.game_map import GameMap

            if elapsed < GameMap.SCAN_GLOW_DURATION:
                sg = engine.scan_glow
                engine.game_map.apply_scan_glow(sg["cx"], sg["cy"], sg["radius"])
            else:
                engine.scan_glow = None

    @staticmethod
    def _update_scan_glow(engine: Engine) -> None:
        """Check scan glow expiry, re-apply visibility on each render frame."""
        if not engine.scan_glow:
            return
        import time as _time

        elapsed = _time.time() - engine.scan_glow["start_time"]
        from world.game_map import GameMap

        if elapsed >= GameMap.SCAN_GLOW_DURATION:
            engine.scan_glow = None
            engine.game_map.update_fov(engine.player.x, engine.player.y)
        else:
            sg = engine.scan_glow
            engine.game_map.apply_scan_glow(sg["cx"], sg["cy"], sg["radius"])

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def on_render(self, console: Any, engine: Engine) -> None:
        if not engine.game_map or not engine.player:
            return

        # Automatic drift: advance one tile every DRIFT_INTERVAL seconds
        if engine.player.drifting and engine.player.fighter.hp > 0 and self._death_cause is None:
            now = time.time()
            if self._drift_timer == 0.0:
                # First frame of drift - initialize timer
                self._drift_timer = now
            elif now - self._drift_timer >= DRIFT_INTERVAL:
                self._drift_timer = now
                self._after_player_turn(engine)
                if engine.current_state is not self:
                    return
                self._update_fov_with_scan(engine)

        layout = self._layout
        cam_x = engine.player.x - layout.viewport_w // 2
        cam_y = engine.player.y - layout.viewport_h // 2
        cam_x = max(0, min(cam_x, max(0, engine.game_map.width - layout.viewport_w)))
        cam_y = max(0, min(cam_y, max(0, engine.game_map.height - layout.viewport_h)))

        # Manage scan glow lifecycle
        self._update_scan_glow(engine)

        engine.game_map.render(
            console,
            cam_x,
            cam_y,
            vp_x=0,
            vp_y=0,
            vp_w=layout.viewport_w,
            vp_h=layout.viewport_h,
            scan_glow=engine.scan_glow,
        )

        from ui.viewport_renderer import render_map_starfield

        render_map_starfield(
            console,
            engine.game_map,
            cam_x,
            cam_y,
            vp_x=0,
            vp_y=0,
            vp_w=layout.viewport_w,
            vp_h=layout.viewport_h,
        )

        if self._ranged_cursor is not None:
            cx, cy = self._ranged_cursor
            sx = cx - cam_x
            sy = cy - cam_y
            if 0 <= sx < layout.viewport_w and 0 <= sy < layout.viewport_h:
                console.bg[sx, sy] = (130, 60, 60)
        elif self._look_cursor is not None:
            cx, cy = self._look_cursor
            sx = cx - cam_x
            sy = cy - cam_y
            if 0 <= sx < layout.viewport_w and 0 <= sy < layout.viewport_h:
                console.bg[sx, sy] = (60, 60, 130)

        self._render_stats(console, engine, layout)
        engine.message_log.render(console, 0, layout.log_y, engine.CONSOLE_WIDTH, layout.log_h)

        # Death fade-out overlay
        if self._death_cause is not None:
            elapsed = time.time() - self._death_fade_start
            alpha = min(1.0, elapsed / DEATH_FADE_DURATION)
            dim_factor = 1.0 - alpha
            console.fg[:] = (console.fg * dim_factor).astype(console.fg.dtype)
            console.bg[:] = (console.bg * dim_factor).astype(console.bg.dtype)
            if alpha >= 1.0:
                from ui.game_over_state import GameOverState

                engine.switch_state(GameOverState(victory=False, cause=self._death_cause))

    def _render_stats(self, console: Any, engine: Engine, layout: SimpleNamespace) -> None:
        from ui.tactical_hud import HudView, render_stats

        if self.location:
            label = f"{self.location.name} ({self.location.loc_type})"
        elif getattr(self, "explore_ship", False):
            label = "YOUR SHIP"
        else:
            label = "DREADNOUGHT"
        view = HudView(
            location_label=label,
            explore_ship=getattr(self, "explore_ship", False),
            look_cursor=self._look_cursor,
            ranged_cursor=self._ranged_cursor,
            ground_lines=self._ground_lines,
        )
        render_stats(console, engine, layout, view)
