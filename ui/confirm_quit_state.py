"""Modal confirmation dialog for quitting the game."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine


class ConfirmQuitState(State):
    """Pushed onto the stack to confirm quit. Y exits, N/ESC returns."""

    def __init__(self, abandon: bool = False) -> None:
        self.abandon = abandon

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        import tcod.event

        key = event.sym
        K = tcod.event.KeySym

        if key == K.y:
            if self.abandon:
                from ui.game_over_state import GameOverState
                engine.switch_state(GameOverState(victory=False, title="MISSION ABANDONED"))
                return True
            raise SystemExit
        if key == K.n or key == K.ESCAPE:
            engine.pop_state()
            return True
        return True  # consume all other keys

    def on_render(self, console: Any, engine: Engine) -> None:
        # Draw previous state underneath
        if len(engine._state_stack) >= 2:
            engine._state_stack[-2].on_render(console, engine)

        cw, ch = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw, bh = 27, 6
        bx = (cw - bw) // 2
        by = (ch - bh) // 2

        from ui.colors import DIALOG_BG, GRAY, HEADER_TITLE
        console.draw_rect(bx, by, bw, bh, ch=32, bg=DIALOG_BG)
        console.print(x=bx + 2, y=by + 1, string="Quit game?", fg=HEADER_TITLE)
        console.print(x=bx + 2, y=by + 3, string="[Y] Yes, exit", fg=GRAY)
        console.print(x=bx + 2, y=by + 4, string="[N] No, stay", fg=GRAY)
