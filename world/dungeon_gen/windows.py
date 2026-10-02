"""Window placement for hulls and buildings."""

from __future__ import annotations

import random

import numpy as np

from world import tile_types
from world.dungeon_gen.rooms import RectRoom
from world.game_map import GameMap


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
    w, h = game_map.width, game_map.height
    wall_tid = int(wall_tile["tile_id"])

    # Direction pairs: (dx, dy) for the inside (floor) side;
    # opposite direction is the outside (hull) side.
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]

    # Collect candidates: map (x,y) -> (inside_dx, inside_dy)
    # If a tile qualifies in multiple directions, keep only the first.
    candidates: dict[tuple[int, int], tuple[int, int]] = {}

    for x in range(1, w - 1):
        for y in range(1, h - 1):
            if int(game_map.tiles["tile_id"][x, y]) != wall_tid:
                continue
            for dx, dy in directions:
                inside_x, inside_y = x + dx, y + dy
                outside_x, outside_y = x - dx, y - dy
                if not game_map.in_bounds(inside_x, inside_y):
                    continue
                if not game_map.in_bounds(outside_x, outside_y):
                    continue
                if not game_map.tiles["walkable"][inside_x, inside_y]:
                    continue
                if int(game_map.tiles["tile_id"][outside_x, outside_y]) != wall_tid:
                    continue
                if (x, y) not in candidates:
                    candidates[(x, y)] = (dx, dy)
                break

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
    w, h = game_map.width, game_map.height
    wall_tid = int(wall_tile["tile_id"])

    # Direction pairs: (dx, dy) for the inside (floor) side
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]

    # Collect hull-facing candidates with their room association
    # candidate -> (inside_direction, room)
    candidates: dict[tuple[int, int], tuple[tuple[int, int], RectRoom]] = {}

    for x in range(1, w - 1):
        for y in range(1, h - 1):
            if int(game_map.tiles["tile_id"][x, y]) != wall_tid:
                continue
            for dx, dy in directions:
                inside_x, inside_y = x + dx, y + dy
                outside_x, outside_y = x - dx, y - dy
                if not game_map.in_bounds(inside_x, inside_y):
                    continue
                if not game_map.in_bounds(outside_x, outside_y):
                    continue
                if not game_map.tiles["walkable"][inside_x, inside_y]:
                    continue
                if int(game_map.tiles["tile_id"][outside_x, outside_y]) != wall_tid:
                    continue

                # Find which room this wall belongs to
                room = None
                for r in rooms:
                    if r.x1 <= x <= r.x2 and r.y1 <= y <= r.y2:
                        room = r
                        break
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
                if room.label == "bridge":
                    # Bridge: allow west (forward), north, south — no aft (east)
                    # Aft-facing wall: inside is west (dx=-1), so block dx=-1
                    if dx == -1 and dy == 0:
                        continue  # skip aft-facing bridge windows
                else:
                    pass  # other rooms: allow all hull-facing directions

                if (x, y) not in candidates:
                    candidates[(x, y)] = ((dx, dy), room)
                break

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
    # Each candidate: (x, y)
    # Directions: outside_dx/dy tells which way is outside
    sides: list[list[tuple[int, int]]] = []

    for wing in wing_rects:
        # North wall: y=wing.y1, x in (x1+1 .. x2-1), outside = y-1
        north = []
        for x in range(wing.x1 + 1, wing.x2):
            pos = (x, wing.y1)
            outside = (x, wing.y1 - 1)
            inside = (x, wing.y1 + 1)
            if _is_window_candidate(game_map, pos, outside, inside, wall_tid, outside_tid):
                north.append(pos)
        sides.append(north)

        # South wall: y=wing.y2, outside = y+1
        south = []
        for x in range(wing.x1 + 1, wing.x2):
            pos = (x, wing.y2)
            outside = (x, wing.y2 + 1)
            inside = (x, wing.y2 - 1)
            if _is_window_candidate(game_map, pos, outside, inside, wall_tid, outside_tid):
                south.append(pos)
        sides.append(south)

        # West wall: x=wing.x1, outside = x-1
        west = []
        for y in range(wing.y1 + 1, wing.y2):
            pos = (wing.x1, y)
            outside = (wing.x1 - 1, y)
            inside = (wing.x1 + 1, y)
            if _is_window_candidate(game_map, pos, outside, inside, wall_tid, outside_tid):
                west.append(pos)
        sides.append(west)

        # East wall: x=wing.x2, outside = x+1
        east = []
        for y in range(wing.y1 + 1, wing.y2):
            pos = (wing.x2, y)
            outside = (wing.x2 + 1, y)
            inside = (wing.x2 - 1, y)
            if _is_window_candidate(game_map, pos, outside, inside, wall_tid, outside_tid):
                east.append(pos)
        sides.append(east)

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
