"""Ship: player's vessel with fuel, cargo, and scanner quality."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.entity import Entity


class Ship:
    """The player's ship — persists across tactical sessions."""

    @staticmethod
    def _max_nav_units() -> int:
        import debug

        return debug.MAX_NAV_UNITS if debug.MAX_NAV_UNITS is not None else 6

    @property
    def max_nav_units(self) -> int:
        return Ship._max_nav_units()

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
        self.cargo: list[Entity] = []
        self.scanner_quality = scanner_quality
        self.nav_units: int = 0
        self.hull = hull
        self.max_hull = max_hull

    def add_cargo(self, item: Entity) -> None:
        """Add an item to the cargo hold."""
        self.cargo.append(item)

    def remove_cargo(self, item: Entity) -> bool:
        """Remove an item from cargo. Returns True if found and removed."""
        try:
            self.cargo.remove(item)
        except ValueError:
            return False
        return True

    def add_fuel(self, amount: int) -> int:
        """Add fuel, clamped at max_fuel. Returns the amount actually added."""
        added = min(amount, self.max_fuel - self.fuel)
        self.fuel += added
        return added

    def consume_fuel(self, cost: int) -> bool:
        """Deduct fuel if sufficient. Returns True if successful, False if insufficient."""
        if self.fuel < cost:
            return False
        self.fuel -= cost
        return True

    def damage_hull(self, amount: int = 1) -> None:
        """Reduce hull by *amount*, clamped at 0."""
        self.hull = max(0, self.hull - amount)

    def repair_hull(self, amount: int) -> int:
        """Repair hull, clamped at max_hull. Returns the amount actually repaired."""
        repaired = min(amount, self.max_hull - self.hull)
        self.hull += repaired
        return repaired

    def add_nav_unit(self) -> bool:
        """Increment nav_units by 1 if below max. Returns True if added."""
        if self.nav_units >= self.max_nav_units:
            return False
        self.nav_units += 1
        return True
