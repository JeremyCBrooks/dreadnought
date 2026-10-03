"""Strategic (star system navigation) state with compass rose starmap."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from data.colors import (
    CONSOLE_FRAME,
    CONSOLE_IDLE,
    CONSOLE_LABEL,
    FOCUS_MARKER,
    HEADER_SEP,
    HEADER_TEXT,
    LOCATION_NAME,
    LOCATION_UNVISITED,
    LOCATION_VISITED,
    WARNING,
    WHITE,
    Color,
)
from engine.game_state import State
from ui.helm_console import Gauge, KeyHint, Span, gauge_spans, keycap_spans, print_spans, ratio_color, spans_width

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


# Key hints on the dash: always-available keys, then the ones that follow focus.
_GLOBAL_KEYS: tuple[KeyHint, ...] = (KeyHint("C", "Cargo"), KeyHint("S", "Ship"), KeyHint("M", "Galaxy"))
_FOCUS_KEYS: dict[str, tuple[KeyHint, ...]] = {
    "locations": (KeyHint("Tab", "Star Map"), KeyHint("↑↓", "Select"), KeyHint("Enter", "Dock")),
    "navigation": (KeyHint("Tab", "Locations"), KeyHint("Arrows", "Navigate")),
}
_QUIT_KEYS: tuple[KeyHint, ...] = (KeyHint("Esc", "Quit"),)

_NAV_LOCKED: Color = (255, 200, 0)
_NAV_FULL: Color = (0, 255, 200)
_NAV_PARTIAL: Color = (140, 160, 180)

_MARGIN = 2
_GAUGE_GAP = 2
_COLUMN_GAP = "   "
_STATUS_LABELS: dict[bool, str] = {True: "visited", False: "unvisited"}


@dataclass(frozen=True)
class HelmLayout:
    """Where the helm's parts sit: console on the left, window on the right, dash beneath both."""

    width: int
    height: int
    left_w: int = 64
    log_h: int = 8

    @property
    def log_y(self) -> int:
        return self.height - self.log_h

    @property
    def keys_y(self) -> int:
        """Key hints, with a blank row left between them and the message log."""
        return self.log_y - 2

    @property
    def sill_y(self) -> int:
        return self.keys_y - 1

    @property
    def gauge_y(self) -> int:
        """Instruments are set into the sill itself."""
        return self.sill_y

    @property
    def strut_x(self) -> int:
        return self.left_w - 1

    @property
    def viewport_x(self) -> int:
        return self.left_w

    @property
    def viewport_w(self) -> int:
        return self.width - self.left_w

    @property
    def viewport_h(self) -> int:
        return self.sill_y

    @property
    def text_width(self) -> int:
        return max(1, self.left_w - 2 * _MARGIN)

    @property
    def right_edge(self) -> int:
        return self.width - _MARGIN


def helm_layout(width: int, height: int) -> HelmLayout:
    """Layout of the helm screen for a console of the given size."""
    return HelmLayout(width, height)


