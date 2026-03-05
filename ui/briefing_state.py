"""Briefing screen shown before entering a tactical mission."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine
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
    elif score <= 3:
        return "MODERATE"
    else:
        return "HIGH"



class BriefingState(State):
    """Shows mission intel before entering a location. [C] to continue to loadout."""

    def __init__(self, location: Location, depth: int = 0) -> None:
        self.location = location
        self.depth = depth

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        from ui.keys import confirm_keys, cancel_keys

        key = event.sym

        if key in cancel_keys():
            engine.pop_state()
            return True

        if key in confirm_keys():
            from ui.loadout_state import LoadoutState
            engine.switch_state(LoadoutState(location=self.location, depth=self.depth))
            return True

        return True

    def on_render(self, console: Any, engine: Engine) -> None:
        cw, ch = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw = min(60, cw - 10)
        bh = min(25, ch - 10)
        bx = (cw - bw) // 2
        by = (ch - bh) // 2
        console.draw_rect(bx, by, bw, bh, ch=32, bg=(15, 15, 30))

        console.print(x=bx + 2, y=by + 1, string="=== MISSION BRIEFING ===", fg=(255, 255, 200))

        y = by + 3
        console.print(x=bx + 2, y=y, string=f"Location: {self.location.name}", fg=(200, 200, 255))
        y += 1
        console.print(x=bx + 2, y=y, string=f"Type: {self.location.loc_type}", fg=(180, 180, 200))

        # Compute effective environment: location data + implied hazards
        env = dict(self.location.environment or {})
        from world.loc_profiles import get_profile
        profile = get_profile(self.location.loc_type)
        if profile.generator in ("ship", "standard"):
            env.setdefault("vacuum", 1)

        y += 2
        threat = _threat_level(env, self.depth)
        threat_color = {"LOW": (100, 255, 100), "MODERATE": (255, 255, 100), "HIGH": (255, 100, 100)}
        console.print(x=bx + 2, y=y, string=f"Threat Level: {threat}", fg=threat_color.get(threat, (200, 200, 200)))

        y += 2
        console.print(x=bx + 2, y=y, string="Environmental Hazards:", fg=(180, 180, 200))
        y += 1
        if env:
            for hazard_type, severity in env.items():
                label = hazard_type.replace("_", " ").title()
                console.print(x=bx + 4, y=y, string=f"- {label} (severity: {severity})", fg=(255, 200, 100))
                y += 1
        else:
            console.print(x=bx + 4, y=y, string="None detected", fg=(100, 200, 100))
            y += 1

        console.print(
            x=bx + 2, y=by + bh - 2,
            string="[ENTER] Continue to Loadout  [ESC] Back",
            fg=(100, 100, 100),
        )
