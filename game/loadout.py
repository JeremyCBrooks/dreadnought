"""Loadout: 2 generic equipment slots for mission gear (weapon or tool)."""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from game.entity import Entity


from ui.colors import EQUIP_MSG, NEUTRAL, WARNING

_EQUIPPABLE_TYPES = {"weapon", "scanner"}


def is_equippable(entity: Entity) -> bool:
    """True if the entity is a weapon or tool (scanner) that can go in an equipment slot."""
    if not entity.item:
        return False
    return entity.item.get("type") in _EQUIPPABLE_TYPES


def recalc_melee_power(player: Entity) -> None:
    """Recalculate player melee power from base + equipped melee weapon bonus."""
    base = player.fighter.base_power
    bonus = 0
    if player.loadout:
        for item in player.loadout.all_items():
            if item.item and item.item.get("weapon_class", "melee") == "melee":
                bonus = item.item.get("value", 0)
                break
    player.fighter.power = base + bonus


class Loadout:
    """2 generic equipment slots (weapon or tool)."""

    __slots__ = ("slot1", "slot2")

    def __init__(
        self,
        slot1: Optional[Entity] = None,
        slot2: Optional[Entity] = None,
    ) -> None:
        self.slot1 = slot1
        self.slot2 = slot2

    def all_items(self) -> List[Entity]:
        """Return all non-None items across both slots."""
        return [s for s in (self.slot1, self.slot2) if s is not None]

    def has_item(self, item: Entity) -> bool:
        return item is self.slot1 or item is self.slot2

    def remove_item(self, item: Entity) -> bool:
        """Clear whichever slot holds item. Returns True if found."""
        if self.slot1 is item:
            self.slot1 = None
            return True
        if self.slot2 is item:
            self.slot2 = None
            return True
        return False

    def equip(self, item: Entity) -> Optional[Entity]:
        """Put item in first empty slot. Returns None. Does nothing if both full."""
        if self.slot1 is None:
            self.slot1 = item
            return None
        if self.slot2 is None:
            self.slot2 = item
            return None
        return None

    def unequip(self, item: Entity) -> Optional[Entity]:
        """Remove item from slot and return it. Returns None if not found."""
        if self.slot1 is item:
            self.slot1 = None
            return item
        if self.slot2 is item:
            self.slot2 = None
            return item
        return None

    def is_full(self) -> bool:
        return self.slot1 is not None and self.slot2 is not None

    def get_ranged_weapon(self) -> Optional[Entity]:
        """Return a ranged weapon with ammo from either slot."""
        for s in (self.slot1, self.slot2):
            if (
                s is not None
                and s.item
                and s.item.get("weapon_class") == "ranged"
                and s.item.get("ammo", 0) > 0
            ):
                return s
        return None

    def get_scanner(self) -> Optional[Entity]:
        """Return the first scanner from either slot."""
        for s in (self.slot1, self.slot2):
            if s is not None and s.item and s.item.get("type") == "scanner":
                return s
        return None

    def get_all_scanners(self) -> List[Entity]:
        """Return all scanner items across both slots."""
        return [
            s for s in (self.slot1, self.slot2)
            if s is not None and s.item and s.item.get("type") == "scanner"
        ]

    def items_with_durability(self) -> List[Entity]:
        """Return all loadout items that have a durability stat > 0."""
        result = []
        for item in self.all_items():
            if item.item and item.item.get("durability") is not None and item.item.get("durability", 0) > 0:
                result.append(item)
        return result


def toggle_equip(engine: object, player: Entity, item: Entity) -> None:
    """Equip or unequip *item* on *player*, logging a message.

    If the item is currently equipped, unequip it.  Otherwise equip it
    (if equippable and a slot is free).  Used by both InventoryState and
    CargoState to avoid duplicated equip/unequip logic.
    """
    lo = player.loadout
    if lo and lo.has_item(item):
        lo.unequip(item)
        if player.fighter:
            recalc_melee_power(player)
        engine.message_log.add_message(f"Unequipped {item.name}.", NEUTRAL)
        return

    if not is_equippable(item):
        return

    if lo and not lo.is_full():
        lo.equip(item)
        if player.fighter:
            recalc_melee_power(player)
        engine.message_log.add_message(f"Equipped {item.name}.", EQUIP_MSG)
    elif lo and lo.is_full():
        engine.message_log.add_message(
            "Equipment slots full. Unequip something first.", WARNING
        )
