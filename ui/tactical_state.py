"""Tactical (dungeon exploration) state."""
from __future__ import annotations

import hashlib
import textwrap
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from engine.game_state import State
from ui.colors import DARK_GRAY, EQUIP_MSG, GRAY, PROMPT

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.actions import Action
    from world.galaxy import Location

# Minimum map size so dungeons stay playable when console is small
MIN_MAP_W = 60
MIN_MAP_H = 42
STATS_PANEL_W = 20
LOG_PANEL_H = 8
# Stats panel: reserved rows from bottom
CTRL_LINES = 4
GROUND_MAX_LINES_DEFAULT = 8
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

Color = Tuple[int, int, int]


def _area_key(location: Optional[Location], depth: int) -> Tuple[str, int]:
    """Stable key for area cache: (location_name, depth)."""
    loc_name = location.name if location else "the dungeon"
    return (loc_name, depth)


def _area_seed(location_name: str, depth: int) -> int:
    """Deterministic seed for dungeon layout so the same area is always the same layout."""
    raw = hashlib.md5(f"{location_name}_{depth}".encode()).hexdigest()[:8]
    return int(raw, 16)


from ui.keys import move_keys as _move_keys, confirm_keys, cancel_keys, action_keys, is_action


def _hint(name: str) -> str:
    """Build a HUD hint like '[x] look' from the action_keys registry."""
    _, label, verb = action_keys()[name]
    return f"[{label}] {verb}"


DRIFT_INTERVAL = 2.0  # seconds between automatic drift ticks
DEATH_FADE_DURATION = 1.0  # seconds to fade out tactical on player death


