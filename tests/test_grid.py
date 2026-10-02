"""Shared grid primitives: breadth-first search and neighbour masks."""

import numpy as np

from tests.conftest import make_arena
from world import tile_types
from world.grid import DIAGONALS, NEIGHBOURS_8, bfs, flood_fill_walkable, neighbour_any, neighbour_count, path_to


def _open(w: int, h: int, blocked: set = frozenset()):
    return lambda x, y: 0 <= x < w and 0 <= y < h and (x, y) not in blocked


def test_bfs_distances_are_manhattan_on_an_open_grid():
    dist, parent = bfs([(0, 0)], _open(4, 4))

    assert dist[(3, 3)] == 6
    assert len(dist) == 16
    assert parent[(0, 0)] is None


def test_bfs_goes_round_obstacles_and_stops_at_walls():
    wall = {(1, 0), (1, 1), (1, 2)}
    dist, _ = bfs([(0, 0)], _open(3, 4, wall))

    assert dist[(2, 0)] == 8
    assert all(p not in dist for p in wall)


def test_bfs_respects_max_distance():
    dist, _ = bfs([(0, 0)], _open(10, 1), max_distance=3)

    assert max(dist.values()) == 3
    assert (4, 0) not in dist


def test_bfs_from_several_sources_takes_the_nearest():
    dist, _ = bfs([(0, 0), (9, 0)], _open(10, 1))

    assert dist[(4, 0)] == 4
    assert dist[(6, 0)] == 3


def test_sources_are_included_even_when_not_passable():
    dist, _ = bfs([(0, 0)], lambda x, y: False)

    assert dist == {(0, 0): 0}


def test_parent_prefers_the_first_cardinal_that_reaches_a_tile():
    # (1, 1) is reached from both (1, 0) and (0, 1). (1, 0) is discovered first
    # (east is the first cardinal), so it is expanded first and becomes the parent.
    _, parent = bfs([(0, 0)], _open(2, 2))

    assert parent[(1, 1)] == (1, 0)


def test_path_to_walks_the_parents_back():
    _, parent = bfs([(0, 0)], _open(3, 1))

    assert path_to(parent, (2, 0)) == [(0, 0), (1, 0), (2, 0)]
    assert path_to(parent, (9, 9)) is None


def test_flood_fill_walkable_marks_reachable_floor_and_its_sources():
    game_map = make_arena(7, 5)
    for y in range(5):
        game_map.tiles[3, y] = tile_types.wall

    filled = flood_fill_walkable(game_map, [(1, 1), (99, 99)])

    assert filled[2, 3] and not filled[4, 1]
    assert filled.shape == (7, 5)
    assert not filled[3, 1]


def test_neighbour_any_cardinal_and_eight_way():
    mask = np.zeros((3, 3), dtype=bool)
    mask[1, 1] = True

    cardinal = neighbour_any(mask)
    eight = neighbour_any(mask, NEIGHBOURS_8)

    assert cardinal.sum() == 4 and cardinal[0, 1] and not cardinal[0, 0] and not cardinal[1, 1]
    assert eight.sum() == 8 and eight[0, 0]
    assert neighbour_any(mask, DIAGONALS).sum() == 4


def test_neighbour_masks_do_not_wrap_at_the_edges():
    mask = np.zeros((3, 3), dtype=bool)
    mask[0, 0] = True

    assert neighbour_any(mask, NEIGHBOURS_8).sum() == 3
    assert not neighbour_any(mask)[2, 0]


def test_neighbour_count_counts_cardinal_neighbours():
    mask = np.ones((3, 3), dtype=bool)

    counts = neighbour_count(mask)

    assert counts[1, 1] == 4 and counts[0, 0] == 2 and counts[0, 1] == 3
