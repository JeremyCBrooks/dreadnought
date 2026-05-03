"""Full-screen galaxy map overlay showing all discovered systems."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine
    from world.galaxy import Galaxy, StarSystem

# Grid-to-screen spacing. _CELL_W must be 2× _CELL_H so diagonals
# at (2 cols, 1 row) per step look ~45 degrees in a 2:1-aspect terminal.
_CELL_W = 8
_CELL_H = 4

# Maximum label length (chars). Must be < _CELL_W to avoid overlapping
# adjacent columns.  Longer names are truncated.
_MAX_LABEL = 3


class GalaxyMapState(State):
    needs_animation = False

    def __init__(self, galaxy: Galaxy) -> None:
        self.galaxy = galaxy
        current = galaxy.systems[galaxy.current_system]
        self.camera_gx = current.gx
        self.camera_gy = current.gy

    def ev_key(self, engine: Engine, event: Any) -> bool:
        import tcod.event

        from ui.keys import cancel_keys, move_keys

        key = event.sym

        if key in cancel_keys():
            engine.pop_state()
            return True

        # 'c' = center on current system
        if key == tcod.event.KeySym.C:
            current = self.galaxy.systems[self.galaxy.current_system]
            self.camera_gx = current.gx
            self.camera_gy = current.gy
            return True

        # Shift+H = center on home system
        if key == tcod.event.KeySym.H and event.mod & tcod.event.Modifier.SHIFT:
            home = self.galaxy.systems[self.galaxy.home_system]
            self.camera_gx = home.gx
            self.camera_gy = home.gy
            return True

        direction = move_keys().get(key)
        if direction:
            dx, dy = direction
            self.camera_gx += dx
            self.camera_gy += dy
            return True

        return False

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def on_render(self, console: Any, engine: Engine) -> None:
        from ui.colors import DIALOG_BG

        cw = engine.CONSOLE_WIDTH
        ch = engine.CONSOLE_HEIGHT
        console.draw_rect(0, 0, cw, ch, ch=32, bg=DIALOG_BG)

        # Header — show current system name in full
        current_name = self.galaxy.current_system
        console.print(x=2, y=1, string=f"GALAXY MAP — {current_name}", fg=(255, 255, 100))
        console.print(
            x=2,
            y=ch - 1,
            string="[ARROWS] Scroll  [C] Center  [Shift+H] Home  [ESC] Back",
            fg=(80, 80, 80),
        )

        # Render bounds
        rx0, ry0 = 2, 3
        rx1, ry1 = cw - 2, ch - 2
        mid_x = (rx0 + rx1) // 2
        mid_y = (ry0 + ry1) // 2

        galaxy = self.galaxy
        home_name = galaxy.home_system

        # --- connections (lines behind nodes) ---
        drawn_edges: set[tuple[str, str]] = set()
        for name, sys in galaxy.systems.items():
            for nb_name in sys.connections:
                edge = (min(name, nb_name), max(name, nb_name))
                if edge in drawn_edges:
                    continue
                drawn_edges.add(edge)
                nb = galaxy.systems[nb_name]
                self._draw_connection(console, sys, nb, mid_x, mid_y, rx0, ry0, rx1, ry1)

        # --- nodes + labels ---
        # Collect label rects first so we can skip overlapping ones.
        label_rects: list[tuple[int, int, int]] = []  # (lx, ly, length)

        for name, sys in galaxy.systems.items():
            sx = mid_x + (sys.gx - self.camera_gx) * _CELL_W
            sy = mid_y + (sys.gy - self.camera_gy) * _CELL_H
            if not (rx0 <= sx < rx1 and ry0 <= sy < ry1):
                continue

            # Node glyph
            if name == current_name:
                char, fg = "@", (255, 255, 100)
            elif name == home_name:
                char, fg = "H", (100, 255, 100)
            elif getattr(galaxy, "dreadnought_system", None) and name == galaxy.dreadnought_system:
                char, fg = "D", (255, 80, 80)
            else:
                char, fg = "*", (150, 150, 200)
            console.print(x=sx, y=sy, string=char, fg=fg)

            # Label
            label = name[:_MAX_LABEL]
            lx = sx - len(label) // 2
            ly = sy + 1
            if not (ry0 <= ly < ry1 and rx0 <= lx and lx + len(label) < rx1):
                continue

            # Check overlap with previously placed labels
            overlaps = False
            for ox, oy, olen in label_rects:
                if oy == ly and not (lx >= ox + olen + 1 or lx + len(label) + 1 <= ox):
                    overlaps = True
                    break
            if overlaps:
                continue

            label_rects.append((lx, ly, len(label)))
            label_color = fg if name == current_name else (100, 100, 130)
            console.print(x=lx, y=ly, string=label, fg=label_color)

    def _draw_connection(
        self,
        console: Any,
        sys_a: StarSystem,
        sys_b: StarSystem,
        mid_x: int,
        mid_y: int,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
    ) -> None:
        """Draw an ASCII line between two systems using direction-aware stepping."""
        ax = mid_x + (sys_a.gx - self.camera_gx) * _CELL_W
        ay = mid_y + (sys_a.gy - self.camera_gy) * _CELL_H
        bx = mid_x + (sys_b.gx - self.camera_gx) * _CELL_W
        by = mid_y + (sys_b.gy - self.camera_gy) * _CELL_H

        dx = bx - ax
        dy = by - ay
        if dx == 0 and dy == 0:
            return

        color = (40, 60, 80)

        if dy == 0:
            # Horizontal — step by x
            sx = 1 if dx > 0 else -1
            for i in range(1, abs(dx)):
                px = ax + i * sx
                if x0 <= px < x1 and y0 <= ay < y1:
                    console.print(x=px, y=ay, string="-", fg=color)
        elif dx == 0:
            # Vertical — step by y
            sy = 1 if dy > 0 else -1
            for i in range(1, abs(dy)):
                py = ay + i * sy
                if x0 <= ax < x1 and y0 <= py < y1:
                    console.print(x=ax, y=py, string="|", fg=color)
        else:
            # Diagonal — step by y, compute x at each row
            char = "\\" if (dx > 0) == (dy > 0) else "/"
            sy = 1 if dy > 0 else -1
            for i in range(1, abs(dy)):
                py = ay + i * sy
                px = ax + round(dx * i / abs(dy))
                if x0 <= px < x1 and y0 <= py < y1:
                    console.print(x=px, y=py, string=char, fg=color)
