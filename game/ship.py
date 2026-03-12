"""Ship: player's vessel with fuel, cargo, and scanner quality."""
from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from game.entity import Entity


class Ship:
    """The player's ship — persists across tactical sessions."""

    MAX_NAV_UNITS = 6

    def __init__(
        self,
        fuel: int = 5,
        max_fuel: int = 10,
        scanner_quality: int = 1,
        hull: int = 10,
        max_hull: int = 10,
    ) -> None:
        self.fuel = fuel
        self.max_fuel = max_fuel
        self.cargo: List[Entity] = []
        self.scanner_quality = scanner_quality
        self.nav_units: int = 0
        self.hull = hull
        self.max_hull = max_hull

    def add_cargo(self, item: Entity) -> None:
        """Add an item to the cargo hold."""
        self.cargo.append(item)

    def remove_cargo(self, item: Entity) -> bool:
        """Remove an item from cargo. Returns True if found and removed."""
        if item in self.cargo:
            self.cargo.remove(item)
            return True
        return False
