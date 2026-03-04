"""Suit: environment resistances and current resource pools."""
from __future__ import annotations

from typing import Dict


class Suit:
    """Suit stats: resistances (max turns per hazard) and current pools."""

    def __init__(
        self,
        name: str,
        resistances: Dict[str, int],
        defense_bonus: int = 0,
    ) -> None:
        self.name = name
        self.resistances = dict(resistances)
        self.defense_bonus = defense_bonus
        self.current_pools = dict(resistances)

    def refill_pools(self) -> None:
        """Reset all pools to max (e.g. when starting a tactical session)."""
        self.current_pools = dict(self.resistances)


# Predefined suits for the vertical slice
EVA_SUIT = Suit(
    name="EVA Suit",
    resistances={"vacuum": 50, "cold": 10},
    defense_bonus=0,
)

HAZARD_SUIT = Suit(
    name="Hazard Suit",
    resistances={"radiation": 40, "heat": 30},
    defense_bonus=1,
)
