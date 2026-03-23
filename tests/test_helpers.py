"""Tests for game.helpers shared utilities."""

from game.entity import Entity, Fighter
from game.helpers import (
    chebyshev,
    get_door_tile_ids,
    get_equipped_ranged_weapon,
    has_ranged_weapon,
    has_usable_ranged,
    is_door_closed,
    is_door_open,
)
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
        wpn = Entity(
            name="Blaster",
            item={
                "type": "weapon",
                "weapon_class": "ranged",
                "ammo": 5,
                "value": 3,
            },
        )
        e.inventory.append(wpn)
        assert has_usable_ranged(e) is True

    def test_ranged_no_ammo(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(
            name="Blaster",
            item={
                "type": "weapon",
                "weapon_class": "ranged",
                "ammo": 0,
                "value": 3,
            },
        )
        e.inventory.append(wpn)
        assert has_usable_ranged(e) is False

    def test_melee_only(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(
            name="Sword",
            item={
                "type": "weapon",
                "weapon_class": "melee",
                "value": 3,
            },
        )
        e.inventory.append(wpn)
        assert has_usable_ranged(e) is False

    def test_loadout_ranged(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(
            name="Blaster",
            item={
                "type": "weapon",
                "weapon_class": "ranged",
                "ammo": 5,
                "value": 3,
            },
        )
        e.loadout = Loadout(slot1=wpn)
        assert has_usable_ranged(e) is True

    def test_loadout_no_ammo(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(
            name="Blaster",
            item={
                "type": "weapon",
                "weapon_class": "ranged",
                "ammo": 0,
                "value": 3,
            },
        )
        e.loadout = Loadout(slot1=wpn)
        assert has_usable_ranged(e) is False

    def test_damaged_ranged_not_usable_inventory(self):
        """A damaged ranged weapon in inventory should not be usable."""
        e = Entity(name="AI", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(
            name="Broken Blaster",
            item={
                "type": "weapon",
                "weapon_class": "ranged",
                "ammo": 5,
                "damaged": True,
            },
        )
        e.inventory.append(wpn)
        assert get_equipped_ranged_weapon(e) is None
        assert has_usable_ranged(e) is False

    def test_damaged_ranged_not_usable_loadout(self):
        """A damaged ranged weapon in loadout should not be usable."""
        e = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(
            name="Broken Blaster",
            item={
                "type": "weapon",
                "weapon_class": "ranged",
                "ammo": 5,
                "damaged": True,
            },
        )
        e.loadout = Loadout(slot1=wpn)
        assert get_equipped_ranged_weapon(e) is None
        assert has_usable_ranged(e) is False


class TestHasRangedWeapon:
    def test_no_weapon(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        assert has_ranged_weapon(e) is False

    def test_ranged_in_inventory(self):
        e = Entity(name="AI", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(
            name="Blaster",
            item={"type": "weapon", "weapon_class": "ranged", "ammo": 0},
        )
        e.inventory.append(wpn)
        assert has_ranged_weapon(e) is True

    def test_loadout_ranged(self):
        e = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(
            name="Blaster",
            item={"type": "weapon", "weapon_class": "ranged", "ammo": 0},
        )
        e.loadout = Loadout(slot1=wpn)
        assert has_ranged_weapon(e) is True

    def test_melee_only(self):
        e = Entity(name="Test", fighter=Fighter(10, 10, 0, 1))
        wpn = Entity(
            name="Sword",
            item={"type": "weapon", "weapon_class": "melee"},
        )
        e.inventory.append(wpn)
        assert has_ranged_weapon(e) is False


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

    def test_is_door_closed_out_of_bounds(self):
        """is_door_closed should return False for out-of-bounds coords."""
        gm = make_arena()
        assert is_door_closed(gm, -1, 0) is False
        assert is_door_closed(gm, 100, 100) is False
        assert is_door_closed(gm, 0, -5) is False

    def test_is_door_open_out_of_bounds(self):
        """is_door_open should return False for out-of-bounds coords."""
        gm = make_arena()
        assert is_door_open(gm, -1, 0) is False
        assert is_door_open(gm, 100, 100) is False
        assert is_door_open(gm, 0, -5) is False

    def test_is_diagonal_blocked_out_of_bounds(self):
        """is_diagonal_blocked should not crash for out-of-bounds diagonals."""
        from game.helpers import is_diagonal_blocked

        gm = make_arena()
        # Top-left corner diagonal should not crash
        assert is_diagonal_blocked(gm, 0, 0, -1, -1) is False
