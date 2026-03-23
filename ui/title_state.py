"""Title screen state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State
from ui.colors import DARK_GRAY

if TYPE_CHECKING:
    from engine.game_state import Engine

# Title screen text and colors
_TITLE = "D R E A D N O U G H T"
_SEPARATOR = "_ _ _ _ _ _ _ _ _ _ _"
_TAGLINE = "A roguelike in the void"
_PROMPT = "Press any key to begin"
_QUIT_HINT = "[ESC] to quit"

_TITLE_COLOR = (180, 180, 255)
_SEPARATOR_COLOR = (80, 80, 140)
_TAGLINE_COLOR = (120, 120, 170)
_QUIT_HINT_COLOR = (70, 70, 70)


def _center_x(width: int, text: str) -> int:
    """Return x position to horizontally center *text* in *width* columns."""
    return width // 2 - len(text) // 2


class TitleState(State):
    def ev_key(self, engine: Engine, event: Any) -> bool:
        from ui.keys import cancel_keys

        if event.sym in cancel_keys():
            return False

        from game.ship import Ship
        from ui.strategic_state import StrategicState
        from world.galaxy import Galaxy

        galaxy = Galaxy()
        engine.ship = Ship()
        engine.galaxy = galaxy
        import debug

        debug.seed_ship_cargo(engine)
        engine.switch_state(StrategicState(galaxy))
        return True

    def on_render(self, console: Any, engine: Engine) -> None:
        w = engine.CONSOLE_WIDTH
        cy = engine.CONSOLE_HEIGHT // 2

        console.print(x=_center_x(w, _TITLE), y=cy - 10, string=_TITLE, fg=_TITLE_COLOR)
        console.print(x=_center_x(w, _SEPARATOR), y=cy - 8, string=_SEPARATOR, fg=_SEPARATOR_COLOR)
        console.print(x=_center_x(w, _TAGLINE), y=cy - 4, string=_TAGLINE, fg=_TAGLINE_COLOR)
        console.print(x=_center_x(w, _PROMPT), y=cy + 2, string=_PROMPT, fg=DARK_GRAY)
        console.print(x=_center_x(w, _QUIT_HINT), y=cy + 4, string=_QUIT_HINT, fg=_QUIT_HINT_COLOR)
