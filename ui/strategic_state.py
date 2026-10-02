"""Strategic (star system navigation) state with compass rose starmap."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine
    from world.galaxy import Galaxy

# Compass rose line offsets: direction -> list of (dx, dy) cells from center
# Terminal cells are ~2:1 (tall), so horizontal lines use 2x spacing and
# diagonals step 2 cols per 1 row to look correct.
_ROSE_LINES: dict[tuple[int, int], list[tuple[int, int]]] = {
    (0, -1): [(0, -1), (0, -2), (0, -3), (0, -4)],
    (0, 1): [(0, 1), (0, 2), (0, 3), (0, 4)],
    (-1, 0): [(-2, 0), (-4, 0), (-6, 0), (-8, 0)],
    (1, 0): [(2, 0), (4, 0), (6, 0), (8, 0)],
    (-1, -1): [(-2, -1), (-4, -2), (-6, -3), (-8, -4)],
    (1, -1): [(2, -1), (4, -2), (6, -3), (8, -4)],
    (-1, 1): [(-2, 1), (-4, 2), (-6, 3), (-8, 4)],
    (1, 1): [(2, 1), (4, 2), (6, 3), (8, 4)],
}

# Characters for compass lines by direction
_ROSE_CHARS: dict[tuple[int, int], str] = {
    (0, -1): "|",
    (0, 1): "|",
    (-1, 0): "-",
    (1, 0): "-",
    (-1, -1): "\\",
    (1, -1): "/",
    (-1, 1): "/",
    (1, 1): "\\",
}


_RED = (255, 80, 80)
_WARNING = (255, 200, 100)
_DRIFT = (200, 100, 100)
_TRAVEL = (100, 200, 255)

# "{item}" is the name of the cargo item that was lost.
_CARGO_LOST_MSGS: list[str] = [
    "A crate tumbles into the void. {item} is lost.",
    "The ship lurches and {item} slides out of the cargo bay.",
    "An impact shakes {item} loose. It spins away into the dark.",
    "Emergency venting ejects {item} to stabilize the ship.",
    "The cargo hold buckles. {item} is pushed into space.",
    "A hull breach tears {item} from its moorings.",
    "Gravity shifts and {item} tumbles out through a gap in the hull.",
    "You watch helplessly as {item} drifts away into the void.",
]

_DRIFT_DAMAGE_MSGS: list[str] = [
    "The hull groans under the stress of unshielded drift!",
    "Unable to maneuver, your ship strikes something.",
    "Metal screams as the hull scrapes against debris.",
    "A shudder runs through the ship.",
    "Without power, the ship drifts helplessly into an asteroid. The hull dents inward.",
    "Micro-debris peppers the hull.",
    "The ship tumbles, slamming broadside into a rock.",
    "An alarm blares as the hull deforms under impact.",
]

_BREAK_AWAY_DAMAGE_MSGS: list[str] = [
    "Hull plating peels away where the clamps held on.",
    "The airlock frame buckles as the boarding craft is ripped off.",
    "Metal shrieks. A strip of hull goes with the pirate ship.",
    "The ship wrenches sideways; something structural gives.",
]


def _gauge_color(ratio: float) -> tuple[int, int, int]:
    """Return green/yellow/red color based on a 0-1 ratio."""
    from data.colors import HP_GREEN, HP_RED, HP_YELLOW

    if ratio > 0.5:
        return HP_GREEN
    if ratio >= 0.3:
        return HP_YELLOW
    return HP_RED


def _render_gauge(console: Any, x: int, y: int, label: str, value: int, max_value: int) -> None:
    """Render a labeled gauge like 'FUEL: 5/10' with ratio-based coloring."""
    ratio = value / max_value if max_value > 0 else 0
    console.print(x=x, y=y, string=f"{label}: {value}/{max_value}", fg=_gauge_color(ratio))


def _direction(sys_a: Any, sys_b: Any) -> tuple[int, int]:
    dx = sys_b.gx - sys_a.gx
    dy = sys_b.gy - sys_a.gy
    return ((dx > 0) - (dx < 0), (dy > 0) - (dy < 0))


class StrategicState(State):
    needs_animation = True

    def __init__(self, galaxy: Galaxy) -> None:
        self.galaxy = galaxy
        self.selected = 0
        self.focus = "locations"  # "locations" or "navigation"

    def on_enter(self, engine: Engine) -> None:
        engine.message_log.add_message("You are aboard your ship.", (180, 180, 220))

    def _connection_by_direction(self) -> dict[tuple[int, int], str]:
        """Map each direction to the connected system name in that direction."""
        system = self.galaxy.systems[self.galaxy.current_system]
        result: dict[tuple[int, int], str] = {}
        for neighbor_name in system.connections:
            neighbor = self.galaxy.systems[neighbor_name]
            d = _direction(system, neighbor)
            result[d] = neighbor_name
        return result

    def ev_key(self, engine: Engine, event: Any) -> bool:
        import tcod.event

        from engine.keys import confirm_keys, is_action, move_keys
        from game.interdiction import current_interdiction

        key = event.sym
        system = self.galaxy.systems[self.galaxy.current_system]

        # Message log scrolling
        if self._handle_log_scroll(engine, key):
            return True

        # Quit confirmation
        if key == tcod.event.KeySym.ESCAPE or is_action("quit", key):
            from ui.confirm_quit_state import ConfirmQuitState

            engine.push_state(ConfirmQuitState())
            return True

        # Tab toggles focus
        if key == tcod.event.KeySym.TAB:
            self.focus = "navigation" if self.focus == "locations" else "locations"
            return True

        # Cargo works in either focus
        if is_action("cargo", key):
            from ui.cargo_state import CargoState

            engine.push_state(CargoState())
            return True

        if key == tcod.event.KeySym.M:
            from ui.galaxy_map_state import GalaxyMapState

            engine.push_state(GalaxyMapState(self.galaxy))
            return True

        if key == tcod.event.KeySym.S:
            from ui.tactical_state import TacticalState

            engine.push_state(TacticalState(explore_ship=True))
            return True

        direction = move_keys().get(key)

        if self.focus == "locations":
            if direction:
                _, dy = direction
                if dy < 0:
                    self.selected = max(0, self.selected - 1)
                elif dy > 0:
                    self.selected = min(len(system.locations) - 1, self.selected + 1)
                return True
            if key in confirm_keys():
                if not system.locations:
                    return True
                loc = system.locations[self.selected]
                loc.visited = True
                engine.message_log.add_message(f"Docking at {loc.name}...")
                from ui.briefing_state import BriefingState

                engine.push_state(BriefingState(location=loc, depth=system.depth))
                return True

        else:  # navigation focus
            if direction:
                conn_map = self._connection_by_direction()
                if direction in conn_map:
                    dest_name = conn_map[direction]
                    cost = self.galaxy.travel_cost(dest_name)
                    # A hard-docked ship can only leave by tearing free, so ask
                    # first. Drift (fuel=0 path) tears free unasked — see _drift().
                    if engine.ship.fuel > 0 and engine.ship.fuel >= cost:
                        active = current_interdiction(engine)
                        if active is not None and not active.resolved:
                            from ui.break_away_state import BreakAwayState

                            engine.push_state(BreakAwayState(self, dest_name))
                            return True
                    if not engine.ship.consume_fuel(cost):
                        if engine.ship.fuel == 0:
                            self._drift(engine)
                        else:
                            engine.message_log.add_message("Not enough fuel.", _RED)
                        return True
                    engine.message_log.add_message(f"Traveling to {dest_name}.", _TRAVEL)
                    self._arrive(engine, dest_name)
                return True
            if key in confirm_keys():
                return True

        return False

    def _check_victory(self, engine: Engine) -> bool:
        """End the game in victory if the ship is home with the Dreadnought core aboard."""
        if self.galaxy.current_system != self.galaxy.home_system:
            return False
        if not any(c.item and c.item.get("type") == "dreadnought_core" for c in engine.ship.cargo):
            return False
        from ui.game_over_state import GameOverState

        engine.switch_state(
            GameOverState(
                victory=True,
                title="VICTORY",
                cause="You delivered the Dreadnought's reactor core. Unlimited energy is yours.",
            )
        )
        return True

    def _drift_destination(self) -> str:
        """Pick a weighted-random neighbor, preferring systems with unvisited derelicts."""
        system = self.galaxy.systems[self.galaxy.current_system]
        neighbors = list(system.connections.keys())
        weights = []
        for name in neighbors:
            sys = self.galaxy.systems[name]
            has_derelict = any(loc.loc_type == "derelict" and not loc.visited for loc in sys.locations)
            weights.append(5 if has_derelict else 1)
        return random.choices(neighbors, weights=weights, k=1)[0]

    def _arrive(self, engine: Engine, dest_name: str, interdictable: bool = True) -> None:
        """Put the ship in *dest_name*; pirates may be waiting unless *interdictable* is False."""
        self.galaxy.current_system = dest_name
        if interdictable:
            self.galaxy.arrive_at(dest_name, ship=engine.ship, rng=engine.rng(f"interdiction:{dest_name}"))
        else:
            self.galaxy.arrive_at(dest_name)
        self.selected = 0
        self._check_victory(engine)

    def _tear_free(self, engine: Engine, message: str) -> None:
        """Snap any attached boarding craft off: resolve it and restore the original ship map."""
        source = self.galaxy.systems[self.galaxy.current_system]
        active = getattr(source, "interdiction", None)
        if active is None or active.resolved:
            return
        from game.interdiction import restore_original_ship_map

        active.resolve()
        restore_original_ship_map(active, engine.ship)
        engine.message_log.add_message(message, _WARNING)

    def _jettison_cargo(self, engine: Engine, rng: Any) -> bool:
        """Lose one random cargo item to space. Returns True if that ended the game."""
        item = rng.choice(engine.ship.cargo)
        engine.ship.remove_cargo(item)
        engine.message_log.add_message(rng.choice(_CARGO_LOST_MSGS).format(item=item.name), _RED)
        if not (item.item and item.item.get("type") == "dreadnought_core"):
            return False
        self._game_over(
            engine,
            title="THE CORE IS LOST",
            cause="The Dreadnought's reactor core tumbles into the void. All hope is lost.",
        )
        return True

    def _damage_hull(self, engine: Engine, amount: int, messages: list[str], cause: str, rng: Any) -> bool:
        """Take *amount* hull damage. Returns True if the ship broke apart (*cause* ends the game)."""
        engine.ship.damage_hull(amount)
        engine.message_log.add_message(rng.choice(messages), (255, 120, 50))
        if engine.ship.hull > 0:
            return False
        engine.message_log.add_message("The hull buckles and breaks apart...", (255, 0, 0))
        self._game_over(engine, title="SHIP DESTROYED", cause=cause)
        return True

    @staticmethod
    def _game_over(engine: Engine, title: str, cause: str) -> None:
        from ui.game_over_state import GameOverState

        engine.switch_state(GameOverState(title=title, cause=cause))

    def _drift(self, engine: Engine) -> None:
        """Execute adrift travel: random neighbor, jettison cargo, desperate messages."""
        dest_name = self._drift_destination()
        # Drift physically tears the ship out of the system; any attached
        # boarding craft snaps off with it.
        self._tear_free(engine, "The boarding craft tears free as you drift!")
        engine.message_log.add_message("Engines dead. The ship drifts on momentum...", _DRIFT)
        if engine.ship.cargo:
            if self._jettison_cargo(engine, random):
                return
        elif self._damage_hull(
            engine, 1, _DRIFT_DAMAGE_MSGS, "Your ship broke apart drifting through the void.", random
        ):
            return
        engine.message_log.add_message(f"Drifting into {dest_name}...", _DRIFT)
        self._arrive(engine, dest_name)

    def break_away(self, engine: Engine, dest_name: str) -> None:
        """Burn clear of a hard-docked boarding craft and travel to *dest_name* under power.

        Unlike drift the player keeps their heading and pays for the jump, but
        the clamps take hull with them and may shake cargo loose.
        """
        from game.interdiction import BREAK_AWAY_CARGO_LOSS_CHANCE, BREAK_AWAY_HULL_DAMAGE

        if not engine.ship.consume_fuel(self.galaxy.travel_cost(dest_name)):
            engine.message_log.add_message("Not enough fuel.", _RED)
            return
        rng = engine.rng(f"break_away:{dest_name}")
        self._tear_free(engine, "The docking clamps shear away as you burn clear!")
        if self._damage_hull(
            engine,
            BREAK_AWAY_HULL_DAMAGE,
            _BREAK_AWAY_DAMAGE_MSGS,
            "Your ship broke apart tearing free of the boarding craft.",
            rng,
        ):
            return
        if engine.ship.cargo and rng.random() < BREAK_AWAY_CARGO_LOSS_CHANCE and self._jettison_cargo(engine, rng):
            return
        engine.message_log.add_message(f"Traveling to {dest_name}.", _TRAVEL)
        # The pirates here are left behind; nobody is lying in wait at the far end.
        self._arrive(engine, dest_name, interdictable=False)

    def on_render(self, console: Any, engine: Engine) -> None:
        from data.star_types import STAR_TYPES
        from game.helpers import stable_seed
        from game.interdiction import current_interdiction
        from ui.viewport_renderer import render_viewport

        system = self.galaxy.systems[self.galaxy.current_system]
        cw = engine.CONSOLE_WIDTH
        ch = engine.CONSOLE_HEIGHT
        log_h = 8
        log_y = ch - log_h
        ctrl_y = log_y - 2
        content_max_y = ctrl_y - 1
        left_w = 64
        text_width = max(1, left_w - 4)

        # Header
        star_type_name = STAR_TYPES[system.star_type].name if system.star_type in STAR_TYPES else system.star_type
        is_home = system.name == self.galaxy.home_system
        home_tag = " (home)" if is_home else ""
        header_color = (100, 255, 100) if is_home else (255, 255, 100)
        console.print(x=2, y=1, string=f"{system.name} ({star_type_name}){home_tag}", fg=header_color)
        from data.colors import HEADER_SEP

        console.print(x=2, y=2, string="=" * text_width, fg=HEADER_SEP)

        # Star map section (fixed position at top)
        nav_active = self.focus == "navigation"
        nav_header_color = (180, 180, 200) if nav_active else (80, 80, 100)
        console.print(x=2, y=4, string="STAR MAP:", fg=nav_header_color)
        compass_top = 6
        compass_bottom = compass_top + 14
        self._render_compass(console, system, left_w, compass_top, compass_bottom, nav_active)

        # Locations section (below compass, fixed position)
        loc_y = compass_bottom + 1
        loc_active = self.focus == "locations"
        loc_header_color = (180, 180, 200) if loc_active else (80, 80, 100)
        console.print(x=2, y=loc_y, string="LOCATIONS:", fg=loc_header_color)
        loc_start_y = loc_y + 2
        max_locs = min(len(system.locations), max(0, content_max_y - loc_start_y + 1))
        loc_start = max(0, min(self.selected - max_locs + 1, len(system.locations) - max_locs))
        for j in range(max_locs):
            i = loc_start + j
            if i >= len(system.locations):
                break
            loc = system.locations[i]
            y = loc_start_y + j
            prefix = ">" if i == self.selected else " "
            status = "VISITED" if loc.visited else "UNVISITED"
            if loc_active:
                color = (255, 255, 255) if i == self.selected else (140, 140, 140)
            else:
                color = (80, 80, 100)
            text = f"{prefix} {loc.name} ({loc.loc_type}) - {status}"
            if text_width > 3 and len(text) > text_width:
                text = text[: text_width - 3] + "..."
            console.print(x=2, y=y, string=text[:text_width], fg=color)

        # Controls
        if self.focus == "locations":
            ctrl = "[ESC] Quit [C] Cargo [S] Explore Ship [M] Galaxy [TAB] Star Map [UP/DOWN] Select [ENTER] Dock"
        else:
            ctrl = "[ESC] Quit [C] Cargo [S] Explore Ship [M] Galaxy [TAB] Locations [ARROWS] Navigate"
        console.print(x=2, y=ctrl_y, string=ctrl, fg=(80, 80, 80))

        # Viewport: star + starfield
        vp_x = left_w
        vp_w = cw - left_w
        vp_h = ctrl_y
        system_seed = stable_seed(system.name)
        render_viewport(console, vp_x, 0, vp_w, vp_h, system.star_type, system_seed)

        # HUD gauges (top of star map viewport, left-justified, rendered after viewport)
        hud_x = left_w + 1
        hud_y = 0

        if engine.ship:
            _render_gauge(console, hud_x, hud_y, "FUEL", engine.ship.fuel, engine.ship.max_fuel)
            _render_gauge(console, hud_x, hud_y + 1, "HULL", engine.ship.hull, engine.ship.max_hull)

            # Nav unit counter
            nav_count = engine.ship.nav_units
            max_nav = engine.ship.max_nav_units
            if nav_count >= max_nav and self.galaxy.dreadnought_system:
                nav_str = "NAV : LOCKED"
                nav_color = (255, 200, 0)
            else:
                nav_str = f"NAV : {nav_count}/{max_nav}"
                nav_color = (0, 255, 200) if nav_count >= max_nav else (140, 160, 180)
            console.print(x=hud_x, y=hud_y + 2, string=nav_str, fg=nav_color)

        # Interdiction banner — appears below the NAV gauge while a hostile
        # boarding craft is attached to the player ship.
        active = current_interdiction(engine)
        if active is not None and not active.resolved:
            console.print(
                x=hud_x,
                y=hud_y + 4,
                string="*** BEING BOARDED ***",
                fg=(255, 200, 100),
            )

        engine.message_log.render(console, 0, log_y, cw, log_h)

    def _render_compass(self, console: Any, system: Any, left_w: int, top_y: int, max_y: int, active: bool) -> None:
        """Draw compass rose showing connections from current system."""
        conn_map = self._connection_by_direction()
        cx = left_w // 2
        cy = top_y + (max_y - top_y) // 2

        # Draw center node (current system)
        console.print(x=cx, y=cy, string="@", fg=(255, 255, 100) if active else (120, 120, 60))

        edge_color = (100, 200, 255) if active else (50, 80, 100)
        label_color = (180, 220, 255) if active else (60, 80, 100)
        dim_color = (40, 40, 50) if active else (25, 25, 30)

        # Draw dim compass dots for unconnected directions
        for d, cells in _ROSE_LINES.items():
            if d not in conn_map:
                for dx, dy in cells:
                    px, py = cx + dx, cy + dy
                    if 0 <= px < left_w and top_y <= py < max_y:
                        console.print(x=px, y=py, string=".", fg=dim_color)

        # Label row offsets: N/S get their own rows separate from diagonals
        # to prevent overlap with NE/NW and SE/SW respectively.
        _label_dy: dict[tuple[int, int], int] = {
            (0, -1): -6,
            (0, 1): 6,  # N/S: one row beyond diagonals
            (-1, 0): 0,
            (1, 0): 0,  # W/E: same row as center
            (-1, -1): -5,
            (1, -1): -5,  # NW/NE: match line endpoint row
            (-1, 1): 5,
            (1, 1): 5,  # SW/SE: match line endpoint row
        }

        # Draw active connections
        for d, neighbor_name in conn_map.items():
            fuel = self.galaxy.travel_cost(neighbor_name)
            char = _ROSE_CHARS.get(d, "*")
            cells = _ROSE_LINES.get(d, [])
            for dx, dy in cells:
                px, py = cx + dx, cy + dy
                if 0 <= px < left_w and top_y <= py < max_y:
                    console.print(x=px, y=py, string=char, fg=edge_color)

            # Label: each direction gets a dedicated row to avoid overlaps
            label = f"{neighbor_name} ({fuel})"
            ly = cy + _label_dy[d]
            if d[0] > 0:
                # Right side: start past line end
                lx = cx + 10
            elif d[0] < 0:
                # Left side: right-align before line start
                lx = cx - 10 - len(label)
            else:
                # Vertical: center
                lx = cx - len(label) // 2
            lx = max(0, min(lx, left_w - 1))
            if top_y <= ly < max_y:
                label = label[: max(1, left_w - lx)]
                console.print(x=lx, y=ly, string=label, fg=label_color)
