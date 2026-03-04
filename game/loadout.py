"""Loadout: typed equipment slots for mission gear."""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from game.entity import Entity


class SlotType(Enum):
    WEAPON = "weapon"
    TOOL = "tool"
    CONSUMABLE = "consumable"


ITEM_TYPE_TO_SLOT = {
    "weapon": SlotType.WEAPON,
    "scanner": SlotType.TOOL,
    "heal": SlotType.CONSUMABLE,
    "repair": SlotType.CONSUMABLE,
    "o2": SlotType.CONSUMABLE,
}


def item_slot_type(entity: Entity) -> Optional[SlotType]:
    """Classify an item entity into a slot type, or None if not equippable."""
    if not entity.item:
        return None
    return ITEM_TYPE_TO_SLOT.get(entity.item.get("type"))


class Loadout:
    """4 typed equipment slots: weapon, tool, consumable1, consumable2."""

    __slots__ = ("weapon", "tool", "consumable1", "consumable2")

    def __init__(
        self,
        weapon: Optional[Entity] = None,
        tool: Optional[Entity] = None,
        consumable1: Optional[Entity] = None,
        consumable2: Optional[Entity] = None,
    ) -> None:
        self.weapon = weapon
        self.tool = tool
        self.consumable1 = consumable1
        self.consumable2 = consumable2

    def all_items(self) -> List[Entity]:
        """Return all non-None items across all slots."""
        return [s for s in (self.weapon, self.tool, self.consumable1, self.consumable2) if s is not None]

    def has_item(self, item: Entity) -> bool:
        return item in (self.weapon, self.tool, self.consumable1, self.consumable2)

    def remove_item(self, item: Entity) -> bool:
        """Clear whichever slot holds item. Returns True if found."""
        for attr in ("weapon", "tool", "consumable1", "consumable2"):
            if getattr(self, attr) is item:
                setattr(self, attr, None)
                return True
        return False

    def use_consumable(self, item: Entity) -> bool:
        """Clear a consumable slot holding item. Returns True if found."""
        if self.consumable1 is item:
            self.consumable1 = None
            return True
        if self.consumable2 is item:
            self.consumable2 = None
            return True
        return False

    def get_ranged_weapon(self) -> Optional[Entity]:
        """Return the weapon slot item if it's a ranged weapon with ammo."""
        w = self.weapon
        if (
            w is not None
            and w.item
            and w.item.get("weapon_class") == "ranged"
            and w.item.get("ammo", 0) > 0
        ):
            return w
        return None

    def get_scanner(self) -> Optional[Entity]:
        """Return the tool slot item if it's a scanner."""
        t = self.tool
        if t is not None and t.item and t.item.get("type") == "scanner":
            return t
        return None

    def items_with_durability(self) -> List[Entity]:
        """Return all loadout items that have a durability stat > 0."""
        result = []
        for item in self.all_items():
            if item.item and item.item.get("durability") is not None and item.item.get("durability", 0) > 0:
                result.append(item)
        return result
