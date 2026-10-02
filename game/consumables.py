"""Standalone consumable use logic, reusable from InventoryState or elsewhere."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from data.colors import HP_GREEN, INTERACT_EMPTY, PROMPT, SCAN_MSG
from game.helpers import chebyshev, has_clear_shot

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity
    from world.game_map import GameMap


# How close (in tiles, with a clear line) the player must be to the breach a Hull Patch seals.
HULL_PATCH_RANGE = 2


def _consume(player: Entity, item: Entity) -> None:
    """Remove a consumed item from the player's inventory."""
    if item in player.inventory:
        player.inventory.remove(item)


def _spend_charge(player: Entity, item: Entity) -> None:
    """Use up one of the item's ``value`` charges; the last one consumes it."""
    item.item["value"] -= 1
    if item.item["value"] <= 0:
        _consume(player, item)


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


def _breach_in_reach(game_map: GameMap, player: Entity, reach: int) -> tuple[int, int] | None:
    """The nearest breach within *reach* tiles that the player has a clear line to.

    A breach with anyone or anything in it is passed over: the plate would seal them into the hull.
    """
    occupied = {(e.x, e.y) for e in game_map.entities}
    in_reach = [
        (chebyshev(player.x, player.y, x, y), (x, y))
        for x, y in game_map.hull_breaches
        if (x, y) not in occupied
        and chebyshev(player.x, player.y, x, y) <= reach
        and has_clear_shot(game_map, player.x, player.y, x, y)
    ]
    return min(in_reach)[1] if in_reach else None


def _use_hull_patch(engine: Engine, player: Entity, item: Entity) -> bool:
    ship = getattr(engine, "ship", None)
    if ship is None or ship.game_map is None or engine.game_map is not ship.game_map:
        engine.message_log.add_message("A hull patch only bonds to your own ship's hull.", INTERACT_EMPTY)
        return False
    if not ship.game_map.hull_breaches:
        engine.message_log.add_message("No breaches to seal.", INTERACT_EMPTY)
        return False
    breach = _breach_in_reach(ship.game_map, player, HULL_PATCH_RANGE)
    if breach is None:
        engine.message_log.add_message("No clear breach within reach.", INTERACT_EMPTY)
        return False
    ship.seal_hull_breach(*breach)
    engine.message_log.add_message(f"Breach sealed. (hull {ship.hull}/{ship.max_hull})", PROMPT)
    return True


type Effect = Callable[[Engine, Entity, Entity], bool]
type Spend = Callable[[Entity, Entity], None]

# Item type → (what using one does, what a successful use costs).
# Add a consumable type here, nowhere else.
_EFFECTS: dict[str, tuple[Effect, Spend]] = {
    "heal": (_use_heal, _consume),
    "repair": (_use_repair, _consume),
    "o2": (_use_o2, _consume),
    "hull_repair": (_use_hull_patch, _spend_charge),
}


def charges_left(item: Entity) -> int | None:
    """Uses left on a multi-charge consumable, or None for anything used up in one go."""
    if not item.item:
        return None
    _, spend = _EFFECTS.get(item.item.get("type"), (None, None))
    return item.item.get("value", 0) if spend is _spend_charge else None


def use_consumable(engine: Engine, player: Entity, item: Entity) -> bool:
    """Apply consumable effect. On success the item (or one charge of it) is spent.

    Returns True if it took effect, False if use failed (nothing to repair, no suit, etc).
    """
    effect, spend = _EFFECTS.get(item.item.get("type"), (None, None)) if item.item else (None, None)
    if effect is None or not effect(engine, player, item):
        return False
    spend(player, item)
    return True
