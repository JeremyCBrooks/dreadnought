"""Tests for Ship class."""

from game.entity import Entity
from game.ship import Ship


def test_ship_defaults():
    ship = Ship()
    assert ship.fuel == 5
    assert ship.max_fuel == 10
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


def test_ship_hull_defaults():
    ship = Ship()
    assert ship.hull == 10
    assert ship.max_hull == 10


def test_ship_nav_units_default():
    ship = Ship()
    assert ship.nav_units == 0


def test_max_nav_units_property():
    ship = Ship()
    assert ship.max_nav_units == 6


def test_custom_ship():
    ship = Ship(fuel=50, max_fuel=200, scanner_quality=3, hull=20, max_hull=30)
    assert ship.fuel == 50
    assert ship.max_fuel == 200
    assert ship.scanner_quality == 3
    assert ship.hull == 20
    assert ship.max_hull == 30


# --- add_fuel ---


def test_add_fuel_basic():
    ship = Ship(fuel=5, max_fuel=10)
    added = ship.add_fuel(3)
    assert added == 3
    assert ship.fuel == 8


def test_add_fuel_clamps_at_max():
    ship = Ship(fuel=8, max_fuel=10)
    added = ship.add_fuel(5)
    assert added == 2
    assert ship.fuel == 10


def test_add_fuel_already_full():
    ship = Ship(fuel=10, max_fuel=10)
    added = ship.add_fuel(3)
    assert added == 0
    assert ship.fuel == 10


# --- consume_fuel ---


def test_consume_fuel_success():
    ship = Ship(fuel=5, max_fuel=10)
    assert ship.consume_fuel(2) is True
    assert ship.fuel == 3


def test_consume_fuel_insufficient():
    ship = Ship(fuel=1, max_fuel=10)
    assert ship.consume_fuel(2) is False
    assert ship.fuel == 1


def test_consume_fuel_exact():
    ship = Ship(fuel=3, max_fuel=10)
    assert ship.consume_fuel(3) is True
    assert ship.fuel == 0


# --- damage_hull ---


def test_damage_hull_basic():
    ship = Ship(hull=10, max_hull=10)
    ship.damage_hull(3)
    assert ship.hull == 7


def test_damage_hull_clamps_at_zero():
    ship = Ship(hull=2, max_hull=10)
    ship.damage_hull(5)
    assert ship.hull == 0


def test_damage_hull_already_zero():
    ship = Ship(hull=0, max_hull=10)
    ship.damage_hull(1)
    assert ship.hull == 0


# --- repair_hull ---


def test_repair_hull_basic():
    ship = Ship(hull=5, max_hull=10)
    repaired = ship.repair_hull(3)
    assert repaired == 3
    assert ship.hull == 8


def test_repair_hull_clamps_at_max():
    ship = Ship(hull=9, max_hull=10)
    repaired = ship.repair_hull(5)
    assert repaired == 1
    assert ship.hull == 10


def test_repair_hull_already_full():
    ship = Ship(hull=10, max_hull=10)
    repaired = ship.repair_hull(3)
    assert repaired == 0
    assert ship.hull == 10


# --- add_nav_unit ---


def test_add_nav_unit_basic():
    ship = Ship()
    assert ship.add_nav_unit() is True
    assert ship.nav_units == 1


def test_add_nav_unit_clamps_at_max():
    ship = Ship()
    ship.nav_units = 6
    assert ship.add_nav_unit() is False
    assert ship.nav_units == 6


def test_add_nav_unit_increments_to_max():
    ship = Ship()
    ship.nav_units = 5
    assert ship.add_nav_unit() is True
    assert ship.nav_units == 6
