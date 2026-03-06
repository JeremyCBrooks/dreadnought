"""Tests for game.helpers shared utilities."""
from game.helpers import chebyshev, has_usable_ranged, is_door_closed, is_door_open, get_door_tile_ids
from game.entity import Entity, Fighter
from game.loadout import Loadout
from tests.conftest import make_arena
from world import tile_types


class TestChebyshev:
    def test_same_point(self):
        assert chebyshev(5, 5, 5, 5) == 0

    def test_cardinal(self):
        assert chebyshev(0, 0, 3, 0) == 3
        assert chebyshev(0, 0, 0, 4) == 4

    def test_diagonal(self):
        assert chebyshev(0, 0, 3, 3) == 3

    def test_asymmetric(self):
        assert chebyshev(1, 2, 5, 3) == 4

    def test_negative_coords(self):
        assert chebyshev(-3, -2, 1, 1) == 4


class TestHasUsableRanged:
    def test_no_weapon(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        assert has_usable_ranged(e) is False

    def test_ranged_in_inventory(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(name="Blaster", item={
            "type": "weapon", "weapon_class": "ranged", "ammo": 5, "value": 3,
        })
        e.inventory.append(wpn)
        assert has_usable_ranged(e) is True

    def test_ranged_no_ammo(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(name="Blaster", item={
            "type": "weapon", "weapon_class": "ranged", "ammo": 0, "value": 3,
        })
        e.inventory.append(wpn)
        assert has_usable_ranged(e) is False

    def test_melee_only(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(name="Sword", item={
            "type": "weapon", "weapon_class": "melee", "value": 3,
        })
        e.inventory.append(wpn)
        assert has_usable_ranged(e) is False

    def test_loadout_ranged(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(name="Blaster", item={
            "type": "weapon", "weapon_class": "ranged", "ammo": 5, "value": 3,
        })
        e.loadout = Loadout(slot1=wpn)
        assert has_usable_ranged(e) is True

    def test_loadout_no_ammo(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(name="Blaster", item={
            "type": "weapon", "weapon_class": "ranged", "ammo": 0, "value": 3,
        })
        e.loadout = Loadout(slot1=wpn)
        assert has_usable_ranged(e) is False


class TestDoorHelpers:
    def test_is_door_closed(self):
        gm = make_arena()
        gm.tiles[3, 3] = tile_types.door_closed
        assert is_door_closed(gm, 3, 3) is True
        assert is_door_closed(gm, 4, 4) is False

    def test_is_door_open(self):
        gm = make_arena()
        gm.tiles[3, 3] = tile_types.door_open
        assert is_door_open(gm, 3, 3) is True
        assert is_door_open(gm, 4, 4) is False

    def test_get_door_tile_ids(self):
        closed_id, open_id = get_door_tile_ids()
        assert closed_id == int(tile_types.door_closed["tile_id"])
        assert open_id == int(tile_types.door_open["tile_id"])
