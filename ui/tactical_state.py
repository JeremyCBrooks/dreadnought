"""Tactical (dungeon exploration) state."""
from __future__ import annotations

import hashlib
import textwrap
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from engine.game_state import State

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
CTRL_LINES = 6
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


_MOVE_KEYS = None


def _move_keys():
    """Lazy-build the movement key map (avoids top-level tcod import). Cached after first call."""
    global _MOVE_KEYS
    if _MOVE_KEYS is not None:
        return _MOVE_KEYS
    import tcod.event
    K = tcod.event.KeySym
    _MOVE_KEYS = {
        K.UP: (0, -1), K.DOWN: (0, 1), K.LEFT: (-1, 0), K.RIGHT: (1, 0),
        K.KP_1: (-1, 1), K.KP_2: (0, 1), K.KP_3: (1, 1),
        K.KP_4: (-1, 0), K.KP_6: (1, 0),
        K.KP_7: (-1, -1), K.KP_8: (0, -1), K.KP_9: (1, -1),
        K.h: (-1, 0), K.j: (0, 1), K.k: (0, -1), K.l: (1, 0),
        K.y: (-1, -1), K.u: (1, -1), K.b: (-1, 1), K.n: (1, 1),
    }
    return _MOVE_KEYS


class TacticalState(State):
    def __init__(self, location: Optional[Location] = None, depth: int = 0) -> None:
        self.location = location
        self.depth = depth
        self.exit_pos: Optional[tuple[int, int]] = None
        self._look_cursor: Optional[tuple[int, int]] = None
        self._ranged_cursor: Optional[tuple[int, int]] = None
        self._visible_enemies: List = []
        self._enemy_cycle_index: int = 0
        self._ground_lines: List[Tuple[str, Color]] = []
        self._layout: Optional[SimpleNamespace] = None

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
        max_enemies = max(1, 1 + self.depth)

        # Environment and suit (Phase 3): from location or default vacuum
        env = getattr(self.location, "environment", None)
        engine.environment = env if env is not None else {"vacuum": 1}
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
            player.collection_tank = sp.get("collection_tank", [])
        game_map.entities.append(player)

        engine.game_map = game_map
        engine.player = player

        # Apply pending loadout from LoadoutState
        pending = getattr(engine, '_pending_loadout', None)
        if pending:
            player.loadout = pending
            engine._pending_loadout = None
            # Auto-apply melee weapon power bonus
            w = pending.weapon
            if w and w.item and w.item.get("weapon_class", "melee") == "melee":
                player.fighter.power = player.fighter.base_power + w.item.get("value", 0)

        game_map.update_fov(player.x, player.y)

        engine.message_log.add_message(
            f"You enter {loc_name}.", (200, 200, 255)
        )
        self._update_ground_underfoot(engine)

    def on_exit(self, engine: Engine) -> None:
        if engine.game_map and engine.player:
            p = engine.player

            if getattr(engine, 'ship', None):
                # Transfer loadout items back to cargo
                if p.loadout:
                    for item in p.loadout.all_items():
                        engine.ship.add_cargo(item)
                # Transfer collection tank to cargo
                for item in list(p.collection_tank):
                    engine.ship.add_cargo(item)
                # Transfer any legacy inventory to cargo
                for item in list(p.inventory):
                    engine.ship.add_cargo(item)
                saved_inventory = []
                saved_loadout = None
                saved_tank = []
            else:
                saved_inventory = list(p.inventory)
                saved_loadout = p.loadout
                saved_tank = list(p.collection_tank)

            engine._saved_player = {
                "hp": p.fighter.hp,
                "max_hp": p.fighter.max_hp,
                "defense": p.fighter.defense,
                "power": p.fighter.base_power,  # reset to base on exit
                "base_power": p.fighter.base_power,
                "inventory": saved_inventory,
                "loadout": saved_loadout,
                "collection_tank": saved_tank,
            }
            key = _area_key(self.location, self.depth)
            if engine.player in engine.game_map.entities:
                engine.game_map.entities.remove(engine.player)
            if key in engine.area_cache:
                engine.area_cache[key]["game_map"] = engine.game_map
                engine.area_cache[key]["exit_pos"] = self.exit_pos
        engine.game_map = None
        engine.player = None

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        import tcod.event
        key = event.sym

        if self._ranged_cursor is not None:
            return self._handle_ranged_input(engine, key)

        if self._look_cursor is not None:
            return self._handle_look_input(engine, key)

        if key == tcod.event.KeySym.ESCAPE:
            return True  # consumed — exit only via docking hatch

        if key == tcod.event.KeySym.PAGEUP:
            engine.message_log.scroll(1)
            return True
        if key == tcod.event.KeySym.PAGEDOWN:
            engine.message_log.scroll(-1)
            return True

        if key == tcod.event.KeySym.i:
            from ui.inventory_state import InventoryState
            engine.push_state(InventoryState())
            return True

        if key == tcod.event.KeySym.x:
            self._enter_look(engine)
            return True

        if key == tcod.event.KeySym.f:
            self._enter_ranged(engine)
            return True

        if key == tcod.event.KeySym.e:
            from game.actions import InteractAction
            consumed = InteractAction().perform(engine, engine.player)
            moved = False
        elif key == tcod.event.KeySym.s:
            from game.actions import ScanAction
            consumed = ScanAction().perform(engine, engine.player)
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
            engine.message_log.add_message("You return to your ship.", (100, 255, 100))
            engine.pop_state()
            return True

        if engine.player.fighter.hp <= 0:
            from ui.game_over_state import GameOverState
            engine.switch_state(GameOverState(victory=False))
            return True

        for _ in range(int(consumed)):
            self._after_player_turn(engine)
            if engine.current_state is not self:
                return True

        engine.game_map.update_fov(engine.player.x, engine.player.y)
        if moved:
            self._update_ground_underfoot(engine)
        return True

    def _after_player_turn(self, engine: Engine) -> None:
        """Environment tick, radiation, enemy turns. Switch to game over if dead."""
        from game.environment import apply_environment_tick
        from game.hazards import apply_dot_effects
        from ui.game_over_state import GameOverState

        apply_environment_tick(engine)
        apply_dot_effects(engine)
        if engine.player.fighter.hp <= 0:
            engine.switch_state(GameOverState(victory=False))
            return

        import debug
        if not debug.DISABLE_ENEMY_AI:
            for entity in list(engine.game_map.entities):
                if entity is engine.player:
                    continue
                if entity.ai and entity.fighter and entity.fighter.hp > 0:
                    entity.ai.perform(entity, engine)

        if engine.player.fighter.hp <= 0:
            engine.message_log.add_message("You died.", (255, 0, 0))
            engine.switch_state(GameOverState(victory=False))

    # ------------------------------------------------------------------
    # Look mode
    # ------------------------------------------------------------------

    def _enter_look(self, engine: Engine) -> None:
        self._look_cursor = (engine.player.x, engine.player.y)
        self._update_ground_look(engine)

    def _handle_look_input(self, engine: Engine, key: Any) -> bool:
        import tcod.event
        K = tcod.event.KeySym

        if key in (K.ESCAPE, K.x, K.RETURN):
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
        from game.actions import _get_equipped_ranged_weapon
        weapon = _get_equipped_ranged_weapon(engine.player)
        if not weapon:
            engine.message_log.add_message("No ranged weapon with ammo.", (255, 100, 100))
            return
        # Find visible enemies
        self._visible_enemies = [
            e for e in engine.game_map.entities
            if e is not engine.player
            and e.fighter
            and e.fighter.hp > 0
            and engine.game_map.visible[e.x, e.y]
        ]
        if self._visible_enemies:
            self._enemy_cycle_index = 0
            e = self._visible_enemies[0]
            self._ranged_cursor = (e.x, e.y)
        else:
            self._ranged_cursor = (engine.player.x, engine.player.y)
        self._update_ground_look_at_cursor(engine, self._ranged_cursor)

    def _handle_ranged_input(self, engine: Engine, key: Any) -> bool:
        import tcod.event
        K = tcod.event.KeySym

        if key == K.ESCAPE:
            self._ranged_cursor = None
            self._update_ground_underfoot(engine)
            return True

        if key == K.TAB and self._visible_enemies:
            self._enemy_cycle_index = (self._enemy_cycle_index + 1) % len(self._visible_enemies)
            e = self._visible_enemies[self._enemy_cycle_index]
            self._ranged_cursor = (e.x, e.y)
            self._update_ground_look_at_cursor(engine, self._ranged_cursor)
            return True

        move = _move_keys().get(key)
        if move:
            cx, cy = self._ranged_cursor
            nx, ny = cx + move[0], cy + move[1]
            if engine.game_map.in_bounds(nx, ny):
                self._ranged_cursor = (nx, ny)
                self._update_ground_look_at_cursor(engine, self._ranged_cursor)
            return True

        if key == K.RETURN:
            # Fire at cursor position
            cx, cy = self._ranged_cursor
            target = engine.game_map.get_blocking_entity(cx, cy)
            if target and target.fighter and target is not engine.player:
                from game.actions import RangedAction
                consumed = RangedAction(target).perform(engine, engine.player)
                self._ranged_cursor = None
                if consumed:
                    if engine.player.fighter.hp <= 0:
                        from ui.game_over_state import GameOverState
                        engine.switch_state(GameOverState(victory=False))
                        return True
                    self._after_player_turn(engine)
                    if engine.current_state is not self:
                        return True
                    engine.game_map.update_fov(engine.player.x, engine.player.y)
                self._update_ground_underfoot(engine)
            else:
                engine.message_log.add_message("No target at cursor.", (150, 150, 150))
            return True

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
        _, flavor = describe_tile(tid)

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
        import tcod.event
        from game.actions import BumpAction, WaitAction, PickupAction

        WAIT_KEYS = {tcod.event.KeySym.PERIOD, tcod.event.KeySym.KP_5}
        PICKUP_KEYS = {tcod.event.KeySym.g, tcod.event.KeySym.COMMA}

        move = _move_keys().get(key)
        if move:
            return BumpAction(*move)
        if key in WAIT_KEYS:
            return WaitAction()
        if key in PICKUP_KEYS:
            return PickupAction()
        return None

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def on_render(self, console: Any, engine: Engine) -> None:
        if not engine.game_map or not engine.player:
            return

        layout = self._layout
        cam_x = engine.player.x - layout.viewport_w // 2
        cam_y = engine.player.y - layout.viewport_h // 2
        cam_x = max(0, min(cam_x, max(0, engine.game_map.width - layout.viewport_w)))
        cam_y = max(0, min(cam_y, max(0, engine.game_map.height - layout.viewport_h)))

        engine.game_map.render(
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
        console.print(x=x, y=2, string="-" * (layout.stats_w - 2), fg=(60, 60, 80))

        hp_ratio = p.fighter.hp / max(1, p.fighter.max_hp)
        if hp_ratio > 0.5:
            hp_color = (0, 255, 0)
        elif hp_ratio > 0.25:
            hp_color = (255, 255, 0)
        else:
            hp_color = (255, 0, 0)
        console.print(x=x, y=4, string=f"HP: {p.fighter.hp}/{p.fighter.max_hp}", fg=hp_color)
        eff_def = p.fighter.defense + (engine.suit.defense_bonus if engine.suit else 0)
        console.print(x=x, y=5, string=f"DEF: {eff_def}", fg=(200, 200, 200))
        console.print(x=x, y=6, string=f"POW: {p.fighter.power}", fg=(200, 200, 200))

        from game.actions import _get_equipped_ranged_weapon
        wpn = _get_equipped_ranged_weapon(p)
        if wpn:
            ammo = wpn.item.get("ammo", 0)
            max_ammo = wpn.item.get("max_ammo", ammo)
            console.print(x=x, y=7, string=f"WPN: {wpn.name} {ammo}/{max_ammo}", fg=(200, 180, 100))
        else:
            console.print(x=x, y=7, string="WPN: --", fg=(80, 80, 80))

        # Suit resource bars (Phase 3)
        row = 9
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
                    console.print(x=x + 4 + bar_w + 1, y=row, string=f"{current}/{max_turns}", fg=(150, 150, 150))
                else:
                    console.print(x=x, y=row, string=f"{label}: --", fg=(100, 100, 100))
                row += 1
            row += 1

        # LOADOUT display (4 slots)
        loadout_section_start = row + 1
        ground_block_lines = 1 + GROUND_MAX_LINES_DEFAULT
        ground_header_y = loadout_section_start + 5  # 1 header + 4 slot lines
        ground_max_lines = min(GROUND_MAX_LINES_DEFAULT, max(1, ctrl_y - 1 - ground_header_y))

        console.print(x=x, y=row, string="LOADOUT:", fg=(180, 180, 200))
        row += 1
        lo = p.loadout
        inv_width = layout.stats_w - 2
        if lo:
            wpn_name = lo.weapon.name if lo.weapon else "--"
            tool_name = lo.tool.name if lo.tool else "--"
            c1_name = lo.consumable1.name if lo.consumable1 else "--"
            c2_name = lo.consumable2.name if lo.consumable2 else "--"
            console.print(x=x, y=row, string=f"WPN: {wpn_name}"[:inv_width], fg=(150, 150, 255))
            console.print(x=x, y=row + 1, string=f"TOOL: {tool_name}"[:inv_width], fg=(150, 150, 255))
            console.print(x=x, y=row + 2, string=f"C1: {c1_name}"[:inv_width], fg=(150, 150, 255))
            console.print(x=x, y=row + 3, string=f"C2: {c2_name}"[:inv_width], fg=(150, 150, 255))
        else:
            console.print(x=x, y=row, string="(none)", fg=(80, 80, 80))

        # --- Ground text block (non-persistent) ---
        if self._ranged_cursor is not None:
            header = "TARGETING:"
            header_color = (255, 100, 100)
        elif self._look_cursor is not None:
            header = "LOOKING AT:"
            header_color = (200, 200, 100)
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

        # --- Controls ---
        if self._ranged_cursor is not None:
            cx, cy = self._ranged_cursor
            dx = abs(p.x - cx)
            dy = abs(p.y - cy)
            dist = max(dx, dy)
            wpn_ctrl = _get_equipped_ranged_weapon(p)
            max_range = wpn_ctrl.item.get("range", 5) if wpn_ctrl else 0
            in_range = dist <= max_range
            look_label = f"TARGETING: {dist}/{max_range}"
            look_color = (100, 255, 100) if in_range else (255, 100, 100)
        elif self._look_cursor is not None:
            look_label = "[x] LOOKING"
            look_color = (200, 200, 100)
        else:
            look_label = "[x]look"
            look_color = (70, 70, 70)

        console.print(x=x, y=ctrl_y, string=look_label, fg=look_color)
        console.print(x=x, y=ctrl_y + 1, string="[i]nventory [f]ire", fg=(70, 70, 70))
        console.print(x=x, y=ctrl_y + 2, string="[e] interact [s] scan", fg=(70, 70, 70))
        console.print(x=x, y=ctrl_y + 3, string="[g]et item", fg=(70, 70, 70))
        console.print(x=x, y=ctrl_y + 4, string="[.]wait", fg=(70, 70, 70))
        console.print(x=x, y=ctrl_y + 5, string="arrows/vi:move", fg=(70, 70, 70))
