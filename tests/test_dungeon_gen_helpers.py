"""Unit tests for the small shared helpers inside world.dungeon_gen."""

from __future__ import annotations

import random

from game.entity import Entity, Fighter
from world import tile_types
from world.dungeon_gen.basic_layouts import _place_room_lights
from world.dungeon_gen.buildings import _find_door_position
from world.dungeon_gen.paths import _has_cardinal_wall
from world.dungeon_gen.rooms import RectRoom, _roll_room
from world.dungeon_gen.spawning import _can_spawn_at, _make_interactable
from world.dungeon_gen.windows import _hull_facing_walls, _wall_sides
from world.game_map import GameMap

WALL_TID = int(tile_types.wall["tile_id"])


def _walled_map(width: int = 9, height: int = 9) -> GameMap:
    return GameMap(width, height, fill_tile=tile_types.wall)


def _floor_map(width: int = 9, height: int = 9) -> GameMap:
    return GameMap(width, height, fill_tile=tile_types.floor)


# ---- _place_room_lights ----

_LIGHTS = {
    "lab": {"radius": 5, "color": (1, 2, 3), "intensity": 0.5},
    "vault": {"radius": 3, "color": (4, 5, 6), "intensity": 0.25},
}


def test_place_room_lights_lights_labelled_rooms_at_their_centre():
    game_map = _floor_map(30, 30)
    lab = RectRoom(2, 2, 6, 4, label="lab")

    _place_room_lights(game_map, [lab], _LIGHTS)

    (light,) = game_map.light_sources
    assert (light.x, light.y) == lab.center
    assert (light.radius, light.color, light.intensity) == (5, (1, 2, 3), 0.5)


def test_place_room_lights_skips_rooms_without_an_entry():
    game_map = _floor_map(30, 30)
    _place_room_lights(game_map, [RectRoom(2, 2, 6, 4, label="closet"), RectRoom(10, 10, 4, 4)], _LIGHTS)
    assert game_map.light_sources == []


def test_place_room_lights_follows_room_order():
    game_map = _floor_map(30, 30)
    vault = RectRoom(12, 12, 4, 4, label="vault")
    lab = RectRoom(2, 2, 6, 4, label="lab")

    _place_room_lights(game_map, [vault, lab], _LIGHTS)

    assert [(ls.x, ls.y) for ls in game_map.light_sources] == [vault.center, lab.center]


# ---- _has_cardinal_wall ----


def test_has_cardinal_wall_true_for_orthogonal_neighbour():
    game_map = _floor_map()
    game_map.tiles[4, 3] = tile_types.wall
    assert _has_cardinal_wall(game_map, 4, 4, WALL_TID) is True


def test_has_cardinal_wall_false_for_diagonal_only_neighbour():
    game_map = _floor_map()
    game_map.tiles[3, 3] = tile_types.wall
    assert _has_cardinal_wall(game_map, 4, 4, WALL_TID) is False


def test_has_cardinal_wall_ignores_out_of_bounds_neighbours():
    assert _has_cardinal_wall(_floor_map(), 0, 0, WALL_TID) is False


# ---- _hull_facing_walls ----


def test_hull_facing_walls_reports_wall_between_floor_and_hull():
    game_map = _walled_map()
    game_map.tiles[4, 4] = tile_types.floor

    found = set(_hull_facing_walls(game_map, WALL_TID))

    # (x, y, dx, dy): the floor ("inside") lies at (x + dx, y + dy).
    assert found == {(4, 3, 0, 1), (4, 5, 0, -1), (3, 4, 1, 0), (5, 4, -1, 0)}


def test_hull_facing_walls_skips_walls_with_floor_on_both_sides():
    game_map = _walled_map()
    game_map.tiles[3, 4] = tile_types.floor
    game_map.tiles[5, 4] = tile_types.floor

    assert not [hit for hit in _hull_facing_walls(game_map, WALL_TID) if hit[:2] == (4, 4)]


def test_hull_facing_walls_never_reports_the_map_border():
    game_map = _walled_map(5, 5)
    game_map.tiles[1, 1] = tile_types.floor

    assert all(0 < x < 4 and 0 < y < 4 for x, y, _, _ in _hull_facing_walls(game_map, WALL_TID))


def test_hull_facing_walls_scans_in_column_then_row_order():
    game_map = _walled_map()
    game_map.tiles[4, 4] = tile_types.floor

    positions = [(x, y) for x, y, _, _ in _hull_facing_walls(game_map, WALL_TID)]

    assert positions == sorted(positions)


# ---- _can_spawn_at ----


def test_can_spawn_at_accepts_free_floor():
    assert _can_spawn_at(_floor_map(), 4, 4, exit_pos=None) is True


def test_can_spawn_at_rejects_out_of_bounds():
    assert _can_spawn_at(_floor_map(), 99, 4, exit_pos=None) is False


def test_can_spawn_at_rejects_unwalkable_tile():
    assert _can_spawn_at(_walled_map(), 4, 4, exit_pos=None) is False


def test_can_spawn_at_rejects_tile_next_to_exit():
    assert _can_spawn_at(_floor_map(), 4, 4, exit_pos=(5, 5)) is False


