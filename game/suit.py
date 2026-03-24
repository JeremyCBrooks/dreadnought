"""Suit: environment resistances and current resource pools."""

from __future__ import annotations


class Suit:
    """Suit stats: resistances (max turns per hazard) and current pools."""

    DRAIN_INTERVAL: int = 4  # drain 1 unit every N turns

    def __init__(
        self,
        name: str,
        resistances: dict[str, int],
        defense_bonus: int = 0,
    ) -> None:
        self.name = name
        self.resistances = dict(resistances)
        self.defense_bonus = defense_bonus
        self.current_pools = dict(resistances)
        self._drain_ticks: dict[str, int] = {}

    def __repr__(self) -> str:
        return f"Suit({self.name!r}, {self.resistances}, defense_bonus={self.defense_bonus})"

    def copy(self) -> Suit:
        """Return an independent copy preserving current state."""
        suit = Suit(self.name, self.resistances, self.defense_bonus)
        suit.current_pools = dict(self.current_pools)
        suit._drain_ticks = dict(self._drain_ticks)
        return suit

    def has_protection(self, hazard_type: str) -> bool:
        """Return True if the suit can still absorb *hazard_type*."""
        return self.resistances.get(hazard_type, 0) > 0 and self.current_pools.get(hazard_type, 0) > 0

    def drain_pool(self, hazard_type: str) -> bool:
        """Attempt to drain one tick of *hazard_type* resistance.

        Returns True if the pool absorbed the hazard (no HP damage needed),
        False if the pool is depleted or the suit has no resistance.
        """
        if not self.has_protection(hazard_type):
            return False
        ticks = self._drain_ticks.get(hazard_type, 0) + 1
        if ticks >= self.DRAIN_INTERVAL:
            self.current_pools[hazard_type] -= 1
            ticks = 0
        self._drain_ticks[hazard_type] = ticks
        return True

    def refill_pools(self) -> None:
        """Reset all pools to max (e.g. when starting a tactical session)."""
        self.current_pools = dict(self.resistances)
        self._drain_ticks.clear()


# Predefined suits
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