class TacticalState(State):
    def __init__(self, location: Optional[Location] = None, depth: int = 0) -> None:
        self.location = location
        self.depth = depth
        self.exit_pos: Optional[tuple[int, int]] = None
        self._look_cursor: Optional[tuple[int, int]] = None
        self._ranged_cursor: Optional[tuple[int, int]] = None
        self._interact_pending: bool = False
        self._scan_pending: Optional[list] = None  # list of scanner entities when choosing
        self._visible_enemies: List = []
        self._enemy_cycle_index: int = 0
        self._ground_lines: List[Tuple[str, Color]] = []
        self._layout: Optional[SimpleNamespace] = None
        self._drift_timer: float = 0.0
        # Death fade-out state
        self._death_cause: Optional[str] = None
        self._death_fade_start: float = 0.0

    def _max_enemies(self) -> int:
        return min(max(1, 1 + self.depth), 3)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_enter(self, engine: Engine) -> None:
        from world.dungeon_gen import generate_dungeon, respawn_creatures
        from game.entity import Entity, Fighter
        from game.suit import EVA_SUIT

        loc_name = self.location.name if self.location else "the dungeon"
        key = _area_key(self.location, self.depth)
        seed = _area_seed(loc_name, self.depth)
        max_enemies = self._max_enemies()

        # Environment and suit: from location data (galaxy sets vacuum for
        # derelicts/asteroids; starbases are pressurised unless breached).
        env = getattr(self.location, "environment", None)
        engine.environment = dict(env) if env else {}
        engine.suit = getattr(engine, "suit", None) or EVA_SUIT
        engine.suit.refill_pools()

        engine.active_effects.clear()
        self._layout = _layout(engine)
        layout = self._layout
        loc_type = self.location.loc_type if self.location else "derelict"

        cached = engine.area_cache.get(key)
        if cached and cached["game_map"].width == layout.map_w and cached["game_map"].height == layout.map_h:
            game_map = cached["game_map"]
            rooms = cached["rooms"]
            self.exit_pos = cached["exit_pos"]
            respawn_creatures(game_map, rooms, max_enemies=max_enemies, seed=None)
        else:
            game_map, rooms, exit_pos = generate_dungeon(
                width=layout.map_w, height=layout.map_h,
                max_enemies=max_enemies,
                max_items=1,
                seed=seed,
                loc_type=loc_type,
            )
            self.exit_pos = exit_pos
            engine.area_cache[key] = {
                "game_map": game_map,
                "rooms": rooms,
                "exit_pos": exit_pos,
                "seed": seed,
            }

        if not rooms:
            return

        px, py = rooms[0].center
        player = Entity(
            x=px, y=py, char="@", color=(255, 255, 255), name="Player",
            blocks_movement=True,
            fighter=Fighter(hp=10, max_hp=10, defense=0, power=1),
        )
        if engine._saved_player:
            sp = engine._saved_player
            player.fighter.hp = sp["hp"]
            player.fighter.max_hp = sp["max_hp"]
            player.fighter.defense = sp["defense"]
            player.fighter.power = sp["power"]
            player.fighter.base_power = sp["base_power"]
            player.inventory = sp.get("inventory", [])
            player.loadout = sp.get("loadout")
        game_map.entities.append(player)

        # Seed for space starfield — matches strategic viewport when available
        system_name = getattr(self.location, "system_name", "") if self.location else ""
        if system_name:
            game_map.space_seed = hash(system_name) & 0xFFFFFFFF

        engine.game_map = game_map
        engine.player = player

        # Sync environment with map: hull breaches/airlocks imply vacuum
        if game_map.hull_breaches or game_map.airlocks:
            engine.environment.setdefault("vacuum", 1)

        # Transfer mission loadout to player inventory on entry
        if hasattr(engine, 'mission_loadout'):
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

        engine.message_log.add_message(
            f"You enter {loc_name}.", (200, 200, 255)
        )
        self._update_ground_underfoot(engine)

    def on_exit(self, engine: Engine) -> None:
        if engine.game_map and engine.player:
            p = engine.player

            saved_inventory = list(p.inventory)
            saved_loadout = p.loadout

            engine._saved_player = {
                "hp": p.fighter.hp,
                "max_hp": p.fighter.max_hp,
                "defense": p.fighter.defense,
                "power": p.fighter.base_power,  # reset to base on exit
                "base_power": p.fighter.base_power,
                "inventory": saved_inventory,
                "loadout": saved_loadout,
            }
            # Convert reactor cores to fuel
            if engine.ship is not None:
                cores = [i for i in saved_inventory if i.item and i.item.get("type") == "reactor_core"]
                for core in cores:
                    added = min(core.item["value"], engine.ship.max_fuel - engine.ship.fuel)
                    if added > 0:
                        engine.ship.fuel += added
                        engine.message_log.add_message(
                            f"Reactor core converted to fuel. (+{added} fuel)",
                            EQUIP_MSG,
                        )
                    saved_inventory.remove(core)
                engine._saved_player["inventory"] = saved_inventory

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

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
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
            return True  # consumed — exit only via docking hatch

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

        # While drifting, block turn-consuming inputs — only UI actions above are allowed
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
            from game.loadout import Loadout
            loadout = getattr(engine.player, "loadout", None)
            scanners = loadout.get_all_scanners() if loadout else []
            if len(scanners) == 0:
                engine.message_log.add_message("You need a scanner in your loadout.", GRAY)
                consumed = 0
            elif len(scanners) == 1:
                from game.actions import ScanAction
                consumed = ScanAction(scanner=scanners[0]).perform(engine, engine.player)
            else:
                labels = " ".join(f"({i+1}) {s.name}" for i, s in enumerate(scanners))
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

        if not consumed:
            return True

        if self.exit_pos and (engine.player.x, engine.player.y) == self.exit_pos:
            engine.message_log.add_message("You return to your ship.", EQUIP_MSG)
            engine.pop_state()
            return True

        if engine.player.fighter.hp <= 0:
            self._handle_player_death(engine, "Killed in action.")
            return True

        for _ in range(consumed):
            self._after_player_turn(engine)
            if engine.current_state is not self:
                return True

        self._update_fov_with_scan(engine)
        if moved:
            self._update_ground_underfoot(engine)
        return True

    def _after_player_turn(self, engine: Engine) -> None:
        """Environment tick, radiation, drift, enemy turns. Switch to game over if dead."""
        from game.environment import (
            apply_environment_tick, apply_environment_tick_entity,
            trigger_decompression, process_decompression_step,
        )
        from game.hazards import apply_dot_effects

        engine.game_map.invalidate_entity_index()
        engine.game_map._fov_cache.clear()
        apply_environment_tick(engine)
        apply_dot_effects(engine)
        if engine.player.fighter.hp <= 0:
            self._handle_player_death(engine, "Succumbed to the environment.")
            return

        # Trigger new decompression events
        pending = engine.game_map._pending_decompression
        if pending:
            pull_dirs = trigger_decompression(
                engine, pending["breach_sources"], pending["newly_exposed"],
            )
            engine.game_map._pull_directions = pull_dirs
            engine.game_map._pending_decompression = None

        # Process ongoing decompression (up to 3 tiles/turn per entity)
        pull_dirs = engine.game_map._pull_directions
        if pull_dirs:
            for entity in list(engine.game_map.entities):
                if entity.decompression_moves > 0:
                    process_decompression_step(engine.game_map, entity, pull_dirs)
            # Clear pull directions when no entities are still being pulled
            if not any(e.decompression_moves > 0 for e in engine.game_map.entities):
                engine.game_map._pull_directions = None

        # Clean up entities killed by decompression impact
        for entity in list(engine.game_map.entities):
            if entity is engine.player:
                continue
            if entity.fighter and entity.fighter.hp <= 0:
                engine.message_log.add_message(
                    f"The {entity.name} is crushed by the decompression!",
                    (200, 200, 200),
                )
                engine.game_map.entities.remove(entity)

        # Check for player death from decompression impact
        if engine.player.fighter.hp <= 0:
            self._handle_player_death(engine, "Crushed by explosive decompression.")
            return

        # Player drift
        if engine.player.drifting:
            from world import tile_types as _tt
            _space_tid = int(_tt.space["tile_id"])
            dx, dy = engine.player.drift_direction
            nx, ny = engine.player.x + dx, engine.player.y + dy
            if not engine.game_map.in_bounds(nx, ny):
                engine.message_log.add_message(
                    "You drift beyond reach... lost to the void.", (255, 0, 0)
                )
                engine.player.fighter.hp = 0
                self._handle_player_death(engine, "Lost to the void.")
                return
            # Only space tiles are passable while drifting
            if engine.game_map.tiles["tile_id"][nx, ny] != _space_tid:
                engine.message_log.add_message(
                    "You slam into the hull. The impact is fatal.", (255, 0, 0)
                )
                engine.player.fighter.hp = 0
                self._handle_player_death(engine, "Slammed into the hull.")
                return
            engine.player.x = nx
            engine.player.y = ny
            engine.message_log.add_message(
                "You drift further into space...", (180, 100, 255)
            )

        # Enemy drift
        for entity in list(engine.game_map.entities):
            if entity is engine.player:
                continue
            if not entity.drifting:
                continue
            from world import tile_types as _tt
            _space_tid = int(_tt.space["tile_id"])
            edx, edy = entity.drift_direction
            enx, eny = entity.x + edx, entity.y + edy
            if not engine.game_map.in_bounds(enx, eny):
                if entity in engine.game_map.entities:
                    engine.game_map.entities.remove(entity)
                continue
            # Only space tiles are passable while drifting
            if engine.game_map.tiles["tile_id"][enx, eny] != _space_tid:
                if entity in engine.game_map.entities:
                    engine.game_map.entities.remove(entity)
                engine.message_log.add_message(
                    f"The {entity.name} slams into the hull!", (200, 200, 200)
                )
                continue
            entity.x = enx
            entity.y = eny

        engine.game_map.invalidate_entity_index()
        import debug
        if not debug.DISABLE_ENEMY_AI:
            for entity in list(engine.game_map.entities):
                if entity is engine.player:
                    continue
                if entity.ai and entity.fighter and entity.fighter.hp > 0:
                    entity.ai.perform(entity, engine)

        # Per-tile hazard damage for enemies
        for entity in list(engine.game_map.entities):
            if entity is engine.player:
                continue
            if entity.fighter and entity.fighter.hp > 0:
                apply_environment_tick_entity(engine, entity)

        if engine.player.fighter.hp <= 0:
            engine.message_log.add_message("You died.", (255, 0, 0))
            self._handle_player_death(engine, "Overwhelmed by hostiles.")

    # ------------------------------------------------------------------
    # Look mode
    # ------------------------------------------------------------------

    def _enter_look(self, engine: Engine) -> None:
        self._look_cursor = (engine.player.x, engine.player.y)
        self._update_ground_look(engine)

    def _handle_look_input(self, engine: Engine, key: Any) -> bool:
        import tcod.event

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
        from game.helpers import get_equipped_ranged_weapon
        weapon = get_equipped_ranged_weapon(engine.player)
        if not weapon:
            engine.message_log.add_message("No ranged weapon with ammo.", (255, 100, 100))
            return
        # Find visible enemies, sorted by distance (closest first)
        px, py = engine.player.x, engine.player.y
        self._visible_enemies = sorted(
            [
                e for e in engine.game_map.entities
                if e is not engine.player
                and e.fighter
                and e.fighter.hp > 0
                and engine.game_map.visible[e.x, e.y]
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
        if key in (tcod.event.KeySym.UP, tcod.event.KeySym.DOWN,
                   tcod.event.KeySym.k, tcod.event.KeySym.j,
                   tcod.event.KeySym.KP_8, tcod.event.KeySym.KP_2):
            if self._visible_enemies:
                if key in (tcod.event.KeySym.DOWN, tcod.event.KeySym.j,
                           tcod.event.KeySym.KP_2):
                    self._enemy_cycle_index = (self._enemy_cycle_index + 1) % len(self._visible_enemies)
                else:
                    self._enemy_cycle_index = (self._enemy_cycle_index - 1) % len(self._visible_enemies)
                e = self._visible_enemies[self._enemy_cycle_index]
                self._ranged_cursor = (e.x, e.y)
            return True

        if key in confirm_keys():
            # Fire at targeted enemy
            cx, cy = self._ranged_cursor
            target = engine.game_map.get_blocking_entity(cx, cy)
            if target and target.fighter and target is not engine.player:
                from game.actions import RangedAction
                consumed = RangedAction(target).perform(engine, engine.player)
                self._ranged_cursor = None
                if consumed:
                    if engine.player.fighter.hp <= 0:
                        self._handle_player_death(engine, "Killed in a firefight.")
                        return True
                    self._after_player_turn(engine)
                    if engine.current_state is not self:
                        return True
                    self._update_fov_with_scan(engine)
                self._update_ground_underfoot(engine)
            else:
                engine.message_log.add_message("No target at cursor.", GRAY)
            return True

        return True

    # ------------------------------------------------------------------
    @staticmethod
    def _perform_interact(engine: Engine, dx: int, dy: int, kind: str) -> int:
        """Dispatch an interact action based on kind."""
        if kind == "door":
            from game.actions import ToggleDoorAction
            return ToggleDoorAction(dx, dy).perform(engine, engine.player)
        elif kind == "switch":
            from game.actions import ToggleSwitchAction
            return ToggleSwitchAction(dx, dy).perform(engine, engine.player)
        elif kind == "reactor":
            from game.actions import TakeReactorCoreAction
            return TakeReactorCoreAction(dx, dy).perform(engine, engine.player)
        else:
            from game.actions import InteractAction
            return InteractAction(dx, dy).perform(engine, engine.player)

    # ------------------------------------------------------------------
    # Interact direction prompt
    # ------------------------------------------------------------------

    @staticmethod
    def _adjacent_interact_dirs(engine: Engine) -> List[Tuple[int, int, str]]:
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
        dirs: List[Tuple[int, int, str]] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = px + dx, py + dy
                if not engine.game_map.in_bounds(nx, ny):
                    continue
                tid = int(engine.game_map.tiles["tile_id"][nx, ny])
                if tid in door_ids:
                    dirs.append((dx, dy, "door"))
                elif tid in switch_ids:
                    dirs.append((dx, dy, "switch"))
                elif tid == reactor_core_id:
                    dirs.append((dx, dy, "reactor"))
                elif engine.game_map.get_interactable_at(nx, ny):
                    dirs.append((dx, dy, "entity"))
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

            if consumed:
                if self.exit_pos and (engine.player.x, engine.player.y) == self.exit_pos:
                    engine.message_log.add_message("You return to your ship.", EQUIP_MSG)
                    engine.pop_state()
                    return True
                for _ in range(consumed):
                    self._after_player_turn(engine)
                    if engine.current_state is not self:
                        return True
                self._update_fov_with_scan(engine)
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
            tcod.event.KeySym.N1: 0, tcod.event.KeySym.N2: 1,
            tcod.event.KeySym.N3: 2, tcod.event.KeySym.N4: 3,
        }
        idx = num_keys.get(key)
        if idx is not None and idx < len(self._scan_pending):
            scanner = self._scan_pending[idx]
            self._scan_pending = None
            from game.actions import ScanAction
            consumed = ScanAction(scanner=scanner).perform(engine, engine.player)
            if consumed:
                if engine.player.fighter.hp <= 0:
                    self._handle_player_death(engine, "Killed in action.")
                    return True
                for _ in range(consumed):
                    self._after_player_turn(engine)
                    if engine.current_state is not self:
                        return True
                self._update_fov_with_scan(engine)
            return True

        self._scan_pending = None
        return True

    def _update_ground_look_at_cursor(self, engine: Engine, cursor: tuple) -> None:
        cx, cy = cursor
        self._ground_lines = engine.game_map.describe_at(cx, cy, visible_only=True)

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

        lines: List[Tuple[str, Color]] = [(flavor, (140, 140, 160))]
        for item in gm.get_items_at(p.x, p.y):
            lines.append(
                (f"You see {item.name} ({item.char}) here.", (180, 200, 255))
            )
        self._ground_lines = lines

    # ------------------------------------------------------------------
    # Actions (shared key map for movement)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_action(key: Any) -> Optional[Action]:
        from game.actions import BumpAction, WaitAction, PickupAction

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
                # First frame of drift — initialize timer
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
            console, cam_x, cam_y,
            vp_x=0, vp_y=0, vp_w=layout.viewport_w, vp_h=layout.viewport_h,
            scan_glow=engine.scan_glow,
        )

        engine.game_map.animate_space(
            console, cam_x, cam_y,
            vp_x=0, vp_y=0, vp_w=layout.viewport_w, vp_h=layout.viewport_h,
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
        x = layout.stats_x + 1
        p = engine.player
        stats_h = layout.viewport_h
        ctrl_y = stats_h - CTRL_LINES

        if self.location:
            loc_label = f"{self.location.name} ({self.location.loc_type})"
        else:
            loc_label = "DREADNOUGHT"
        console.print(x=x, y=1, string=loc_label, fg=(180, 180, 255))
        from ui.colors import HEADER_SEP
        console.print(x=x, y=2, string="-" * (layout.stats_w - 2), fg=HEADER_SEP)

        from ui.colors import HP_GREEN, HP_YELLOW, HP_RED
        hp_ratio = p.fighter.hp / max(1, p.fighter.max_hp)
        if hp_ratio > 0.5:
            hp_color = HP_GREEN
        elif hp_ratio > 0.25:
            hp_color = HP_YELLOW
        else:
            hp_color = HP_RED
        console.print(x=x, y=4, string=f"HP: {p.fighter.hp}/{p.fighter.max_hp}", fg=hp_color)
        eff_def = p.fighter.defense + (engine.suit.defense_bonus if engine.suit else 0)
        console.print(x=x, y=5, string=f"DEF: {eff_def}", fg=(200, 200, 200))
        console.print(x=x, y=6, string=f"POW: {p.fighter.power}", fg=(200, 200, 200))

        # Suit resource bars (Phase 3)
        row = 8
        if engine.suit and engine.environment:
            console.print(x=x, y=row, string="SUIT:", fg=(180, 180, 200))
            row += 1
            for hazard_type in engine.environment:
                max_turns = engine.suit.resistances.get(hazard_type, 0)
                current = engine.suit.current_pools.get(hazard_type, 0)
                if hazard_type == "vacuum":
                    label = "O2 "
                elif hazard_type == "low_gravity":
                    label = "GRV"
                else:
                    label = hazard_type[:3].upper()
                if max_turns > 0:
                    ratio = current / max_turns
                    if ratio > 0.5:
                        bar_color = (0, 255, 0)
                    elif ratio > 0.25:
                        bar_color = (255, 255, 0)
                    else:
                        bar_color = (255, 0, 0)
                    bar_w = min(10, layout.stats_w - 8)
                    filled = max(0, int(bar_w * ratio))
                    bar = "█" * filled + "░" * (bar_w - filled)
                    console.print(x=x, y=row, string=f"{label}: {bar}", fg=bar_color)
                    console.print(x=x + 4 + bar_w + 1, y=row, string=f"{current}/{max_turns}", fg=GRAY)
                else:
                    console.print(x=x, y=row, string=f"{label}: --", fg=DARK_GRAY)
                row += 1
            row += 1

        # Active hazards at player position
        from game.environment import GLOBAL_HAZARDS, NON_DAMAGING_HAZARDS
        engine.game_map.recalculate_hazards()
        active = engine.game_map.get_hazards_at(p.x, p.y)
        # Include global hazards from environment
        if engine.environment:
            for h in engine.environment:
                if h in GLOBAL_HAZARDS and engine.environment[h] > 0:
                    active.add(h)
        damaging_active = {h for h in active if h not in NON_DAMAGING_HAZARDS}
        if active:
            console.print(x=x, y=row, string="HAZARDS:", fg=(255, 100, 100))
            row += 1
            for h in sorted(active):
                label = h.replace("_", " ").upper()
                if h in NON_DAMAGING_HAZARDS:
                    color = PROMPT
                else:
                    color = (255, 80, 80)
                console.print(x=x, y=row, string=f"! {label}", fg=color)
                row += 1
            row += 1
        elif engine.environment and any(
            v > 0 and k not in NON_DAMAGING_HAZARDS
            for k, v in engine.environment.items()
        ):
            console.print(x=x, y=row, string="NO HAZARDS", fg=(0, 200, 100))
            row += 2

        # LOADOUT display (2 slots)
        loadout_section_start = row + 1
        ground_block_lines = 1 + GROUND_MAX_LINES_DEFAULT
        ground_header_y = loadout_section_start + 3  # 1 header + 2 slot lines
        ground_max_lines = min(GROUND_MAX_LINES_DEFAULT, max(1, ctrl_y - 1 - ground_header_y))

        console.print(x=x, y=row, string="LOADOUT:", fg=(180, 180, 200))
        row += 1
        lo = p.loadout
        inv_width = layout.stats_w - 2
        if lo:
            for si, slot_item in enumerate((lo.slot1, lo.slot2)):
                label = f"S{si + 1}"
                if slot_item:
                    ammo = slot_item.item.get("ammo") if slot_item.item else None
                    max_ammo = slot_item.item.get("max_ammo") if slot_item.item else None
                    if ammo is not None and max_ammo is not None:
                        slot_label = f"{label}: {slot_item.name} {ammo}/{max_ammo}"
                    else:
                        slot_label = f"{label}: {slot_item.name}"
                else:
                    slot_label = f"{label}: --"
                console.print(x=x, y=row + si, string=slot_label[:inv_width], fg=(150, 150, 255))
        else:
            console.print(x=x, y=row, string="(none)", fg=(80, 80, 80))

        # --- Ground text block (non-persistent) ---
        if self._look_cursor is not None:
            header = "LOOKING AT:"
            header_color = PROMPT
        else:
            header = "UNDERFOOT:"
            header_color = (140, 140, 170)
        console.print(x=x, y=ground_header_y, string=header, fg=header_color)
        ground_width = max(1, layout.stats_w - 2)
        wrapped: List[Tuple[str, Color]] = []
        for text, color in self._ground_lines:
            for line in textwrap.wrap(text, width=ground_width):
                wrapped.append((line, color))
        for i, (text, color) in enumerate(wrapped[:ground_max_lines]):
            console.print(
                x=x, y=ground_header_y + 1 + i,
                string=text,
                fg=color,
            )

        # NEARBY section (below UNDERFOOT) — unified visible + scan data
        from game.scanner import build_nearby_entries
        nearby_y = ground_header_y + 1 + min(len(wrapped), ground_max_lines) + 1
        nearby_entries = build_nearby_entries(engine)
        if nearby_entries:
            _cat_colors = {
                "creature": (255, 80, 80),
                "hazard": (255, 255, 0),
                "container": (80, 200, 80),
                "item": (100, 200, 255),
            }
            header = "NEARBY:"
            header_color = (180, 180, 200)
            console.print(x=x, y=nearby_y, string=header, fg=header_color)
            nearby_y += 1
            for entry in nearby_entries[:8]:
                targeted = (self._ranged_cursor is not None
                            and entry.x == self._ranged_cursor[0]
                            and entry.y == self._ranged_cursor[1])
                color = _cat_colors.get(entry.category, (180, 180, 200))
                prefix = ">" if targeted else entry.display_char
                line = f"{prefix} {entry.label} {entry.distance}"
                if targeted:
                    color = (255, 255, 255)
                console.print(x=x, y=nearby_y, string=line[:layout.stats_w - 2], fg=color)
                nearby_y += 1

        # --- Controls ---
        if self._ranged_cursor is not None:
            cx, cy = self._ranged_cursor
            dx = abs(p.x - cx)
            dy = abs(p.y - cy)
            dist = max(dx, dy)
            from game.helpers import get_equipped_ranged_weapon
            wpn_ctrl = get_equipped_ranged_weapon(p)
            max_range = wpn_ctrl.item.get("range", 5) if wpn_ctrl else 0
            in_range = dist <= max_range
            look_label = f"[f] {dist}/{max_range}"
            look_color = EQUIP_MSG if in_range else (255, 100, 100)
        elif self._look_cursor is not None:
            ak = action_keys()
            look_label = f"[{ak['look'][1]}] LOOKING"
            look_color = PROMPT
        else:
            look_label = _hint("look")
            look_color = (70, 70, 70)

        col2_x = x + layout.stats_w // 2
        hint_color = (70, 70, 70)
        console.print(x=x, y=ctrl_y, string=look_label, fg=look_color)
        console.print(x=col2_x, y=ctrl_y, string=_hint("fire"), fg=hint_color)
        console.print(x=x, y=ctrl_y + 1, string=_hint("inventory"), fg=hint_color)
        console.print(x=col2_x, y=ctrl_y + 1, string=_hint("scan"), fg=hint_color)
        console.print(x=x, y=ctrl_y + 2, string=_hint("interact"), fg=hint_color)
        console.print(x=col2_x, y=ctrl_y + 2, string=_hint("get"), fg=hint_color)
        console.print(x=x, y=ctrl_y + 3, string=_hint("wait"), fg=hint_color)
        console.print(x=col2_x, y=ctrl_y + 3, string=_hint("quit"), fg=hint_color)