def test_can_spawn_at_rejects_blocking_entity():
    game_map = _floor_map()
    game_map.entities.append(Entity(x=4, y=4, name="Rat", fighter=Fighter(1, 1, 0, 1)))
    assert _can_spawn_at(game_map, 4, 4, exit_pos=None, allow_non_blocking=True) is False


def test_can_spawn_at_rejects_non_blocking_entity_by_default():
    game_map = _floor_map()
    game_map.entities.append(Entity(x=4, y=4, name="Crate", blocks_movement=False, item={"type": "junk"}))
    assert _can_spawn_at(game_map, 4, 4, exit_pos=None) is False


def test_can_spawn_at_can_allow_non_blocking_entity():
    game_map = _floor_map()
    game_map.entities.append(Entity(x=4, y=4, name="Crate", blocks_movement=False, item={"type": "junk"}))
    assert _can_spawn_at(game_map, 4, 4, exit_pos=None, allow_non_blocking=True) is True


# ---- _find_door_position ----


def test_find_door_position_vertical_prefers_spots_open_on_both_sides():
    game_map = _walled_map(9, 12)
    game_map.tiles[3, 5] = tile_types.floor
    game_map.tiles[5, 5] = tile_types.floor

    assert _find_door_position(game_map, random.Random(0), 4, 0, 11, vertical=True) == 5


def test_find_door_position_horizontal_prefers_spots_open_on_both_sides():
    game_map = _walled_map(12, 9)
    game_map.tiles[5, 3] = tile_types.floor
    game_map.tiles[5, 5] = tile_types.floor

    assert _find_door_position(game_map, random.Random(0), 4, 0, 11, vertical=False) == 5


def test_find_door_position_returns_none_when_span_is_too_short():
    assert _find_door_position(_walled_map(), random.Random(0), 4, 2, 5, vertical=True) is None


def test_find_door_position_falls_back_to_one_randint_in_range():
    """With no ideal spot it must draw exactly one randint(lo, hi), as before."""
    reference = random.Random(3)
    expected = reference.randint(2, 9)
    rng = random.Random(3)

    assert _find_door_position(_walled_map(9, 12), rng, 4, 0, 11, vertical=True) == expected
    assert rng.getstate() == reference.getstate()


def test_find_door_position_draws_one_choice_over_ascending_candidates():
    game_map = _walled_map(9, 12)
    for y in (3, 6, 8):
        game_map.tiles[3, y] = tile_types.floor
        game_map.tiles[5, y] = tile_types.floor
    expected = random.Random(5).choice([3, 6, 8])

    assert _find_door_position(game_map, random.Random(5), 4, 0, 11, vertical=True) == expected


# ---- _roll_room ----


def test_roll_room_draws_width_height_x_y_in_that_order():
    reference = random.Random(11)
    rw = reference.randint(4, 8)
    rh = reference.randint(3, 6)
    rx = reference.randint(1, max(1, 40 - rw - 2))
    ry = reference.randint(1, max(1, 30 - rh - 2))

    room = _roll_room(random.Random(11), 40, 30, 4, 8, 3, 6, label="lab")

    assert (room.x1, room.y1, room.x2, room.y2, room.label) == (rx, ry, rx + rw, ry + rh, "lab")


def test_roll_room_consumes_exactly_four_draws():
    rng = random.Random(11)
    _roll_room(rng, 40, 30, 4, 8, 3, 6)
    reference = random.Random(11)
    rw = reference.randint(4, 8)
    rh = reference.randint(3, 6)
    reference.randint(1, max(1, 40 - rw - 2))
    reference.randint(1, max(1, 30 - rh - 2))
    assert rng.getstate() == reference.getstate()


def test_roll_room_keeps_room_on_a_map_too_small_for_it():
    room = _roll_room(random.Random(1), 5, 5, 8, 8, 8, 8)
    assert (room.x1, room.y1) == (1, 1)


# ---- _make_interactable ----


def test_make_interactable_builds_non_blocking_entity_with_kind_hazard_and_loot():
    hazard = {"type": "electric"}
    loot = {"name": "Coin"}

    entity = _make_interactable(3, 4, "&", (1, 2, 3), "Comms Terminal", hazard, loot)

    assert (entity.x, entity.y, entity.char, entity.color, entity.name) == (3, 4, "&", (1, 2, 3), "Comms Terminal")
    assert entity.blocks_movement is False
    assert entity.interactable == {"kind": "comms terminal", "hazard": hazard, "loot": loot}
    assert entity.item is None and entity.fighter is None


# ---- _wall_sides ----


def test_wall_sides_lists_north_south_west_east_without_corners():
    north, south, west, east = _wall_sides(RectRoom(2, 3, 3, 2))  # x 2..5, y 3..5

    # Each entry is (wall position, outside neighbour, inside neighbour).
    assert north == [((3, 3), (3, 2), (3, 4)), ((4, 3), (4, 2), (4, 4))]
    assert south == [((3, 5), (3, 6), (3, 4)), ((4, 5), (4, 6), (4, 4))]
    assert west == [((2, 4), (1, 4), (3, 4))]
    assert east == [((5, 4), (6, 4), (4, 4))]
