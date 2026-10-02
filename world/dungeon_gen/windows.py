"""Window placement for hulls and buildings."""

from __future__ import annotations

import random
from collections.abc import Iterator

import numpy as np

from world import tile_types
from world.dungeon_gen.rooms import RectRoom, _wall_sides
from world.game_map import GameMap


def _hull_facing_walls(game_map: GameMap, wall_tid: int) -> Iterator[tuple[int, int, int, int]]:
    """Yield (x, y, dx, dy) for interior wall tiles that separate floor from hull.

    (dx, dy) points from the wall to its walkable inside neighbour; the tile
    on the opposite side is more wall (uncarved hull). The map border is
    excluded. A tile qualifying in several directions is yielded once per
    direction, in north, south, west, east order of the inside neighbour.
    """
    for x in range(1, game_map.width - 1):
        for y in range(1, game_map.height - 1):
            if int(game_map.tiles["tile_id"][x, y]) != wall_tid:
                continue
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                inside = (x + dx, y + dy)
                outside = (x - dx, y - dy)
                if not game_map.in_bounds(*inside) or not game_map.in_bounds(*outside):
                    continue
                if game_map.tiles["walkable"][inside] and int(game_map.tiles["tile_id"][outside]) == wall_tid:
                    yield x, y, dx, dy


