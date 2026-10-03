"""Hull exterior: airlocks, hull breaches and converting outer hull walls to space."""

from __future__ import annotations

import random

import numpy as np

from world import tile_types
from world.dungeon_gen.rooms import RectRoom, _room_wall_positions
from world.game_map import GameMap
from world.grid import DIAGONALS, NEIGHBOURS_8, neighbour_any, neighbour_count


def _place_airlocks(
    game_map: GameMap,
    rng: random.Random,
    rooms: list[RectRoom],
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> None:
    """Place 1-2 airlocks on the hull exterior.

    Each airlock is a 3-tile extension outward from a hull wall:
    [interior_door] [airlock_floor] [exterior_door]
    surrounded by wall tiles to preserve structure during hull conversion.
    Must be called before _convert_hull_to_space().
    """
    wall_tid = int(wall_tile["tile_id"])
    num_airlocks = rng.randint(1, 2)
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]  # N, S, W, E

    # Collect all walkable positions (room interiors + corridors)
    walkable_mask = game_map.tiles["walkable"]

    candidates: list[tuple] = []  # (wall_x, wall_y, dx, dy)

    for room in rooms:
        for wx, wy in _room_wall_positions(room):
            if not game_map.in_bounds(wx, wy):
                continue
            if int(game_map.tiles["tile_id"][wx, wy]) != wall_tid:
                continue
            for dx, dy in directions:
                # Interior side: tile inside the room (opposite of outward direction)
                ix, iy = wx - dx, wy - dy
                if not game_map.in_bounds(ix, iy):
                    continue
                if not walkable_mask[ix, iy]:
                    continue

                # The 3 outward tiles: wall pos (becomes interior door),
                # wall+1*dir (airlock floor), wall+2*dir (exterior door)
                positions = [(wx + i * dx, wy + i * dy) for i in range(3)]
                # All 3 must be in bounds and currently wall tiles
                valid = True
                for px, py in positions:
                    if not game_map.in_bounds(px, py):
                        valid = False
                        break
                    if int(game_map.tiles["tile_id"][px, py]) != wall_tid:
                        valid = False
                        break
                if not valid:
                    continue

                # Perpendicular directions for wall checks
                if dx == 0:
                    perp = [(1, 0), (-1, 0)]
                else:
                    perp = [(0, 1), (0, -1)]

                # The tile beyond the exterior door must be wall (will become space),
                # and its perpendicular neighbors must also be wall to avoid
                # creating space tiles adjacent to walkable corridors/rooms.
                bx, by = wx + 3 * dx, wy + 3 * dy
                if not game_map.in_bounds(bx, by):
                    continue
                if int(game_map.tiles["tile_id"][bx, by]) != wall_tid:
                    continue
                # Check all cardinal neighbors of beyond-tile are wall
                beyond_ok = True
                for cdx, cdy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                    bnx, bny = bx + cdx, by + cdy
                    # Skip the exterior door direction (back toward airlock)
                    if (cdx, cdy) == (-dx, -dy):
                        continue
                    if not game_map.in_bounds(bnx, bny):
                        beyond_ok = False
                        break
                    if int(game_map.tiles["tile_id"][bnx, bny]) != wall_tid:
                        beyond_ok = False
                        break
                if not beyond_ok:
                    continue

                # Check that surrounding wall tiles exist for chamber walls
                # (perpendicular neighbors of the airlock tiles must be wall)
                walls_ok = True
                for px, py in positions:
                    for pdx, pdy in perp:
                        nx, ny = px + pdx, py + pdy
                        if not game_map.in_bounds(nx, ny):
                            walls_ok = False
                            break
                        if int(game_map.tiles["tile_id"][nx, ny]) != wall_tid:
                            walls_ok = False
                            break
                    if not walls_ok:
                        break
                if not walls_ok:
                    continue

                candidates.append((wx, wy, dx, dy))

    rng.shuffle(candidates)
    placed = 0
    used_positions: set = set()

    for wx, wy, dx, dy in candidates:
        if placed >= num_airlocks:
            break

        # Ensure no overlap with already-placed airlocks
        positions = [(wx + i * dx, wy + i * dy) for i in range(3)]
        if any((px, py) in used_positions for px, py in positions):
            continue

        # Carve the airlock
        # Position 0: interior door (at hull wall)
        game_map.tiles[positions[0][0], positions[0][1]] = tile_types.door_closed
        # Position 1: airlock floor
        game_map.tiles[positions[1][0], positions[1][1]] = tile_types.airlock_floor
        # Position 2: exterior door (hull-colored)
        game_map.tiles[positions[2][0], positions[2][1]] = tile_types.airlock_ext_closed

        for px, py in positions:
            used_positions.add((px, py))

        # Place switch on a wall tile cardinally adjacent to the interior door
        door_x, door_y = positions[0]
        switch_pos = None
        for sdx, sdy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            sx, sy = door_x + sdx, door_y + sdy
            if not game_map.in_bounds(sx, sy):
                continue
            if (sx, sy) in used_positions:
                continue
            stid = int(game_map.tiles["tile_id"][sx, sy])
            if stid != wall_tid:
                continue
            switch_pos = (sx, sy)
            break

        if switch_pos:
            game_map.tiles[switch_pos[0], switch_pos[1]] = tile_types.airlock_switch_off
            used_positions.add(switch_pos)

        game_map.airlocks.append(
            {
                "interior_door": positions[0],
                "exterior_door": positions[2],
                "direction": (dx, dy),
                "switch": switch_pos,
            }
        )
        placed += 1


