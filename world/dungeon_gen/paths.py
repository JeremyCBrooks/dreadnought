"""Grid pathfinding used to lay village paths."""

from __future__ import annotations

import heapq
import random

from world import tile_types
from world.game_map import GameMap


def _wall_adjacent_set(game_map: GameMap, ground_tid: int) -> set:
    """Return set of ground tiles with at least one cardinal wall neighbor."""
    w, h = game_map.width, game_map.height
    wall_tid = int(tile_types.structure_wall["tile_id"])
    result: set = set()
    for x in range(w):
        for y in range(h):
            if int(game_map.tiles["tile_id"][x, y]) != ground_tid:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and int(game_map.tiles["tile_id"][nx, ny]) == wall_tid:
                    result.add((x, y))
                    break
    return result


def _bfs_path(
    game_map: GameMap,
    start: tuple[int, int],
    end: tuple[int, int],
    ground_tid: int,
    extra_walkable: set | None = None,
    wall_cost: int = 3,
) -> list[tuple[int, int]]:
    """Dijkstra shortest path from *start* to *end* through ground tiles.

    *extra_walkable* tiles may be traversed but are NOT target destinations.
    Delegates to ``_bfs_to_set`` with *end* as the sole target.
    """
    extra = extra_walkable or set()
    return _bfs_to_set(
        game_map,
        start,
        {end},
        ground_tid,
        wall_cost,
        extra_walkable=extra,
    )


def _bfs_to_set(
    game_map: GameMap,
    start: tuple[int, int],
    targets: set,
    ground_tid: int,
    wall_cost: int = 3,
    extra_walkable: set | None = None,
) -> list[tuple[int, int]]:
    """Dijkstra from *start* to the nearest coordinate in *targets*.

    *extra_walkable* tiles may be traversed but are not destinations.
    Wall-adjacent tiles cost *wall_cost* to traverse.  Returns ordered path,
    or [] if unreachable.
    """
    if start in targets:
        return [start]
    w, h = game_map.width, game_map.height
    sx, sy = start
    if not (0 <= sx < w and 0 <= sy < h):
        return []
    walkable = targets | (extra_walkable or set())
    wall_adj = _wall_adjacent_set(game_map, ground_tid)
    heap: list[tuple[int, int, int]] = [(0, sx, sy)]
    best_cost: dict[tuple[int, int], int] = {start: 0}
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while heap:
        cost, cx, cy = heapq.heappop(heap)
        if (cx, cy) in targets:
            path: list[tuple[int, int]] = []
            cur: tuple[int, int] | None = (cx, cy)
            while cur is not None:
                path.append(cur)
                cur = came_from[cur]
            path.reverse()
            return path
        if cost > best_cost.get((cx, cy), float("inf")):
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if (nx, ny) not in walkable and int(game_map.tiles["tile_id"][nx, ny]) != ground_tid:
                continue
            step = wall_cost if (nx, ny) in wall_adj else 1
            new_cost = cost + step
            if new_cost < best_cost.get((nx, ny), float("inf")):
                best_cost[(nx, ny)] = new_cost
                came_from[(nx, ny)] = (cx, cy)
                heapq.heappush(heap, (new_cost, nx, ny))
    return []


def _meander(
    rng: random.Random,
    path: list[tuple[int, int]],
    game_map: GameMap,
    ground_tid: int,
    freq: int = 6,
) -> list[tuple[int, int]]:
    """Add gentle lateral wobble to a path for organic feel.

    Every *freq* tiles, attempt a 1-tile lateral jog: step sideways from
    the previous tile, then forward to the current tile.  Both inserted tiles
    must be ground, in bounds, and not adjacent to any wall.  In tight spaces
    (corridors, wall-adjacent areas) the offset is simply skipped.
    """
    if len(path) < 3:
        return list(path)
    w, h = game_map.width, game_map.height
    wall_tid = int(tile_types.structure_wall["tile_id"])

    def _is_wall_adjacent(x: int, y: int) -> bool:
        for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + ddx, y + ddy
            if 0 <= nx < w and 0 <= ny < h:
                if int(game_map.tiles["tile_id"][nx, ny]) == wall_tid:
                    return True
        return False

    def _is_valid_offset(x: int, y: int) -> bool:
        if not (0 < x < w - 1 and 0 < y < h - 1):
            return False
        if int(game_map.tiles["tile_id"][x, y]) != ground_tid:
            return False
        if _is_wall_adjacent(x, y):
            return False
        return True

    result: list[tuple[int, int]] = [path[0]]
    for i in range(1, len(path)):
        if i % freq == 0 and i < len(path) - 1:
            px, py = path[i - 1]
            cx, cy = path[i]
            dx, dy = cx - px, cy - py
            # Lateral direction (perpendicular to travel)
            if dx != 0:
                offsets = [(0, -1), (0, 1)]
            elif dy != 0:
                offsets = [(-1, 0), (1, 0)]
            else:
                offsets = []
            rng.shuffle(offsets)
            for ox, oy in offsets:
                # Two-tile jog: prev+lateral, then current+lateral (=prev+lateral+forward)
                # Step 1: from prev, go lateral
                s1x, s1y = px + ox, py + oy
                # Step 2: from step1, go forward (same direction as travel)
                s2x, s2y = s1x + dx, s1y + dy
                # s2 must be adjacent to current tile
                if abs(s2x - cx) + abs(s2y - cy) != 1:
                    continue
                if _is_valid_offset(s1x, s1y) and _is_valid_offset(s2x, s2y):
                    result.append((s1x, s1y))
                    result.append((s2x, s2y))
                    break
        result.append(path[i])
    return result