def _place_exterior_windows(
    game_map: GameMap,
    rng: random.Random,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> None:
    """Place window tiles on walls facing the hull (uncarved wall fill).

    Scans all wall tiles (excluding map border). A tile is a candidate if it
    has walkable floor on one side and more wall (hull) on the opposite side.
    Candidates are grouped into contiguous segments by orientation, then
    windows are placed with context-aware sizing.
    """
    wall_tid = int(wall_tile["tile_id"])

    # Collect candidates: map (x,y) -> (inside_dx, inside_dy)
    # If a tile qualifies in multiple directions, keep only the first.
    candidates: dict[tuple[int, int], tuple[int, int]] = {}
    for x, y, dx, dy in _hull_facing_walls(game_map, wall_tid):
        candidates.setdefault((x, y), (dx, dy))

    # Group candidates by (orientation, row/col) so _split_into_segments
    # receives positions that share one axis, sorted along the other.
    by_orient: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for (x, y), direction in candidates.items():
        by_orient.setdefault(direction, []).append((x, y))

    all_segments: list[list[tuple[int, int]]] = []
    for (dx, dy), positions in by_orient.items():
        if dx == 0:
            # North/south-facing walls — group by row, sort by x
            by_row: dict[int, list[tuple[int, int]]] = {}
            for pos in positions:
                by_row.setdefault(pos[1], []).append(pos)
            for row_positions in by_row.values():
                row_positions.sort()
                all_segments.extend(_split_into_segments(row_positions))
        else:
            # East/west-facing walls — group by column, sort by y
            by_col: dict[int, list[tuple[int, int]]] = {}
            for pos in positions:
                by_col.setdefault(pos[0], []).append(pos)
            for col_positions in by_col.values():
                col_positions.sort(key=lambda p: p[1])
                all_segments.extend(_split_into_segments(col_positions))

    # Place windows per segment with context-aware sizing
    for seg in all_segments:
        n = len(seg)
        if n < 2:
            continue
        if n <= 3:
            count = 1
        elif n <= 5:
            count = 2
        elif n <= 8:
            count = 3
        else:
            count = 5
        start = (n - count) // 2
        for i in range(start, start + count):
            x, y = seg[i]
            game_map.tiles[x, y] = tile_types.structure_window


def _place_ship_exterior_windows(
    game_map: GameMap,
    rng: random.Random,
    rooms: list[RectRoom],
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> None:
    """Place hull-facing windows on ship rooms.

    Bridge rooms get larger observation windows on forward (west) and side
    (north/south) walls. Other rooms get small portholes (1-2 max) on any
    hull-facing wall.
    """
    wall_tid = int(wall_tile["tile_id"])

    # Collect hull-facing candidates with their room association
    # candidate -> (inside_direction, room)
    # A tile that qualifies in several directions keeps the first accepted one.
    candidates: dict[tuple[int, int], tuple[tuple[int, int], RectRoom]] = {}

    for x, y, dx, dy in _hull_facing_walls(game_map, wall_tid):
        if (x, y) in candidates:
            continue

        # Find which room this wall belongs to
        room = next((r for r in rooms if r.x1 <= x <= r.x2 and r.y1 <= y <= r.y2), None)
        if room is None:
            continue

        # Filter by room type and direction
        # dx, dy is direction from wall to inside (floor side)
        # So the wall faces *away* from inside, i.e. toward (-dx, -dy)
        # Wall facing west (forward): outside is to the west, inside east
        #   -> dx=1, dy=0 (inside is east of wall)
        # Wall facing north: outside north, inside south -> dx=0, dy=1
        # Wall facing south: outside south, inside north -> dx=0, dy=-1
        # Wall facing east (aft): outside east, inside west -> dx=-1, dy=0
        # Bridge: allow west (forward), north, south — no aft (east).
        # Aft-facing wall: inside is west (dx=-1), so block dx=-1.
        # Other rooms allow all hull-facing directions.
        if room.label == "bridge" and (dx, dy) == (-1, 0):
            continue  # skip aft-facing bridge windows

        candidates[(x, y)] = ((dx, dy), room)

    # Group candidates by (room, orientation) for segment building
    grouped: dict[tuple[str, tuple[int, int]], list[tuple[int, int]]] = {}
    for (x, y), ((dx, dy), room) in candidates.items():
        # Use a hashable key that includes room identity
        group_key = (room.label + str(id(room)), (dx, dy))
        grouped.setdefault(group_key, []).append((x, y))

    # Build segments and place windows
    for (room_key, direction), positions in grouped.items():
        is_bridge = room_key.startswith("bridge")
        segments = _split_into_segments(positions)
        for seg in segments:
            n = len(seg)
            if n < 2:
                continue
            if is_bridge:
                # Bridge: fill entire segment (observation windows)
                count = n
            else:
                # Other rooms: porthole sizing
                if n <= 4:
                    count = 1
                else:
                    count = 2
            start = (n - count) // 2
            # Look up the hull direction for this group from any candidate
            sample = seg[0]
            (sdx, sdy), _ = candidates[sample]
            hull_dx, hull_dy = -sdx, -sdy  # direction toward hull
            for i in range(start, start + count):
                x, y = seg[i]
                game_map.tiles[x, y] = tile_types.structure_window
                # Also replace the hull wall outside so the window isn't blocked
                hx, hy = x + hull_dx, y + hull_dy
                if game_map.in_bounds(hx, hy):
                    game_map.tiles[hx, hy] = tile_types.structure_window


def _place_building_windows(
    game_map: GameMap,
    rng: random.Random,
    wing_rects: list[RectRoom],
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
    outside_tid: int | None = None,
) -> None:
    """Place window tiles on exterior walls of rooms/buildings.

    Scans each rect's 4 exterior edges (excluding corners), identifies
    candidate wall tiles that face *outside_tid* outside and walkable floor
    inside, groups them into contiguous segments, then places centered
    window tile(s) per segment.

    *outside_tid* defaults to ground for colony buildings; pass
    ``int(floor_tile["tile_id"])`` for ship/starbase corridors.
    """
    wall_tid = int(wall_tile["tile_id"])
    if outside_tid is None:
        outside_tid = int(tile_types.ground["tile_id"])

    # Collect candidate positions per side, grouped by wing & direction
    sides: list[list[tuple[int, int]]] = [
        [
            pos
            for pos, outside, inside in side
            if _is_window_candidate(game_map, pos, outside, inside, wall_tid, outside_tid)
        ]
        for wing in wing_rects
        for side in _wall_sides(wing)
    ]

    # For each side, split candidates into contiguous segments and place windows
    for candidates in sides:
        if not candidates:
            continue
        segments = _split_into_segments(candidates)
        for seg in segments:
            _place_centered_windows(game_map, seg)


def _is_window_candidate(
    game_map: GameMap,
    pos: tuple[int, int],
    outside: tuple[int, int],
    inside: tuple[int, int],
    wall_tid: int,
    outside_tid: int,
) -> bool:
    """Check if a wall tile qualifies as a window candidate."""
    if not game_map.in_bounds(*outside) or not game_map.in_bounds(*inside):
        return False
    if int(game_map.tiles["tile_id"][pos[0], pos[1]]) != wall_tid:
        return False
    if int(game_map.tiles["tile_id"][outside[0], outside[1]]) != outside_tid:
        return False
    if not game_map.tiles["walkable"][inside[0], inside[1]]:
        return False
    return True


def _split_into_segments(
    candidates: list[tuple[int, int]],
) -> list[list[tuple[int, int]]]:
    """Split a list of positions into contiguous segments.

    Positions are contiguous if they differ by 1 in either x or y
    (they'll all share one axis since they're on the same wall side).
    """
    if not candidates:
        return []
    segments: list[list[tuple[int, int]]] = [[candidates[0]]]
    for pos in candidates[1:]:
        prev = segments[-1][-1]
        if abs(pos[0] - prev[0]) + abs(pos[1] - prev[1]) == 1:
            segments[-1].append(pos)
        else:
            segments.append([pos])
    return segments


def _place_centered_windows(
    game_map: GameMap,
    segment: list[tuple[int, int]],
) -> None:
    """Place centered window tile(s) in a wall segment."""
    n = len(segment)
    if n < 3:
        return  # too narrow

    if n <= 4:
        count = 1
    elif n <= 6:
        count = 2
    else:
        count = 3

    start = (n - count) // 2
    for i in range(start, start + count):
        x, y = segment[i]
        game_map.tiles[x, y] = tile_types.structure_window
