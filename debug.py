"""Debug configuration flags for development. Toggle these to alter game behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from data.items import ItemDef, ScannerDef
    from engine.game_state import Engine
    from game.entity import Entity

GOD_MODE: bool = True  # Player takes no damage from any source
DISABLE_OXYGEN: bool = False  # Suit O2 pools never deplete
DISABLE_HAZARDS: bool = False  # Interactable hazards don't trigger
DISABLE_ENEMY_AI: bool = False  # Enemies skip their turns
ONE_HIT_KILL: bool = False  # Player attacks always kill
VISIBLE_ALL: bool = False  # All tiles visible, lit, and explored
MAX_NAV_UNITS: int | None = 1  # Override Ship.MAX_NAV_UNITS (None = use default 6)

# Debug starting inventory — list of (category, name) tuples.
# category is "scanner", "item", etc. matching data module categories.
# Set to empty list to disable.
START_INVENTORY: list[tuple[str, str]] = [
    ("scanner", "Basic Scanner"),
    ("scanner", "Advanced Scanner"),
    ("scanner", "Military Scanner"),
]

_DEFAULT_START_INVENTORY: list[tuple[str, str]] = list(START_INVENTORY)

_CATEGORY_LOOKUPS: dict[str, str] = {
    "scanner": "scanner_by_name",
    "item": "item_by_name",
}


def build_debug_inventory() -> list[Entity]:
    """Build Entity list from START_INVENTORY definitions. Returns [] if disabled."""
    if not START_INVENTORY:
        return []
    from data import items as items_mod
    from game.entity import Entity

    lookup: dict[str, Callable[[str], ItemDef | ScannerDef]] = {
        cat: getattr(items_mod, fn_name) for cat, fn_name in _CATEGORY_LOOKUPS.items()
    }

    result: list[Entity] = []
    for category, name in START_INVENTORY:
        lookup_fn = lookup.get(category)
        if lookup_fn is None:
            continue
        try:
            defn = lookup_fn(name)
        except KeyError:
            continue
        item_data = items_mod.build_item_data(defn)
        result.append(
            Entity(
                char=defn.char,
                color=defn.color,
                name=defn.name,
                item=item_data,
            )
        )
    return result


def seed_ship_cargo(engine: Engine) -> None:
    """Place debug starting items into ship cargo."""
    for item in build_debug_inventory():
        engine.ship.add_cargo(item)
