"""Title screen state."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine


class TitleState(State):
    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        import tcod.event

        if event.sym == tcod.event.KeySym.ESCAPE:
            return False

        from world.galaxy import Galaxy
        from ui.strategic_state import StrategicState
        from game.ship import Ship

        galaxy = Galaxy()
        engine.ship = Ship()
        engine.switch_state(StrategicState(galaxy))
        return True

    def on_render(self, console: Any, engine: Engine) -> None:
        w = engine.CONSOLE_WIDTH
        h = engine.CONSOLE_HEIGHT
        cy = h // 2

        console.print(
            x=w // 2 - 13, y=cy - 10,
            string="D R E A D N O U G H T",
            fg=(180, 180, 255),
        )
        console.print(
            x=w // 2 - 13, y=cy - 8,
            string="_ _ _ _ _ _ _ _ _ _ _",
            fg=(80, 80, 140),
        )
        console.print(
            x=w // 2 - 12, y=cy - 4,
            string="A roguelike in the void",
            fg=(120, 120, 170),
        )
        console.print(
            x=w // 2 - 12, y=cy + 2,
            string="Press any key to begin",
            fg=(100, 100, 100),
        )
        console.print(
            x=w // 2 - 8, y=cy + 4,
            string="[ESC] to quit",
            fg=(70, 70, 70),
        )
