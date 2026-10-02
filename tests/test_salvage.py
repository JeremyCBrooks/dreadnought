"""Mission salvage is handed to the ship by item type, from one table."""

from game.entity import Entity
from game.salvage import unload_mission_salvage
from tests.conftest import make_heal_item, new_game


def _item(name: str, item_type: str, value: int) -> Entity:
    return Entity(name=name, blocks_movement=False, item={"type": item_type, "value": value})


def _texts(engine) -> list[str]:
    return [text for text, _ in engine.message_log.messages]


def test_reactor_core_becomes_fuel_and_leaves_the_inventory():
    engine, _ = new_game()
    engine.ship.fuel = 2
    inventory = [_item("Reactor Core", "reactor_core", 5), make_heal_item()]

    unload_mission_salvage(engine, inventory)

    assert engine.ship.fuel == 7
    assert [i.name for i in inventory] == ["Medkit"]
    assert "Reactor core converted to fuel. (+5 fuel)" in _texts(engine)


def test_reactor_core_at_a_full_tank_is_consumed_silently():
    engine, _ = new_game()
    engine.ship.fuel = engine.ship.max_fuel
    inventory = [_item("Reactor Core", "reactor_core", 5)]

    unload_mission_salvage(engine, inventory)

    assert inventory == []
    assert not any("converted to fuel" in t for t in _texts(engine))


def test_hull_patch_repairs_the_hull():
    engine, _ = new_game()
    engine.ship.hull = 4
    inventory = [_item("Hull Patch", "hull_repair", 3)]

    unload_mission_salvage(engine, inventory)

    assert engine.ship.hull == 7
    assert inventory == []


def test_dreadnought_core_goes_to_cargo():
    engine, _ = new_game()
    core = _item("Dreadnought Core", "dreadnought_core", 99)
    inventory = [core]

    unload_mission_salvage(engine, inventory)

    assert engine.ship.cargo == [core]
    assert inventory == []


def test_last_nav_unit_reveals_the_dreadnought_once():
    engine, _ = new_game()
    engine.ship.nav_units = engine.ship.max_nav_units - 1
    inventory = [_item("Navigation Unit", "nav_unit", 1)]

    unload_mission_salvage(engine, inventory)

    assert engine.ship.nav_units == engine.ship.max_nav_units
    assert engine.galaxy.dreadnought_system is not None
    assert _texts(engine).count("All navigation units installed. The Dreadnought's coordinates are locked in!") == 1


def test_ordinary_items_are_left_alone():
    engine, _ = new_game()
    inventory = [make_heal_item()]

    unload_mission_salvage(engine, inventory)

    assert len(inventory) == 1
