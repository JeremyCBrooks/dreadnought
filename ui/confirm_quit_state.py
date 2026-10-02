"""Modal confirmation dialog for quitting the game."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.confirm_dialog import ConfirmDialogState

if TYPE_CHECKING:
    from engine.game_state import Engine


class ConfirmQuitState(ConfirmDialogState):
    """Pushed onto the stack to confirm quit. Y exits, N/ESC returns."""

    def __init__(self, abandon: bool = False) -> None:
        self.abandon = abandon
        self.title = "Abandon mission?" if abandon else "Quit game?"
        self.confirm_label = "[Y] Yes, abandon" if abandon else "[Y] Yes, exit"

    def on_confirm(self, engine: Engine) -> None:
        if self.abandon:
            from ui.game_over_state import GameOverState

            engine.switch_state(GameOverState(victory=False, title="MISSION ABANDONED"))
            return
        if engine.on_quit:
            engine.on_quit()
            return
        raise SystemExit
