"""Building helpers produce the same tiles whichever axis they work along."""

import random

import numpy as np

from world import tile_types
from world.dungeon_gen.buildings import _carve_wing_doorway, _subdivide_building
from world.dungeon_gen.rooms import RectRoom
from world.game_map import GameMap
from world.grid import flood_fill_walkable


def _walled(w: int = 30, h: int = 30) -> GameMap:
    return GameMap(w, h, fill_tile=tile_types.structure_wall)


def _floor(game_map: GameMap) -> np.ndarray:
    return game_map.tiles["tile_id"] == int(tile_types.dirt_floor["tile_id"])


def _carve(game_map: GameMap, room: RectRoom) -> None:
    game_map.tiles[room.inner] = tile_types.dirt_floor


def test_doorway_between_side_by_side_wings_is_centred_on_the_shared_wall():
    game_map = _walled()
    left, right = RectRoom(2, 2, 6, 6), RectRoom(8, 4, 6, 8)
    _carve(game_map, left)
    _carve(game_map, right)

    _carve_wing_doorway(game_map, left, right, tile_types.dirt_floor)

    # overlap of interiors along y: max(3, 5)..min(7, 11) = 5..7, midpoint 6
    assert _floor(game_map)[8, 6]


def test_doorway_is_the_same_whichever_wing_comes_first():
    for a, b in [
        (RectRoom(2, 2, 6, 6), RectRoom(8, 4, 6, 8)),
        (RectRoom(4, 2, 8, 6), RectRoom(2, 8, 6, 6)),
    ]:
        first, second = _walled(), _walled()
        for game_map in (first, second):
            _carve(game_map, a)
            _carve(game_map, b)
        _carve_wing_doorway(first, a, b, tile_types.dirt_floor)
        _carve_wing_doorway(second, b, a, tile_types.dirt_floor)

        assert np.array_equal(_floor(first), _floor(second))


def test_doorway_between_stacked_wings_is_centred_on_the_shared_wall():
    game_map = _walled()
    top, bottom = RectRoom(4, 2, 8, 6), RectRoom(2, 8, 6, 6)
    _carve(game_map, top)
    _carve(game_map, bottom)

    _carve_wing_doorway(game_map, top, bottom, tile_types.dirt_floor)

    # overlap of interiors along x: max(5, 3)..min(11, 7) = 5..7, midpoint 6
    assert _floor(game_map)[6, 8]


def test_wings_that_do_not_touch_get_no_doorway():
    game_map = _walled()
    a, b = RectRoom(2, 2, 5, 5), RectRoom(12, 12, 5, 5)
    _carve(game_map, a)
    _carve(game_map, b)
    before = _floor(game_map).copy()

    _carve_wing_doorway(game_map, a, b, tile_types.dirt_floor)

    assert np.array_equal(_floor(game_map), before)


def test_subdividing_a_wide_and_a_tall_footprint_are_transposes_of_each_other():
    """The vertical-split and horizontal-split paths must be the same algorithm on swapped axes."""
    for seed in range(25):
        wide, tall = _walled(), _walled()
        wide_rooms = _subdivide_building(
            wide, random.Random(seed), 2, 2, 20, 10, 3, tile_types.dirt_floor, tile_types.structure_wall
        )
        tall_rooms = _subdivide_building(
            tall, random.Random(seed), 2, 2, 10, 20, 3, tile_types.dirt_floor, tile_types.structure_wall
        )

        assert np.array_equal(_floor(wide), _floor(tall).T), f"seed {seed}"
        assert [(r.x1, r.y1, r.x2, r.y2) for r in wide_rooms] == [(r.y1, r.x1, r.y2, r.x2) for r in tall_rooms]


def test_subdivided_rooms_are_all_connected():
    for seed in range(25):
        game_map = _walled()
        rooms = _subdivide_building(
            game_map, random.Random(seed), 2, 2, 22, 14, 3, tile_types.dirt_floor, tile_types.structure_wall
        )

        reached = flood_fill_walkable(game_map, [rooms[0].center])

        assert np.array_equal(reached, _floor(game_map)), f"seed {seed}"
