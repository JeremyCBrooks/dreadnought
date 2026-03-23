"""Game over / victory screen state."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from engine.game_state import State
from ui.colors import DARK_GRAY, HP_GREEN, HP_RED, NEUTRAL

if TYPE_CHECKING:
    from engine.game_state import Engine

FADE_IN_DURATION = 1.0


class GameOverState(State):
    def __init__(self, victory: bool = False, cause: str = "", title: str = "") -> None:
        self.victory = victory
        self.cause = cause
        self.title = title or ("YOU ESCAPED!" if victory else "YOU DIED")
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
    def _fade_color(color: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
        return (int(color[0] * alpha), int(color[1] * alpha), int(color[2] * alpha))

    def ev_key(self, engine: Engine, event: Any) -> bool:
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
        engine.galaxy = None
        engine.reset_to_state(TitleState())
        return True

    def on_render(self, console: Any, engine: Engine) -> None:
        cx = engine.CONSOLE_WIDTH // 2
        cy = engine.CONSOLE_HEIGHT // 2
        alpha = self._alpha()

        title_color = HP_GREEN if self.victory else HP_RED
        title_x = cx - len(self.title) // 2
        console.print(
            x=title_x,
            y=cy - 2,
            string=self.title,
            fg=self._fade_color(title_color, alpha),
        )

        if self.cause:
            console.print(
                x=cx - len(self.cause) // 2,
                y=cy,
                string=self.cause,
                fg=self._fade_color(NEUTRAL, alpha),
            )

        if alpha >= 1.0:
            prompt = "Press Enter to continue"
            console.print(
                x=cx - len(prompt) // 2,
                y=cy + 8,
                string=prompt,
                fg=DARK_GRAY,
            )