def _fit(text: str, width: int) -> str:
    """Pad *text* to *width*, or cut it with an ellipsis when it is too long."""
    if len(text) > width:
        text = text[: max(0, width - 3)] + "..." if width > 3 else text[:width]
    return text.ljust(width)


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
                    # first. Drift (fuel=0 path) tears free unasked - see _drift().
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
            from game.interdiction import docking_alert

            docked = self.galaxy.arrive_at(dest_name, ship=engine.ship, rng=engine.rng(f"interdiction:{dest_name}"))
            if docked is not None:
                engine.message_log.add_message(docking_alert(docked), WARNING)
        else:
            self.galaxy.arrive_at(dest_name)
        self.selected = 0
        self._check_victory(engine)

    def _attached_interdiction(self) -> Any | None:
        """The unresolved interdiction holding the ship in this system, if any."""
        source = self.galaxy.systems[self.galaxy.current_system]
        active = getattr(source, "interdiction", None)
        return active if active is not None and not active.resolved else None

    def _tear_free(self, engine: Engine, message: str) -> tuple[int, int] | None:
        """Snap any attached boarding craft off: resolve it and restore the original ship map.

        Returns where it had clamped on (ship coordinates), if that is known.
        """
        active = self._attached_interdiction()
        if active is None:
            return None
        from game.interdiction import restore_original_ship_map

        active.resolve()
        restore_original_ship_map(active, engine.ship)
        engine.message_log.add_message(message, WARNING)
        return active.native_attach_point()

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

    def _damage_hull(
        self,
        engine: Engine,
        amount: int,
        messages: list[str],
        cause: str,
        rng: Any,
        near: tuple[int, int] | None = None,
    ) -> bool:
        """Take *amount* hull damage, holing the hull closest to *near* when given.

        Returns True if the ship broke apart (*cause* ends the game).
        """
        engine.ship.damage_hull(amount, rng=rng, near=near)
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
        clamp_point = self._tear_free(engine, "The docking clamps shear away as you burn clear!")
        if self._damage_hull(
            engine,
            BREAK_AWAY_HULL_DAMAGE,
            _BREAK_AWAY_DAMAGE_MSGS,
            "Your ship broke apart tearing free of the boarding craft.",
            rng,
            near=clamp_point,
        ):
            return
        if engine.ship.cargo and rng.random() < BREAK_AWAY_CARGO_LOSS_CHANCE and self._jettison_cargo(engine, rng):
            return
        engine.message_log.add_message(f"Traveling to {dest_name}.", _TRAVEL)
        # The pirates here are left behind; nobody is lying in wait at the far end.
        self._arrive(engine, dest_name, interdictable=False)

    def on_render(self, console: Any, engine: Engine) -> None:
        from game.helpers import stable_seed
        from ui.viewport_renderer import render_viewport

        system = self.galaxy.systems[self.galaxy.current_system]
        layout = helm_layout(engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT)

        self._render_header(console, system, layout)

        # Star map section (fixed position at top)
        nav_active = self.focus == "navigation"
        self._render_section_header(console, 4, "STAR MAP", nav_active)
        compass_top = 6
        compass_bottom = compass_top + 14
        self._render_compass(console, system, layout.left_w, compass_top, compass_bottom, nav_active)

        # Locations section (below compass, fixed position)
        loc_y = compass_bottom + 1
        loc_active = self.focus == "locations"
        self._render_section_header(console, loc_y, "LOCATIONS", loc_active)
        self._render_locations(console, system, layout, loc_y + 2, loc_active)

        # Window: star + starfield, untouched by any text
        render_viewport(
            console,
            layout.viewport_x,
            0,
            layout.viewport_w,
            layout.viewport_h,
            system.star_type,
            stable_seed(system.name),
        )

        self._render_frame(console, layout)
        self._render_dash(console, engine, layout)

        engine.message_log.render(console, 0, layout.log_y, layout.width, layout.log_h)

    def _render_header(self, console: Any, system: Any, layout: HelmLayout) -> None:
        """System name and star type over a thin rule."""
        from data.star_types import STAR_TYPES

        star_type_name = STAR_TYPES[system.star_type].name if system.star_type in STAR_TYPES else system.star_type
        is_home = system.name == self.galaxy.home_system
        header_color = (100, 255, 100) if is_home else (255, 255, 100)
        spans: list[Span] = [(system.name, header_color), (f" · {star_type_name}", CONSOLE_LABEL)]
        if is_home:
            spans.append((" · home", header_color))
        print_spans(console, _MARGIN, 1, spans)
        console.print(x=_MARGIN, y=2, string="─" * layout.text_width, fg=HEADER_SEP)

    @staticmethod
    def _render_section_header(console: Any, y: int, title: str, active: bool) -> None:
        """Section title; the one holding focus is lit and flagged in the margin."""
        if active:
            console.print(x=0, y=y, string="▌", fg=FOCUS_MARKER)
        console.print(x=_MARGIN, y=y, string=title, fg=HEADER_TEXT if active else CONSOLE_IDLE)

    def _render_locations(self, console: Any, system: Any, layout: HelmLayout, top_y: int, active: bool) -> None:
        """List the system's locations as aligned name / type / status columns."""
        locations = system.locations
        if not locations:
            return
        type_w = max(len(loc.loc_type) for loc in locations)
        status_w = max(len(label) for label in _STATUS_LABELS.values())
        cursor_w = 2
        room = layout.text_width - cursor_w - type_w - status_w - 2 * len(_COLUMN_GAP)
        name_w = max(1, min(max(len(loc.name) for loc in locations), room))

        max_locs = min(len(locations), max(0, layout.sill_y - top_y))
        first = max(0, min(self.selected - max_locs + 1, len(locations) - max_locs))
        for row, loc in enumerate(locations[first : first + max_locs]):
            selected = first + row == self.selected
            if active:
                name_color = WHITE if selected else LOCATION_NAME
                type_color = CONSOLE_LABEL
                status_color = LOCATION_VISITED if loc.visited else LOCATION_UNVISITED
            else:
                name_color = type_color = status_color = CONSOLE_IDLE
            spans: list[Span] = [
                ("► " if selected else "  ", FOCUS_MARKER if active else CONSOLE_IDLE),
                (_fit(loc.name, name_w), name_color),
                (_COLUMN_GAP + _fit(loc.loc_type, type_w), type_color),
                (_COLUMN_GAP + _STATUS_LABELS[bool(loc.visited)], status_color),
            ]
            print_spans(console, _MARGIN, top_y + row, spans)

    @staticmethod
    def _render_frame(console: Any, layout: HelmLayout) -> None:
        """One strut between console and window, and a sill beneath them both."""
        for y in range(layout.sill_y):
            console.print(x=layout.strut_x, y=y, string="│", fg=CONSOLE_FRAME)
        console.print(x=0, y=layout.sill_y, string="─" * layout.width, fg=CONSOLE_FRAME)
        console.print(x=layout.strut_x, y=layout.sill_y, string="┴", fg=CONSOLE_FRAME)

    def _gauges(self, engine: Engine) -> list[Gauge]:
        """The ship's instruments, left to right."""
        ship = engine.ship
        if not ship:
            return []
        nav_full = ship.nav_units >= ship.max_nav_units
        locked = nav_full and bool(self.galaxy.dreadnought_system)
        if locked:
            nav_color = _NAV_LOCKED
        else:
            nav_color = _NAV_FULL if nav_full else _NAV_PARTIAL
        return [
            Gauge("FUEL", ship.fuel, ship.max_fuel, ratio_color(ship.fuel / ship.max_fuel if ship.max_fuel else 0)),
            Gauge("HULL", ship.hull, ship.max_hull, ratio_color(ship.hull / ship.max_hull if ship.max_hull else 0)),
            Gauge(
                "NAV",
                ship.nav_units,
                ship.max_nav_units,
                nav_color,
                readout="LOCKED" if locked else None,
                width=min(Gauge.width, max(1, ship.max_nav_units)),
            ),
        ]

    def _render_dash(self, console: Any, engine: Engine, layout: HelmLayout) -> None:
        """The dash under the window: instruments and alerts, then the keys that work here."""
        from game.interdiction import current_interdiction

        # Instruments break the sill under the window, each padded clear of the rule.
        pad: Span = (" ", CONSOLE_FRAME)
        x = layout.viewport_x + _GAUGE_GAP
        for gauge in self._gauges(engine):
            x = print_spans(console, x, layout.gauge_y, [pad, *gauge_spans(gauge), pad]) + _GAUGE_GAP

        # Alert while a hostile boarding craft is attached to the player ship.
        active = current_interdiction(engine)
        if active is not None and not active.resolved:
            alert = " ‼ BEING BOARDED "
            console.print(x=layout.right_edge - len(alert.rstrip()), y=layout.gauge_y, string=alert, fg=WARNING)

        print_spans(console, _MARGIN, layout.keys_y, keycap_spans([_GLOBAL_KEYS, _FOCUS_KEYS[self.focus]]))
        quit_spans = keycap_spans([_QUIT_KEYS])
        print_spans(console, layout.right_edge - spans_width(quit_spans), layout.keys_y, quit_spans)

    def _render_compass(self, console: Any, system: Any, left_w: int, top_y: int, max_y: int, active: bool) -> None:
        """Draw compass rose showing connections from current system."""
        conn_map = self._connection_by_direction()
        cx = left_w // 2
        left_w -= 1  # the last column belongs to the strut
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
