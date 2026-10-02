"""Standalone consumable use logic, reusable from InventoryState or elsewhere."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from data.colors import HP_GREEN, INTERACT_EMPTY, PROMPT, SCAN_MSG

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity


def _consume(player: Entity, item: Entity) -> None:
    """Remove a consumed item from the player's inventory."""
    if item in player.inventory:
        player.inventory.remove(item)


def _use_heal(engine: Engine, player: Entity, item: Entity) -> bool:
    if player.fighter.hp >= player.fighter.max_hp:
        engine.message_log.add_message("Already at full health.", INTERACT_EMPTY)
        return False
    old_hp = player.fighter.hp
    heal = item.item.get("value", 0)
    player.fighter.hp = min(player.fighter.max_hp, player.fighter.hp + heal)
    actual = player.fighter.hp - old_hp
    engine.message_log.add_message(f"Used {item.name}. Healed {actual} HP.", HP_GREEN)
    return True


def _use_repair(engine: Engine, player: Entity, item: Entity) -> bool:
    repaired = None
    if player.loadout:
        for other in player.loadout.all_items():
            if other.item and other.item.get("durability") is not None:
                d = other.item.get("durability", 0)
                max_d = other.item.get("max_durability", 5)
                if d < max_d:
                    other.item["durability"] = min(max_d, d + item.item.get("value", 1))
                    other.item.pop("damaged", None)
                    repaired = other.name
                    break
    if repaired:
        from game.loadout import recalc_melee_power

        recalc_melee_power(player)
        engine.message_log.add_message(f"Used {item.name}. Repaired {repaired}.", PROMPT)
        return True
    engine.message_log.add_message("No damaged items to repair.", INTERACT_EMPTY)
    return False


def _use_o2(engine: Engine, player: Entity, item: Entity) -> bool:
    if getattr(engine, "suit", None) and "vacuum" in engine.suit.resistances:
        max_o2 = engine.suit.resistances["vacuum"]
        cur = engine.suit.current_pools.get("vacuum", 0)
        if cur >= max_o2:
            engine.message_log.add_message("O2 already full.", INTERACT_EMPTY)
            return False
        engine.suit.current_pools["vacuum"] = min(max_o2, cur + item.item.get("value", 0))
        engine.message_log.add_message(f"Used {item.name}. O2 restored.", SCAN_MSG)
        return True
    engine.message_log.add_message("No suit O2 to restore.", INTERACT_EMPTY)
    return False


_EFFECTS: dict[str, Callable[[Engine, Entity, Entity], bool]] = {
    "heal": _use_heal,
    "repair": _use_repair,
    "o2": _use_o2,
}


def use_consumable(engine: Engine, player: Entity, item: Entity) -> bool:
    """Apply consumable effect. Removes item from player.inventory on success.

    Returns True if consumed, False if use failed (nothing to repair, no suit, etc).
    """
    effect = _EFFECTS.get(item.item.get("type")) if item.item else None
    if effect is None or not effect(engine, player, item):
        return False
    _consume(player, item)
    return True
