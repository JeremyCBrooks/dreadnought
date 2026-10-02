"""Village buildings: interior subdivision, wings and doorways."""

from __future__ import annotations

import random

import numpy as np

from world import tile_types
from world.dungeon_gen.rooms import RectRoom
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


def _find_door_position_v(
    game_map: GameMap,
    rng: random.Random,
    split_x: int,
    y1: int,
    y2: int,
) -> int | None:
    """Find a y-position for a door through a vertical partition at split_x.

    Prefers positions where both adjacent tiles (split_x-1, split_x+1) are
    already walkable, producing a clean 1-tile doorway.  Falls back to any
    valid position if none are ideal.
    """
    lo, hi = y1 + 2, y2 - 2
    if lo > hi:
        return None
    good = [
        y
        for y in range(lo, hi + 1)
        if (
            game_map.in_bounds(split_x - 1, y)
            and game_map.tiles["walkable"][split_x - 1, y]
            and game_map.in_bounds(split_x + 1, y)
            and game_map.tiles["walkable"][split_x + 1, y]
        )
    ]
    if good:
        return rng.choice(good)
    return rng.randint(lo, hi)


def _find_door_position_h(
    game_map: GameMap,
    rng: random.Random,
    split_y: int,
    x1: int,
    x2: int,
) -> int | None:
    """Find an x-position for a door through a horizontal partition at split_y.

    Same logic as the vertical variant but for a horizontal wall.
    """
    lo, hi = x1 + 2, x2 - 2
    if lo > hi:
        return None
    good = [
        x
        for x in range(lo, hi + 1)
        if (
            game_map.in_bounds(x, split_y - 1)
            and game_map.tiles["walkable"][x, split_y - 1]
            and game_map.in_bounds(x, split_y + 1)
            and game_map.tiles["walkable"][x, split_y + 1]
        )
    ]
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
    inner_w = x2 - x1 - 1
    inner_h = y2 - y1 - 1

    # Min sub-room interior 3×3 → each half needs outer width ≥ 4 → min_offset 4
    min_offset = 4
    can_split_v = inner_w >= (min_offset * 2 - 1)  # vertical partition (split x)
    can_split_h = inner_h >= (min_offset * 2 - 1)  # horizontal partition (split y)

    # Base case: single room
    if num_rooms <= 1 or (not can_split_v and not can_split_h):
        _carve_room_interior(game_map, x1, y1, x2, y2, floor_tile)
        return [RectRoom(x1, y1, x2 - x1, y2 - y1, label=label)]

    # Choose split axis from viable options; prefer longer dimension
    if can_split_v and can_split_h:
        if inner_w > inner_h:
            axis = "vertical"
        elif inner_h > inner_w:
            axis = "horizontal"
        else:
            axis = rng.choice(["vertical", "horizontal"])
    elif can_split_v:
        axis = "vertical"
    else:
        axis = "horizontal"

    if axis == "vertical":
        lo = x1 + min_offset
        hi = x2 - min_offset

        # Asymmetric split: when we need >2 rooms, push the partition
        # toward one side so the larger half can subdivide further.
        if num_rooms > 2:
            if rng.random() < 0.5:
                split_x = lo  # small left, big right
            else:
                split_x = hi  # big left, small right
        else:
            split_x = rng.randint(lo, hi)

        # Draw partition wall
        for by in range(y1 + 1, y2):
            if game_map.in_bounds(split_x, by):
                game_map.tiles[split_x, by] = wall_tile

        # Assign room counts: give 1 to the smaller half, rest to the bigger
        left_w = split_x - x1
        right_w = x2 - split_x
        if left_w >= right_w:
            left_count = num_rooms - 1
            right_count = 1
        else:
            left_count = 1
            right_count = num_rooms - 1
        # For 2-room case keep even split
        if num_rooms == 2:
            left_count = right_count = 1

        left_rooms = _subdivide_building(
            game_map,
            rng,
            x1,
            y1,
            split_x,
            y2,
            left_count,
            floor_tile,
            wall_tile,
            label,
        )
        right_rooms = _subdivide_building(
            game_map,
            rng,
            split_x,
            y1,
            x2,
            y2,
            right_count,
            floor_tile,
            wall_tile,
            label,
        )

        # Carve a 1-tile doorway, preferring positions with floor on both sides
        door_y = _find_door_position_v(game_map, rng, split_x, y1, y2)
        if door_y is not None:
            game_map.tiles[split_x, door_y] = floor_tile
            # Only force-clear a side if it's still walled (perpendicular partition)
            # but never breach the building's outer boundary walls
            if (
                split_x - 1 > x1
                and game_map.in_bounds(split_x - 1, door_y)
                and not game_map.tiles["walkable"][split_x - 1, door_y]
            ):
                game_map.tiles[split_x - 1, door_y] = floor_tile
            if (
                split_x + 1 < x2
                and game_map.in_bounds(split_x + 1, door_y)
                and not game_map.tiles["walkable"][split_x + 1, door_y]
            ):
                game_map.tiles[split_x + 1, door_y] = floor_tile

        return left_rooms + right_rooms

    else:  # horizontal
        lo = y1 + min_offset
        hi = y2 - min_offset

        if num_rooms > 2:
            if rng.random() < 0.5:
                split_y = lo
            else:
                split_y = hi
        else:
            split_y = rng.randint(lo, hi)

        for bx in range(x1 + 1, x2):
            if game_map.in_bounds(bx, split_y):
                game_map.tiles[bx, split_y] = wall_tile

        top_h = split_y - y1
        bot_h = y2 - split_y
        if top_h >= bot_h:
            top_count = num_rooms - 1
            bot_count = 1
        else:
            top_count = 1
            bot_count = num_rooms - 1
        if num_rooms == 2:
            top_count = bot_count = 1

        top_rooms = _subdivide_building(
            game_map,
            rng,
            x1,
            y1,
            x2,
            split_y,
            top_count,
            floor_tile,
            wall_tile,
            label,
        )
        bot_rooms = _subdivide_building(
            game_map,
            rng,
            x1,
            split_y,
            x2,
            y2,
            bot_count,
            floor_tile,
            wall_tile,
            label,
        )

        door_x = _find_door_position_h(game_map, rng, split_y, x1, x2)
        if door_x is not None:
            game_map.tiles[door_x, split_y] = floor_tile
            # Never breach the building's outer boundary walls
            if (
                split_y - 1 > y1
                and game_map.in_bounds(door_x, split_y - 1)
                and not game_map.tiles["walkable"][door_x, split_y - 1]
            ):
                game_map.tiles[door_x, split_y - 1] = floor_tile
            if (
                split_y + 1 < y2
                and game_map.in_bounds(door_x, split_y + 1)
                and not game_map.tiles["walkable"][door_x, split_y + 1]
            ):
                game_map.tiles[door_x, split_y + 1] = floor_tile

        return top_rooms + bot_rooms


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

    def _clear_if_blocked(x: int, y: int) -> None:
        if game_map.in_bounds(x, y) and not game_map.tiles["walkable"][x, y]:
            game_map.tiles[x, y] = floor_tile

    # A's east wall == B's west wall (x2a == x1b)
    if wing_a.x2 == wing_b.x1:
        y_lo = max(wing_a.y1 + 1, wing_b.y1 + 1)
        y_hi = min(wing_a.y2 - 1, wing_b.y2 - 1)
        if y_lo <= y_hi:
            door_y = (y_lo + y_hi) // 2
            x = wing_a.x2
            if game_map.in_bounds(x, door_y):
                game_map.tiles[x, door_y] = floor_tile
            _clear_if_blocked(x - 1, door_y)
            _clear_if_blocked(x + 1, door_y)
            return

    # A's west wall == B's east wall (x1a == x2b)
    if wing_a.x1 == wing_b.x2:
        y_lo = max(wing_a.y1 + 1, wing_b.y1 + 1)
        y_hi = min(wing_a.y2 - 1, wing_b.y2 - 1)
        if y_lo <= y_hi:
            door_y = (y_lo + y_hi) // 2
            x = wing_a.x1
            if game_map.in_bounds(x, door_y):
                game_map.tiles[x, door_y] = floor_tile
            _clear_if_blocked(x - 1, door_y)
            _clear_if_blocked(x + 1, door_y)
            return

    # A's south wall == B's north wall (y2a == y1b)
    if wing_a.y2 == wing_b.y1:
        x_lo = max(wing_a.x1 + 1, wing_b.x1 + 1)
        x_hi = min(wing_a.x2 - 1, wing_b.x2 - 1)
        if x_lo <= x_hi:
            door_x = (x_lo + x_hi) // 2
            y = wing_a.y2
            if game_map.in_bounds(door_x, y):
                game_map.tiles[door_x, y] = floor_tile
            _clear_if_blocked(door_x, y - 1)
            _clear_if_blocked(door_x, y + 1)
            return

    # A's north wall == B's south wall (y1a == y2b)
    if wing_a.y1 == wing_b.y2:
        x_lo = max(wing_a.x1 + 1, wing_b.x1 + 1)
        x_hi = min(wing_a.x2 - 1, wing_b.x2 - 1)
        if x_lo <= x_hi:
            door_x = (x_lo + x_hi) // 2
            y = wing_a.y1
            if game_map.in_bounds(door_x, y):
                game_map.tiles[door_x, y] = floor_tile
            _clear_if_blocked(door_x, y - 1)
            _clear_if_blocked(door_x, y + 1)
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

    # Collect all wall tiles across all wings with their inward direction
    # Each entry: (wall_pos, inside_pos, outside_pos)
    door_candidates: list[tuple[tuple[int, int], tuple[int, int], tuple[int, int]]] = []
    for wing in wing_rooms:
        # North wall
        for x in range(wing.x1 + 1, wing.x2):
            wall = (x, wing.y1)
            inside = (x, wing.y1 + 1)
            outside = (x, wing.y1 - 1)
            if game_map.in_bounds(*outside) and int(game_map.tiles["tile_id"][outside[0], outside[1]]) == ground_tid:
                door_candidates.append((wall, inside, outside))
        # South wall
        for x in range(wing.x1 + 1, wing.x2):
            wall = (x, wing.y2)
            inside = (x, wing.y2 - 1)
            outside = (x, wing.y2 + 1)
            if game_map.in_bounds(*outside) and int(game_map.tiles["tile_id"][outside[0], outside[1]]) == ground_tid:
                door_candidates.append((wall, inside, outside))
        # West wall
        for y in range(wing.y1 + 1, wing.y2):
            wall = (wing.x1, y)
            inside = (wing.x1 + 1, y)
            outside = (wing.x1 - 1, y)
            if game_map.in_bounds(*outside) and int(game_map.tiles["tile_id"][outside[0], outside[1]]) == ground_tid:
                door_candidates.append((wall, inside, outside))
        # East wall
        for y in range(wing.y1 + 1, wing.y2):
            wall = (wing.x2, y)
            inside = (wing.x2 - 1, y)
            outside = (wing.x2 + 1, y)
            if game_map.in_bounds(*outside) and int(game_map.tiles["tile_id"][outside[0], outside[1]]) == ground_tid:
                door_candidates.append((wall, inside, outside))

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
