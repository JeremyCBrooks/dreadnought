"""Game over / victory screen state."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine


class GameOverState(State):
    def __init__(self, victory: bool = False) -> None:
        self.victory = victory

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        import tcod.event

        if event.sym != tcod.event.KeySym.RETURN:
            return True
        from ui.title_state import TitleState
        engine._saved_player = None
        engine.area_cache.clear()
        engine.active_effects.clear()
        engine.suit = None
        engine.environment = None
        engine.ship = None
        engine._pending_loadout = None
        # Clear entire stack to prevent stale states accumulating across restarts
        while engine._state_stack:
            engine._state_stack.pop().on_exit(engine)
        engine._state_stack.append(TitleState())
        engine._state_stack[-1].on_enter(engine)
        return True

    def on_render(self, console: Any, engine: Engine) -> None:
        cx = engine.CONSOLE_WIDTH // 2
        cy = engine.CONSOLE_HEIGHT // 2

        if self.victory:
            console.print(x=cx - 7, y=cy - 2, string="YOU ESCAPED!", fg=(0, 255, 0))
            console.print(
                x=cx - 17, y=cy,
                string="You made it back to your ship alive.",
                fg=(200, 200, 200),
            )
        else:
            console.print(x=cx - 4, y=cy - 2, string="YOU DIED", fg=(255, 0, 0))

        console.print(
            x=cx - 13, y=cy + 8,
            string="Press Enter to continue",
            fg=(100, 100, 100),
        )
