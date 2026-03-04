"""Environment hazard system: per-turn resource drain and damage."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Engine

# Environment types that modify gameplay but don't deal damage per tick.
NON_DAMAGING_HAZARDS = {"low_gravity"}


def has_low_gravity(engine: Engine) -> bool:
    """Return True if the current environment has active low gravity."""
    env = getattr(engine, "environment", None)
    if not env:
        return False
    return env.get("low_gravity", 0) > 0


def apply_environment_tick(engine: Engine) -> None:
    """
    Apply one turn of environment effects.
    For each active hazard: decrement suit pool if resistant; if pool 0 or no resistance, deal 1 HP.
    """
    if not engine.player or not engine.player.fighter:
        return
    env = engine.environment
    suit = engine.suit
    if not env or not suit:
        return

    for hazard_type, severity in env.items():
        if hazard_type in NON_DAMAGING_HAZARDS:
            continue
        if severity <= 0:
            continue
        max_turns = suit.resistances.get(hazard_type, 0)
        current = suit.current_pools.get(hazard_type, 0)

        if max_turns > 0 and current > 0:
            import debug
            if not debug.DISABLE_OXYGEN:
                suit.current_pools[hazard_type] = current - 1
            continue
        # No resistance or pool depleted: deal 1 HP per turn
        import debug
        if debug.GOD_MODE:
            continue
        engine.player.fighter.hp -= 1
        if engine.player.fighter.hp < 0:
            engine.player.fighter.hp = 0
        engine.message_log.add_message(
            f"WARNING: {hazard_type.replace('_', ' ').title()}! Taking damage!",
            (255, 100, 100),
        )
