"""Tests for Ship class."""
from game.ship import Ship
from game.entity import Entity


def test_ship_defaults():
    ship = Ship()
    assert ship.fuel == 100
    assert ship.max_fuel == 100
    assert ship.cargo == []
    assert ship.scanner_quality == 1


def test_add_cargo():
    ship = Ship()
    item = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    ship.add_cargo(item)
    assert len(ship.cargo) == 1
    assert ship.cargo[0] is item


def test_remove_cargo():
    ship = Ship()
    item = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    ship.add_cargo(item)
    assert ship.remove_cargo(item) is True
    assert len(ship.cargo) == 0


def test_remove_cargo_not_found():
    ship = Ship()
    item = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    assert ship.remove_cargo(item) is False


def test_multiple_cargo():
    ship = Ship()
    items = [Entity(name=f"Item {i}") for i in range(5)]
    for item in items:
        ship.add_cargo(item)
    assert len(ship.cargo) == 5
    ship.remove_cargo(items[2])
    assert len(ship.cargo) == 4
    assert items[2] not in ship.cargo


def test_custom_ship():
    ship = Ship(fuel=50, max_fuel=200, scanner_quality=3)
    assert ship.fuel == 50
    assert ship.max_fuel == 200
    assert ship.scanner_quality == 3
