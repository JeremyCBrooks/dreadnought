"""Strategic (star system navigation) state with compass rose starmap."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Tuple

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine
    from world.galaxy import Galaxy

# Compass rose line offsets: direction -> list of (dx, dy) cells from center
# Terminal cells are ~2:1 (tall), so horizontal lines use 2x spacing and
# diagonals step 2 cols per 1 row to look correct.
_ROSE_LINES: Dict[Tuple[int, int], list[Tuple[int, int]]] = {
    (0, -1):  [(0, -1), (0, -2), (0, -3), (0, -4)],
    (0, 1):   [(0, 1), (0, 2), (0, 3), (0, 4)],
    (-1, 0):  [(-2, 0), (-4, 0), (-6, 0), (-8, 0)],
    (1, 0):   [(2, 0), (4, 0), (6, 0), (8, 0)],
    (-1, -1): [(-2, -1), (-4, -2), (-6, -3), (-8, -4)],
    (1, -1):  [(2, -1), (4, -2), (6, -3), (8, -4)],
    (-1, 1):  [(-2, 1), (-4, 2), (-6, 3), (-8, 4)],
    (1, 1):   [(2, 1), (4, 2), (6, 3), (8, 4)],
}

# Characters for compass lines by direction
_ROSE_CHARS: Dict[Tuple[int, int], str] = {
    (0, -1): "|", (0, 1): "|",
    (-1, 0): "-", (1, 0): "-",
    (-1, -1): "\\", (1, -1): "/",
    (-1, 1): "/", (1, 1): "\\",
}


def _direction(sys_a: Any, sys_b: Any) -> Tuple[int, int]:
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

    def _connection_by_direction(self) -> Dict[Tuple[int, int], str]:
        """Map each direction to the connected system name in that direction."""
        system = self.galaxy.systems[self.galaxy.current_system]
        result: Dict[Tuple[int, int], str] = {}
        for neighbor_name in system.connections:
            neighbor = self.galaxy.systems[neighbor_name]
            d = _direction(system, neighbor)
            result[d] = neighbor_name
        return result

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        import tcod.event
        from ui.keys import move_keys, confirm_keys

        key = event.sym
        system = self.galaxy.systems[self.galaxy.current_system]

        # Tab toggles focus
        if key == tcod.event.KeySym.TAB:
            self.focus = "navigation" if self.focus == "locations" else "locations"
            return True

        # Cargo works in either focus
        from ui.keys import is_action
        if is_action("cargo", key):
            from ui.cargo_state import CargoState
            engine.push_state(CargoState())
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
                    self.galaxy.current_system = dest_name
                    self.selected = 0
                    engine.message_log.add_message(
                        f"Traveling to {dest_name}.", (100, 200, 255)
                    )
                return True
            if key in confirm_keys():
                return True

        return False

    def on_render(self, console: Any, engine: Engine) -> None:
        from data.star_types import STAR_TYPES
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
        console.print(x=2, y=1, string=f"STAR SYSTEM: {system.name} ({star_type_name})", fg=(255, 255, 100))
        from ui.colors import HEADER_SEP
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
        max_locs = min(len(system.locations), max(0, content_max_y - loc_start_y))
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
                text = text[:text_width - 3] + "..."
            console.print(x=2, y=y, string=text[:text_width], fg=color)

        # Controls
        if self.focus == "locations":
            ctrl = "[UP/DOWN] Select  [ENTER] Dock  [TAB] Star Map  [C] Cargo  [ESC] Quit"
        else:
            ctrl = "[ARROWS] Navigate  [TAB] Locations  [C] Cargo  [ESC] Quit"
        console.print(x=2, y=ctrl_y, string=ctrl, fg=(80, 80, 80))

        # Viewport: star + starfield
        vp_x = left_w
        vp_w = cw - left_w
        vp_h = ctrl_y
        system_seed = hash(system.name) & 0xFFFFFFFF
        render_viewport(console, vp_x, 0, vp_w, vp_h, system.star_type, system_seed)

        engine.message_log.render(console, 0, log_y, cw, log_h)

    def _render_compass(self, console: Any, system: Any, left_w: int,
                       top_y: int, max_y: int, active: bool) -> None:
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
        _label_dy: Dict[Tuple[int, int], int] = {
            (0, -1): -6, (0, 1): 6,        # N/S: one row beyond diagonals
            (-1, 0): 0, (1, 0): 0,          # W/E: same row as center
            (-1, -1): -5, (1, -1): -5,      # NW/NE: match line endpoint row
            (-1, 1): 5, (1, 1): 5,          # SW/SE: match line endpoint row
        }

        # Draw active connections
        for d, neighbor_name in conn_map.items():
            fuel = system.connections[neighbor_name]
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
                label = label[:max(1, left_w - lx)]
                console.print(x=lx, y=ly, string=label, fg=label_color)
