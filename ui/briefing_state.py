"""Briefing screen shown before entering a tactical mission."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State
from ui.colors import (
    DARK_GRAY,
    DIALOG_BG,
    GRAY,
    HEADER_TEXT,
    HEADER_TITLE,
    NEUTRAL,
    PICKUP,
    THREAT_HIGH,
    THREAT_LOW,
    THREAT_MODERATE,
    WARNING,
    WHITE,
)

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.suit import Suit
    from world.galaxy import Location


def _threat_score(env: dict | None, depth: int) -> int:
    """Compute a numeric threat score from environment hazards and depth.

    Scores each hazard's severity, adds depth-based enemy pressure,
    and returns the total.
    """
    score = depth  # deeper systems have tougher enemies
    if env:
        score += sum(env.values())
    return score


def _threat_level(env: dict | None, depth: int) -> str:
    """Return threat level label from location properties."""
    score = _threat_score(env, depth)
    if score <= 1:
        return "LOW"
    if score <= 3:
        return "MODERATE"
    return "HIGH"


class BriefingState(State):
    """Shows mission intel and suit picker before deploying. [ENTER] to deploy."""

    def __init__(self, location: Location, depth: int = 0) -> None:
        self.location = location
        self.depth = depth
        self._suit_index = 0
        self._suits: list[Suit] = []

    def on_enter(self, engine: Engine) -> None:
        from game.suit import EVA_SUIT, HAZARD_SUIT

        self._suits = [EVA_SUIT, HAZARD_SUIT]
        engine.mission_loadout = []
        if engine.suit:
            for i, s in enumerate(self._suits):
                if s.name == engine.suit.name:
                    self._suit_index = i
                    break

    def ev_key(self, engine: Engine, event: Any) -> bool:
        from ui.keys import cancel_keys, confirm_keys, move_keys

        key = event.sym

        if key in cancel_keys():
            engine.pop_state()
            return True

        direction = move_keys().get(key)
        if direction:
            _, dy = direction
            if dy < 0:
                self._suit_index = max(0, self._suit_index - 1)
            elif dy > 0 and self._suits:
                self._suit_index = min(len(self._suits) - 1, self._suit_index + 1)
            return True

        if key in confirm_keys():
            if self._suits:
                engine.suit = self._suits[self._suit_index].copy()
            from ui.tactical_state import TacticalState

            engine.switch_state(TacticalState(location=self.location, depth=self.depth))
            return True

        import tcod.event

        if key == tcod.event.KeySym.c:
            from ui.cargo_state import CargoState

            engine.push_state(CargoState())
            return True

        return True

    def on_render(self, console: Any, engine: Engine) -> None:
        cw, ch = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw = min(65, cw - 10)
        bh = min(25, ch - 10)
        bx = (cw - bw) // 2
        by = (ch - bh) // 2

        console.draw_rect(bx, by, bw, bh, ch=32, bg=DIALOG_BG)

        title = "=== MISSION BRIEFING ==="
        console.print(x=bx + (bw - len(title)) // 2, y=by + 1, string=title, fg=HEADER_TITLE)

        y = by + 3
        console.print(x=bx + 2, y=y, string=f"Location: {self.location.name}", fg=PICKUP)
        y += 1
        console.print(x=bx + 2, y=y, string=f"Type: {self.location.loc_type}", fg=HEADER_TEXT)

        # Environment hazards come directly from the location data
        # (galaxy assigns vacuum to derelicts/asteroids).
        env = dict(self.location.environment or {})

        y += 2
        threat = _threat_level(env, self.depth)
        threat_color = {"LOW": THREAT_LOW, "MODERATE": THREAT_MODERATE, "HIGH": THREAT_HIGH}
        console.print(x=bx + 2, y=y, string=f"Threat Level: {threat}", fg=threat_color.get(threat, NEUTRAL))

        y += 2
        console.print(x=bx + 2, y=y, string="Environmental Hazards:", fg=HEADER_TEXT)
        y += 1
        if env:
            for hazard_type, severity in env.items():
                label = hazard_type.replace("_", " ").title()
                console.print(x=bx + 4, y=y, string=f"- {label} (severity: {severity})", fg=WARNING)
                y += 1
        else:
            console.print(x=bx + 4, y=y, string="None detected", fg=THREAT_LOW)
            y += 1

        # Suit picker
        y += 1
        console.print(x=bx + 2, y=y, string="Select Suit:", fg=HEADER_TEXT)
        y += 1
        for i, suit in enumerate(self._suits):
            prefix = ">" if i == self._suit_index else " "
            color = WHITE if i == self._suit_index else GRAY
            res_str = ", ".join(f"{k}:{v}" for k, v in suit.resistances.items())
            label = f"{prefix} {suit.name} (DEF+{suit.defense_bonus}, {res_str})"
            console.print(x=bx + 4, y=y, string=label[: max(1, bw - 6)], fg=color)
            y += 1

        console.print(
            x=bx + 2,
            y=by + bh - 2,
            string="[ENTER] Deploy  [UP/DOWN] Suit  [C] Cargo  [ESC] Back",
            fg=DARK_GRAY,
        )
