"""Village buildings: interior subdivision, wings and doorways."""

from __future__ import annotations

import random

import numpy as np

from world import tile_types
from world.dungeon_gen.rooms import RectRoom, _wall_sides
from world.game_map import GameMap


def _carve_room_interior(
    game_map: GameMap,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    floor_tile: np.ndarray,
) -> None:
    """Carve the interior of a room bounded by outer walls at (x1,y1)-(x2,y2)."""
    for bx in range(x1 + 1, x2):
        for by in range(y1 + 1, y2):
            if game_map.in_bounds(bx, by):
                game_map.tiles[bx, by] = floor_tile


def _find_door_position(
    game_map: GameMap,
    rng: random.Random,
    split: int,
    lo_edge: int,
    hi_edge: int,
    *,
    vertical: bool,
) -> int | None:
    """Find where to cut a door through a partition wall.

    A *vertical* partition runs along x == split and the result is a y
    between the edges; a horizontal one runs along y == split and the result
    is an x. Prefers positions where the tiles on both sides of the partition
    are already walkable, producing a clean 1-tile doorway. Falls back to any
    position in range if none are ideal, and returns None if the span is too
    short for a door.
    """
    lo, hi = lo_edge + 2, hi_edge - 2
    if lo > hi:
        return None

    def open_on_both_sides(pos: int) -> bool:
        sides = ((split - 1, pos), (split + 1, pos)) if vertical else ((pos, split - 1), (pos, split + 1))
        return all(game_map.in_bounds(x, y) and game_map.tiles["walkable"][x, y] for x, y in sides)

    good = [pos for pos in range(lo, hi + 1) if open_on_both_sides(pos)]
    if good:
        return rng.choice(good)
    return rng.randint(lo, hi)


def _subdivide_building(
    game_map: GameMap,
    rng: random.Random,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    num_rooms: int,
    floor_tile: np.ndarray,
    wall_tile: np.ndarray,
    label: str = "",
) -> list[RectRoom]:
    """Recursively subdivide a building footprint into rooms with internal doors.

    (x1, y1) and (x2, y2) are the outer wall coordinates of this sub-area.
    Interior is (x1+1..x2-1, y1+1..y2-1).
    Returns a list of RectRooms representing each carved sub-room.
    """
    inner = (x2 - x1 - 1, y2 - y1 - 1)

    # Min sub-room interior 3×3 → each half needs outer width ≥ 4 → min_offset 4
    min_offset = 4
    can_split = tuple(size >= min_offset * 2 - 1 for size in inner)  # (split x, split y)

    # Base case: single room
    if num_rooms <= 1 or not any(can_split):
        _carve_room_interior(game_map, x1, y1, x2, y2, floor_tile)
        return [RectRoom(x1, y1, x2 - x1, y2 - y1, label=label)]

    # Choose the split axis from viable options; prefer the longer dimension.
    # axis 0 is a vertical partition (splits x), axis 1 a horizontal one (splits y).
    if all(can_split):
        if inner[0] > inner[1]:
            axis = 0
        elif inner[1] > inner[0]:
            axis = 1
        else:
            axis = 0 if rng.choice(["vertical", "horizontal"]) == "vertical" else 1
    else:
        axis = 0 if can_split[0] else 1

    lo_edge, hi_edge = ((x1, x2), (y1, y2))[axis]
    cross_lo, cross_hi = ((y1, y2), (x1, x2))[axis]

    def at(along: int, across: int) -> tuple[int, int]:
        """(x, y) of the tile *along* the split axis and *across* it."""
        return (along, across) if axis == 0 else (across, along)

    lo, hi = lo_edge + min_offset, hi_edge - min_offset
    # Asymmetric split: when we need >2 rooms, push the partition toward one
    # side so the larger half can subdivide further.
    if num_rooms > 2:
        split = lo if rng.random() < 0.5 else hi
    else:
        split = rng.randint(lo, hi)

    # Draw partition wall
    for across in range(cross_lo + 1, cross_hi):
        pos = at(split, across)
        if game_map.in_bounds(*pos):
            game_map.tiles[pos] = wall_tile

    # Give 1 room to the smaller half and the rest to the bigger; 2 rooms split evenly.
    if num_rooms == 2:
        counts = (1, 1)
    elif split - lo_edge >= hi_edge - split:
        counts = (num_rooms - 1, 1)
    else:
        counts = (1, num_rooms - 1)

    if axis == 0:
        halves = ((x1, y1, split, y2), (split, y1, x2, y2))
    else:
        halves = ((x1, y1, x2, split), (x1, split, x2, y2))
    rooms: list[RectRoom] = []
    for half, count in zip(halves, counts, strict=True):
        rooms += _subdivide_building(game_map, rng, *half, count, floor_tile, wall_tile, label)

    # Carve a 1-tile doorway, preferring positions with floor on both sides
    door = _find_door_position(game_map, rng, split, cross_lo, cross_hi, vertical=axis == 0)
    if door is not None:
        game_map.tiles[at(split, door)] = floor_tile
        # Only force-clear a side if it's still walled (perpendicular partition)
        # but never breach the building's outer boundary walls
        for side, inside_building in ((split - 1, split - 1 > lo_edge), (split + 1, split + 1 < hi_edge)):
            pos = at(side, door)
            if inside_building and game_map.in_bounds(*pos) and not game_map.tiles["walkable"][pos]:
                game_map.tiles[pos] = floor_tile

    return rooms


