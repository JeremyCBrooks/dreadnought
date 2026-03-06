"""Standalone consumable use logic, reusable from InventoryState or elsewhere."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity


def use_consumable(engine: Engine, player: Entity, item: Entity) -> bool:
    """Apply consumable effect. Removes item from player.inventory on success.

    Returns True if consumed, False if use failed (nothing to repair, no suit, etc).
    """
    itype = item.item.get("type") if item.item else None

    if itype == "heal":
        heal = item.item["value"]
        player.fighter.hp = min(player.fighter.max_hp, player.fighter.hp + heal)
        engine.message_log.add_message(
            f"Used {item.name}. Healed {heal} HP.", (0, 255, 0)
        )
        if item in player.inventory:
            player.inventory.remove(item)
        return True

    if itype == "repair":
        repaired = None
        if player.loadout:
            for other in player.loadout.all_items():
                if other.item and other.item.get("durability") is not None:
                    d = other.item.get("durability", 0)
                    max_d = other.item.get("max_durability", 5)
                    if d < max_d:
                        other.item["durability"] = min(max_d, d + item.item["value"])
                        repaired = other.name
                        break
        if repaired:
            engine.message_log.add_message(
                f"Used {item.name}. Repaired {repaired}.", (200, 200, 100)
            )
            if item in player.inventory:
                player.inventory.remove(item)
            return True
        engine.message_log.add_message("No damaged items to repair.", (150, 150, 100))
        return False

    if itype == "o2":
        if getattr(engine, "suit", None) and "vacuum" in engine.suit.resistances:
            max_o2 = engine.suit.resistances["vacuum"]
            cur = engine.suit.current_pools.get("vacuum", 0)
            engine.suit.current_pools["vacuum"] = min(max_o2, cur + item.item["value"])
            engine.message_log.add_message(
                f"Used {item.name}. O2 restored.", (100, 200, 255)
            )
            if item in player.inventory:
                player.inventory.remove(item)
            return True
        engine.message_log.add_message("No suit O2 to restore.", (150, 150, 150))
        return False

    return False
