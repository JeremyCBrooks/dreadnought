"""Modal yes/no dialog shared by every confirmation prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine

type DialogLine = tuple[str, tuple[int, int, int]]


class ConfirmDialogState(State):
    """Pushed onto the stack to confirm an action. Y confirms, N/ESC returns.

    Subclasses set the labels and implement ``on_confirm``; ``body`` adds
    explanatory lines between the title and the choices.
    """

    title: str = ""
    confirm_label: str = "[Y] Yes"
    cancel_label: str = "[N] No, stay"
    min_width: int = 27

    def body(self, engine: Engine) -> list[DialogLine]:
        """Lines of (text, colour) shown under the title."""
        return []

    def on_confirm(self, engine: Engine) -> None:
        raise NotImplementedError

    def ev_key(self, engine: Engine, event: Any) -> bool:
        import tcod.event

        key = event.sym
        K = tcod.event.KeySym

        if key == K.Y:
            self.on_confirm(engine)
        elif key == K.N or key == K.ESCAPE:
            engine.pop_state()
        return True  # consume all other keys

    def on_render(self, console: Any, engine: Engine) -> None:
        # Draw previous state underneath
        below = engine.state_below(self)
        if below is not None:
            below.on_render(console, engine)

        from data.colors import DIALOG_BG, GRAY, HEADER_TITLE

        body = self.body(engine)
        choices: list[DialogLine] = [(self.confirm_label, GRAY), (self.cancel_label, GRAY)]
        # Title, blank, body, blank, choices — the body and its blank drop out when empty.
        rows: list[DialogLine | None] = [(self.title, HEADER_TITLE), None]
        if body:
            rows += [*body, None]
        rows += choices

        con_w, con_h = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw = max(self.min_width, max(len(row[0]) for row in rows if row) + 4)
        bh = len(rows) + 2
        bx = (con_w - bw) // 2
        by = (con_h - bh) // 2

        console.draw_rect(bx, by, bw, bh, ch=32, bg=DIALOG_BG)
        for offset, row in enumerate(rows):
            if row is not None:
                console.print(x=bx + 2, y=by + 1 + offset, string=row[0], fg=row[1])