def _enforce_airlock_walls(game_map: GameMap, wall_tile: np.ndarray) -> None:
    """Restore wall tiles around airlock corridors.

    Hull cleanup passes may convert perpendicular walls to space, creating
    diagonal gaps that allow movement around airlocks.  This re-stamps
    wall tiles on both perpendicular sides of every airlock tile.
    """
    space_tid = int(tile_types.space["tile_id"])
    for al in game_map.airlocks:
        dx, dy = al["direction"]
        ix, iy = al["interior_door"]
        perps = [(1, 0), (-1, 0)] if dx == 0 else [(0, 1), (0, -1)]
        for i in range(3):
            px, py = ix + i * dx, iy + i * dy
            for pdx, pdy in perps:
                nx, ny = px + pdx, py + pdy
                if not game_map.in_bounds(nx, ny):
                    continue
                if int(game_map.tiles["tile_id"][nx, ny]) == space_tid:
                    game_map.tiles[nx, ny] = wall_tile


def hull_breach_candidates(
    game_map: GameMap,
    wall_tile: np.ndarray,
    *,
    airlock_chambers: bool = True,
) -> list[tuple[int, int]]:
    """Hull tiles a breach could open in, in scan order.

    These are *wall_tile* tiles adjacent to both a space tile and a walkable
    tile (the hull boundary) that nothing is mounted on. With
    ``airlock_chambers=False`` the walkable side must be more than an airlock
    chamber, so the breach always opens into the ship proper.
    """
    space_tid = int(tile_types.space["tile_id"])
    wall_tid = int(wall_tile["tile_id"])
    airlock_tid = int(tile_types.airlock_floor["tile_id"])
    entity_positions = {(e.x, e.y) for e in game_map.entities}
    candidates: list[tuple[int, int]] = []

    for x in range(1, game_map.width - 1):
        for y in range(1, game_map.height - 1):
            if int(game_map.tiles["tile_id"][x, y]) != wall_tid:
                continue
            has_space = False
            has_walkable = False
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not game_map.in_bounds(nx, ny):
                    continue
                tid = int(game_map.tiles["tile_id"][nx, ny])
                if tid == space_tid:
                    has_space = True
                if bool(game_map.tiles["walkable"][nx, ny]) and (airlock_chambers or tid != airlock_tid):
                    has_walkable = True
            if has_space and has_walkable and (x, y) not in entity_positions:
                candidates.append((x, y))
    return candidates


def _place_hull_breaches(
    game_map: GameMap,
    rng: random.Random,
    wall_tile: np.ndarray,
) -> None:
    """Place 1-3 hull breaches on a derelict/ship map."""
    candidates = hull_breach_candidates(game_map, wall_tile)
    if not candidates:
        return
    count = min(rng.randint(1, 3), len(candidates))
    chosen = rng.sample(candidates, count)
    for bx, by in chosen:
        game_map.tiles[bx, by] = tile_types.hull_breach
        game_map.hull_breaches.append((bx, by))


