"""Tests for tile type definitions."""
from world.tile_types import (
    floor, wall, exit_tile, rock_floor, rock_wall,
    dirt_floor, structure_wall, ground, tile_dt,
)


def test_floor_walkable_and_transparent():
    assert floor["walkable"] == True
    assert floor["transparent"] == True


def test_wall_not_walkable_or_transparent():
    assert wall["walkable"] == False
    assert wall["transparent"] == False


def test_exit_tile_walkable():
    assert exit_tile["walkable"] == True


def test_tile_dtype_has_expected_fields():
    assert set(tile_dt.names) == {"walkable", "transparent", "dark", "light", "lit", "tile_id"}


def test_rock_floor_walkable():
    assert rock_floor["walkable"] == True
    assert rock_floor["transparent"] == True


def test_rock_wall_not_walkable():
    assert rock_wall["walkable"] == False
    assert rock_wall["transparent"] == False


def test_dirt_floor_walkable():
    assert dirt_floor["walkable"] == True
    assert dirt_floor["transparent"] == True


def test_structure_wall_not_walkable():
    assert structure_wall["walkable"] == False
    assert structure_wall["transparent"] == False


def test_ground_walkable_and_transparent():
    assert ground["walkable"] == True
    assert ground["transparent"] == True


def test_each_tile_has_unique_tile_id():
    tiles = [floor, wall, exit_tile, rock_floor, rock_wall, dirt_floor, structure_wall, ground]
    ids = [int(t["tile_id"]) for t in tiles]
    assert len(ids) == len(set(ids)), f"Duplicate tile_ids: {ids}"
