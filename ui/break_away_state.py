"""Modal confirmation dialog for tearing free of a hard-docked boarding craft."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.confirm_dialog import ConfirmDialogState, DialogLine

if TYPE_CHECKING:
    from engine.game_state import Engine
    from ui.strategic_state import StrategicState


class BreakAwayState(ConfirmDialogState):
    """Pushed when the player navigates while hard-docked. Y breaks away, N/ESC stays."""

    title = "HARD-DOCKED"
    confirm_label = "[Y] Break away"

    def __init__(self, strategic: StrategicState, dest_name: str) -> None:
        self.strategic = strategic
        self.dest_name = dest_name

    def body(self, engine: Engine) -> list[DialogLine]:
        from data.colors import GRAY, HP_RED, HP_YELLOW
        from game.interdiction import BREAK_AWAY_HULL_DAMAGE

        ship = engine.ship
        hull_after = max(0, ship.hull - BREAK_AWAY_HULL_DAMAGE)
        lines: list[DialogLine] = [
            ("A hostile ship is clamped to your airlock.", GRAY),
            (f"Breaking away to {self.dest_name} will tear the hull", GRAY),
            (f"(-{BREAK_AWAY_HULL_DAMAGE}, leaving {hull_after}/{ship.max_hull}) and may rip cargo loose.", GRAY),
        ]
        if hull_after <= 0:
            lines.append(("THIS WILL DESTROY YOUR SHIP.", HP_RED))
        if any(c.item and c.item.get("type") == "dreadnought_core" for c in ship.cargo):
            lines.append(("The Dreadnought core could be lost.", HP_YELLOW))
        return lines

    def on_confirm(self, engine: Engine) -> None:
        engine.pop_state()
        self.strategic.break_away(engine, self.dest_name)