def _place_asteroid_breaches(
    game_map: GameMap,
    rng: random.Random,
) -> None:
    """Place 1-2 hull breaches on an asteroid/cave map.

    Finds rock_wall tiles at the map perimeter adjacent to interior walkable
    tiles, replaces them with hull_breach, and converts the tile beyond the
    breach to space.
    """
    rock_wall_tid = int(tile_types.rock_wall["tile_id"])
    candidates: list[tuple[int, int, int, int]] = []  # (x, y, beyond_x, beyond_y)

    for x in range(game_map.width):
        for y in range(game_map.height):
            if int(game_map.tiles["tile_id"][x, y]) != rock_wall_tid:
                continue
            # Must be at map perimeter or adjacent to map edge
            at_edge = x <= 1 or x >= game_map.width - 2 or y <= 1 or y >= game_map.height - 2
            if not at_edge:
                continue
            # Check for adjacent interior walkable tile and a direction for space
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                bx, by = x - dx, y - dy  # beyond = opposite direction
                if not game_map.in_bounds(nx, ny):
                    continue
                if not game_map.in_bounds(bx, by):
                    continue
                if bool(game_map.tiles["walkable"][nx, ny]):
                    candidates.append((x, y, bx, by))
                    break

    if not candidates:
        return

    count = min(rng.randint(1, 2), len(candidates))
    chosen = rng.sample(candidates, count)
    for bx, by, sx, sy in chosen:
        game_map.tiles[bx, by] = tile_types.hull_breach
        game_map.hull_breaches.append((bx, by))
        game_map.tiles[sx, sy] = tile_types.space
    game_map.has_space = True


def _convert_hull_to_space(game_map: GameMap, wall_tile: np.ndarray) -> None:
    """Replace wall tiles not adjacent to any walkable or window tile with space.

    Uses numpy array shifts for vectorized adjacency checking (no Python loops).
    Walls adjacent (8-directional) to walkable or window tiles are structural
    hull and kept.  Then a cleanup pass converts hull filler behind exterior
    windows (adjacent to a window but not to any walkable tile) to space so
    that windows actually provide a view into space.
    """
    wall_tid = int(wall_tile["tile_id"])
    window_tid = int(tile_types.structure_window["tile_id"])

    is_wall = game_map.tiles["tile_id"] == wall_tid
    is_walkable = game_map.tiles["walkable"].copy()
    is_window = game_map.tiles["tile_id"] == window_tid

    # A tile is "interesting" if walkable or a window
    interesting = is_walkable | is_window

    # Check adjacency to interesting tiles in all 8 directions
    # (diagonal checks prevent corner gaps that allow FOV peek-through)
    adj = neighbour_any(interesting, NEIGHBOURS_8)

    # Wall tiles NOT adjacent to anything interesting become space
    to_space = is_wall & ~adj
    game_map.tiles[to_space] = tile_types.space

    # Cleanup: walls adjacent to windows but not to any walkable tile are
    # hull filler behind exterior windows - convert to space so windows
    # actually look out into space.
    is_wall_now = game_map.tiles["tile_id"] == wall_tid
    is_window_now = game_map.tiles["tile_id"] == window_tid

    adj_walkable = neighbour_any(is_walkable)

    adj_window = neighbour_any(is_window_now)

    hull_filler = is_wall_now & adj_window & ~adj_walkable
    game_map.tiles[hull_filler] = tile_types.space

    # Second cleanup: walls only diagonally adjacent to a window (corner "ears")
    # that are not cardinally adjacent to any walkable or window tile.
    is_wall_now2 = game_map.tiles["tile_id"] == wall_tid
    is_window_now2 = game_map.tiles["tile_id"] == window_tid
    is_walkable2 = game_map.tiles["walkable"].copy()
    cardinal_interesting = neighbour_any(is_walkable2 | is_window_now2)
    diag_window = neighbour_any(is_window_now2, DIAGONALS)
    corner_ears = is_wall_now2 & diag_window & ~cardinal_interesting
    game_map.tiles[corner_ears] = tile_types.space

    # Third cleanup: iteratively remove wall stubs (wall tiles with 3+ space
    # cardinal neighbors) until none remain.
    space_tid = int(tile_types.space["tile_id"])
    for _ in range(5):
        is_wall_pass = game_map.tiles["tile_id"] == wall_tid
        is_space = game_map.tiles["tile_id"] == space_tid
        space_neighbors = neighbour_count(is_space)
        stubs = is_wall_pass & (space_neighbors >= 3)
        if not np.any(stubs):
            break
        game_map.tiles[stubs] = tile_types.space
