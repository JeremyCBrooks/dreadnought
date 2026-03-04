"""Strategic (star system navigation) state."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine
    from world.galaxy import Galaxy

class StrategicState(State):
    def __init__(self, galaxy: Galaxy) -> None:
        self.galaxy = galaxy
        self.selected = 0

    def on_enter(self, engine: Engine) -> None:
        engine.message_log.add_message("You are aboard your ship.", (180, 180, 220))

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        import tcod.event

        key = event.sym
        system = self.galaxy.systems[self.galaxy.current_system]

        if key in (tcod.event.KeySym.UP, tcod.event.KeySym.k):
            self.selected = max(0, self.selected - 1)
            return True
        if key in (tcod.event.KeySym.DOWN, tcod.event.KeySym.j):
            self.selected = min(len(system.locations) - 1, self.selected + 1)
            return True

        if key in (tcod.event.KeySym.LEFT, tcod.event.KeySym.h):
            connected = list(system.connections.keys())
            if connected:
                self.galaxy.current_system = connected[0]
                self.selected = 0
                engine.message_log.add_message(
                    f"Traveling to {self.galaxy.current_system}.", (100, 200, 255)
                )
            return True
        if key in (tcod.event.KeySym.RIGHT, tcod.event.KeySym.l):
            connected = list(system.connections.keys())
            if connected:
                self.galaxy.current_system = connected[-1]
                self.selected = 0
                engine.message_log.add_message(
                    f"Traveling to {self.galaxy.current_system}.", (100, 200, 255)
                )
            return True

        if key == tcod.event.KeySym.RETURN:
            if not system.locations:
                return True
            loc = system.locations[self.selected]
            loc.visited = True
            engine.message_log.add_message(f"Docking at {loc.name}...")
            from ui.briefing_state import BriefingState
            engine.push_state(BriefingState(location=loc, depth=system.depth))
            return True

        return False

    def on_render(self, console: Any, engine: Engine) -> None:
        system = self.galaxy.systems[self.galaxy.current_system]
        cw = engine.CONSOLE_WIDTH
        ch = engine.CONSOLE_HEIGHT
        log_h = 8
        log_y = ch - log_h
        ctrl_y = log_y - 2
        content_max_y = ctrl_y - 1
        text_width = max(1, cw - 4)
        loc_start_y = 6
        # Reserve room for "CONNECTED SYSTEMS" (1) + blank (1) + connections
        available_lines = max(0, content_max_y - loc_start_y - 2)
        max_locs = min(len(system.locations), max(0, available_lines - 1))  # at least 1 line for connections
        max_conns = max(0, available_lines - max_locs)

        console.print(x=2, y=1, string=f"STAR SYSTEM: {system.name}", fg=(255, 255, 100))
        console.print(x=2, y=2, string="=" * max(1, cw - 4), fg=(60, 60, 80))

        console.print(x=2, y=4, string="LOCATIONS:", fg=(180, 180, 200))
        # Scroll so selected location is visible
        loc_start = max(0, min(self.selected - max_locs + 1, len(system.locations) - max_locs))
        loc_start = max(0, min(loc_start, len(system.locations) - max_locs))
        for j in range(max_locs):
            i = loc_start + j
            if i >= len(system.locations):
                break
            loc = system.locations[i]
            y = loc_start_y + j
            prefix = ">" if i == self.selected else " "
            status = "VISITED" if loc.visited else "UNVISITED"
            color = (255, 255, 255) if i == self.selected else (140, 140, 140)
            text = f"{prefix} {loc.name} ({loc.loc_type}) - {status}"
            if len(text) > text_width:
                text = text[: text_width - 3] + "..."
            console.print(x=2, y=y, string=text, fg=color)

        y = loc_start_y + max_locs + 2
        console.print(x=2, y=y, string="CONNECTED SYSTEMS:", fg=(180, 180, 200))
        for i, (name, fuel) in enumerate(system.connections.items()):
            if i >= max_conns:
                break
            y += 1
            text = f"{name} (fuel: {fuel})"
            if len(text) > text_width - 2:
                text = text[: text_width - 5] + "..."
            console.print(x=4, y=y, string=text, fg=(100, 200, 255))

        console.print(
            x=2, y=ctrl_y,
            string="[UP/DOWN] Select  [LEFT/RIGHT] System  [ENTER] Dock  [ESC] Quit",
            fg=(80, 80, 80),
        )

        engine.message_log.render(console, 0, log_y, cw, log_h)