# Weighted wing count distribution for village buildings
_VILLAGE_WING_WEIGHTS = [(1, 40), (2, 45), (3, 15)]


def _pick_building_room_count(rng: random.Random) -> int:
    """Pick number of wings using weighted distribution."""
    total = sum(w for _, w in _VILLAGE_WING_WEIGHTS)
    roll = rng.randint(1, total)
    cumulative = 0
    for count, weight in _VILLAGE_WING_WEIGHTS:
        cumulative += weight
        if roll <= cumulative:
            return count
    return 1


def _compose_building_wings(
    rng: random.Random,
    main_x: int,
    main_y: int,
    main_w: int,
    main_h: int,
    num_wings: int,
    min_w: int = 5,
    min_h: int = 5,
) -> list[tuple[int, int, int, int]]:
    """Return list of (x, y, w, h) rectangles forming a multi-wing building.

    The main wing is always first.  Secondary wings attach to random sides
    of the main wing with a random offset, producing L/T/U-shaped footprints.
    """
    wings = [(main_x, main_y, main_w, main_h)]
    if num_wings <= 1:
        return wings

    sides = ["north", "south", "east", "west"]
    rng.shuffle(sides)

    for i in range(num_wings - 1):
        side = sides[i % len(sides)]
        # Secondary wing dimensions: 60-80% of main, clamped to min
        sw = max(min_w, rng.randint(int(main_w * 0.6), max(int(main_w * 0.8), min_w)))
        sh = max(min_h, rng.randint(int(main_h * 0.6), max(int(main_h * 0.8), min_h)))

        # Minimum overlap of 3 tiles for a doorway
        min_overlap = 3
        if side in ("north", "south"):
            edge_len = main_w
            wing_edge = sw
            if wing_edge > edge_len:
                wing_edge = edge_len
                sw = wing_edge
            max_offset = max(0, edge_len - min_overlap)
            min_offset = max(0, wing_edge - edge_len + min_overlap)
            if min_offset > max_offset:
                # Can't get 3-tile overlap; just center it
                offset = max(0, (edge_len - wing_edge) // 2)
            else:
                offset = rng.randint(min(min_offset, max_offset), max(min_offset, max_offset))
            sx = main_x + offset
            if side == "north":
                sy = main_y - sh  # extends upward
            else:
                sy = main_y + main_h  # extends downward
            # Clamp offset so wing doesn't extend past main + wing width
            sx = min(sx, main_x + main_w - min_overlap)
            wings.append((sx, sy, sw, sh))
        else:  # east or west
            edge_len = main_h
            wing_edge = sh
            if wing_edge > edge_len:
                wing_edge = edge_len
                sh = wing_edge
            max_offset = max(0, edge_len - min_overlap)
            min_offset = max(0, wing_edge - edge_len + min_overlap)
            if min_offset > max_offset:
                offset = max(0, (edge_len - wing_edge) // 2)
            else:
                offset = rng.randint(min(min_offset, max_offset), max(min_offset, max_offset))
            sy = main_y + offset
            if side == "west":
                sx = main_x - sw  # extends left
            else:
                sx = main_x + main_w  # extends right
            sy = min(sy, main_y + main_h - min_overlap)
            wings.append((sx, sy, sw, sh))

    return wings


def _carve_wing_doorway(
    game_map: GameMap,
    wing_a: RectRoom,
    wing_b: RectRoom,
    floor_tile: np.ndarray,
) -> None:
    """Carve a 1-tile doorway through the shared wall between two adjacent wings.

    Two wings that share a side have an overlapping range of wall tiles.
    We find that overlap, carve the shared wall tile, and force-clear the
    tiles on both sides so internal partition walls don't block the passage.
    """
    a = ((wing_a.x1, wing_a.x2), (wing_a.y1, wing_a.y2))
    b = ((wing_b.x1, wing_b.x2), (wing_b.y1, wing_b.y2))
    for axis in (0, 1):  # 0: side by side (shared wall is a column), 1: stacked (a row)
        along = 1 - axis
        # A's far wall against B's near wall, then A's near wall against B's far wall.
        for shared, b_wall in ((a[axis][1], b[axis][0]), (a[axis][0], b[axis][1])):
            if shared != b_wall:
                continue
            lo = max(a[along][0], b[along][0]) + 1
            hi = min(a[along][1], b[along][1]) - 1
            if lo > hi:
                continue
            door = (lo + hi) // 2
            for step in (0, -1, 1):
                pos = (shared + step, door) if axis == 0 else (door, shared + step)
                # The wall tile itself always opens; its neighbours only if still blocked.
                if game_map.in_bounds(*pos) and (step == 0 or not game_map.tiles["walkable"][pos]):
                    game_map.tiles[pos] = floor_tile
            return


def _carve_external_door(
    game_map: GameMap,
    rng: random.Random,
    wing_rooms: list[RectRoom],
    floor_tile: np.ndarray,
) -> tuple[int, int] | None:
    """Carve a 1-tile door on a building's outer wall.

    Iterates over all wing perimeter tiles and picks ones that face outward
    (adjacent to a ground tile), so the door connects the building to the
    outside.  Prefers positions where the inside tile is already walkable.

    Returns the (x, y) of the ground tile just outside the door, or None.
    """
    ground_tid = int(tile_types.ground["tile_id"])

    # Each entry: (wall_pos, inside_pos, outside_pos), in north, south, west, east order per wing.
    door_candidates = [
        (wall, inside, outside)
        for wing in wing_rooms
        for side in _wall_sides(wing)
        for wall, outside, inside in side
        if game_map.in_bounds(*outside) and int(game_map.tiles["tile_id"][outside]) == ground_tid
    ]

    # Prefer positions where the inside tile is already walkable floor
    good = [
        (wall, inside, outside)
        for wall, inside, outside in door_candidates
        if (
            game_map.in_bounds(*wall)
            and game_map.in_bounds(*inside)
            and game_map.tiles["walkable"][inside[0], inside[1]]
        )
    ]
    if good:
        wall_pos, _, outside_pos = rng.choice(good)
        game_map.tiles[wall_pos[0], wall_pos[1]] = floor_tile
        return outside_pos
    elif door_candidates:
        # Fallback: pick any position, force-clear the inside tile too
        wall_pos, inside_pos, outside_pos = rng.choice(door_candidates)
        if game_map.in_bounds(*wall_pos):
            game_map.tiles[wall_pos[0], wall_pos[1]] = floor_tile
        if game_map.in_bounds(*inside_pos):
            game_map.tiles[inside_pos[0], inside_pos[1]] = floor_tile
        return outside_pos
    return None
