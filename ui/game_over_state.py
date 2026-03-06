"""Game over / victory screen state."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Tuple

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine

FADE_IN_DURATION = 1.0


class GameOverState(State):
    def __init__(self, victory: bool = False, cause: str = "") -> None:
        self.victory = victory
        self.cause = cause
        self._fade_start: float = 0.0

    def on_enter(self, engine: Engine) -> None:
        self._fade_start = time.time()

    @property
    def needs_animation(self) -> bool:
        return (time.time() - self._fade_start) < FADE_IN_DURATION

    def _alpha(self) -> float:
        elapsed = time.time() - self._fade_start
        return min(1.0, elapsed / FADE_IN_DURATION)

    @staticmethod
    def _fade_color(color: Tuple[int, int, int], alpha: float) -> Tuple[int, int, int]:
        return (int(color[0] * alpha), int(color[1] * alpha), int(color[2] * alpha))

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        if self._alpha() < 1.0:
            return True

        from ui.keys import confirm_keys

        if event.sym not in confirm_keys():
            return True
        from ui.title_state import TitleState
        engine._saved_player = None
        engine.area_cache.clear()
        engine.active_effects.clear()
        engine.suit = None
        engine.environment = None
        engine.ship = None
        engine.reset_to_state(TitleState())
        return True

    def on_render(self, console: Any, engine: Engine) -> None:
        cx = engine.CONSOLE_WIDTH // 2
        cy = engine.CONSOLE_HEIGHT // 2
        alpha = self._alpha()

        if self.victory:
            console.print(
                x=cx - 7, y=cy - 2, string="YOU ESCAPED!",
                fg=self._fade_color((0, 255, 0), alpha),
            )
            console.print(
                x=cx - 17, y=cy,
                string="You made it back to your ship alive.",
                fg=self._fade_color((200, 200, 200), alpha),
            )
        else:
            console.print(
                x=cx - 4, y=cy - 2, string="YOU DIED",
                fg=self._fade_color((255, 0, 0), alpha),
            )
            if self.cause:
                cause_x = cx - len(self.cause) // 2
                console.print(
                    x=cause_x, y=cy, string=self.cause,
                    fg=self._fade_color((200, 200, 200), alpha),
                )

        if alpha >= 1.0:
            console.print(
                x=cx - 13, y=cy + 8,
                string="Press Enter to continue",
                fg=(100, 100, 100),
            )
