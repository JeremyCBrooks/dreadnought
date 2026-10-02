"""Hand mission salvage over to the ship when the player comes back aboard."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from data.colors import EQUIP_MSG

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity

type SalvageHandler = Callable[[Engine, Entity], None]


def _convert_reactor_core(engine: Engine, core: Entity) -> None:
    added = engine.ship.add_fuel(core.item["value"])
    if added > 0:
        engine.message_log.add_message(f"Reactor core converted to fuel. (+{added} fuel)", EQUIP_MSG)


def _install_nav_unit(engine: Engine, unit: Entity) -> None:
    engine.ship.add_nav_unit()
    engine.message_log.add_message("Navigation unit installed.", (0, 255, 200))


def _patch_hull(engine: Engine, kit: Entity) -> None:
    repaired = engine.ship.repair_hull(kit.item["value"])
    if repaired > 0:
        engine.message_log.add_message(f"Hull patched. (+{repaired} hull integrity)", EQUIP_MSG)


def _stow_dreadnought_core(engine: Engine, core: Entity) -> None:
    engine.ship.add_cargo(core)
    engine.message_log.add_message("Dreadnought core secured in cargo hold.", (255, 50, 50))


def _reveal_dreadnought_if_ready(engine: Engine) -> None:
    """Spawn the Dreadnought system once every nav unit is installed."""
    if engine.ship.nav_units < engine.ship.max_nav_units:
        return
    if not engine.galaxy or engine.galaxy.dreadnought_system:
        return
    engine.galaxy.spawn_dreadnought()
    engine.message_log.add_message(
        "All navigation units installed. The Dreadnought's coordinates are locked in!",
        (255, 200, 0),
    )


# Item type → (what the ship does with one, what happens after all of that type are in).
# Order is the order the messages appear in. Add a salvage type here, nowhere else.
_SALVAGE: dict[str, tuple[SalvageHandler, Callable[[Engine], None] | None]] = {
    "reactor_core": (_convert_reactor_core, None),
    "nav_unit": (_install_nav_unit, _reveal_dreadnought_if_ready),
    "hull_repair": (_patch_hull, None),
    "dreadnought_core": (_stow_dreadnought_core, None),
}


def unload_mission_salvage(engine: Engine, inventory: list[Entity]) -> None:
    """Give the ship every salvage item in *inventory*, removing each from the list."""
    for item_type, (handle, afterwards) in _SALVAGE.items():
        for item in [i for i in inventory if i.item and i.item.get("type") == item_type]:
            handle(engine, item)
            inventory.remove(item)
        if afterwards is not None:
            afterwards(engine)
