"""Grid primitives shared by hazards, decompression, corridor routing and hull cleanup."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from world.game_map import GameMap

type Pos = tuple[int, int]

# Expansion order is part of the contract: pull directions and corridor
# routes are whichever neighbour reaches a tile first.
CARDINALS: tuple[Pos, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONALS: tuple[Pos, ...] = ((-1, -1), (-1, 1), (1, -1), (1, 1))
NEIGHBOURS_8: tuple[Pos, ...] = CARDINALS + DIAGONALS


def bfs(
    sources: Iterable[Pos],
    passable: Callable[[int, int], bool],
    *,
    max_distance: int | None = None,
) -> tuple[dict[Pos, int], dict[Pos, Pos | None]]:
    """4-connected breadth-first search from *sources* through *passable* tiles.

    Returns ``(distance, parent)``. Sources are always included, at distance 0
    with parent ``None``, whether or not they are passable themselves.
    """
    distance: dict[Pos, int] = {}
    parent: dict[Pos, Pos | None] = {}
    queue: deque[Pos] = deque()
    for source in sources:
        if source not in distance:
            distance[source] = 0
            parent[source] = None
            queue.append(source)

    while queue:
        current = queue.popleft()
        steps = distance[current]
        if max_distance is not None and steps >= max_distance:
            continue
        for dx, dy in CARDINALS:
            neighbour = (current[0] + dx, current[1] + dy)
            if neighbour in distance or not passable(*neighbour):
                continue
            distance[neighbour] = steps + 1
            parent[neighbour] = current
            queue.append(neighbour)
    return distance, parent


def path_to(parent: dict[Pos, Pos | None], goal: Pos) -> list[Pos] | None:
    """The route from a source to *goal* recorded in *parent*, or None if the search never reached it."""
    if goal not in parent:
        return None
    path: list[Pos] = []
    node: Pos | None = goal
    while node is not None:
        path.append(node)
        node = parent[node]
    path.reverse()
    return path


def walkable(game_map: GameMap) -> Callable[[int, int], bool]:
    """A *passable* predicate for in-bounds walkable tiles of *game_map*."""
    tiles = game_map.tiles["walkable"]
    return lambda x, y: game_map.in_bounds(x, y) and bool(tiles[x, y])


def flood_fill_walkable(game_map: GameMap, sources: list[Pos]) -> np.ndarray:
    """Bool array (width, height) of tiles reachable from in-bounds *sources* over walkable tiles."""
    result = np.full((game_map.width, game_map.height), fill_value=False, order="F")
    starts = [s for s in sources if game_map.in_bounds(*s)]
    distance, _ = bfs(starts, walkable(game_map))
    for x, y in distance:
        result[x, y] = True
    return result


def _neighbour(mask: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """out[x, y] = mask[x + dx, y + dy], False where that falls off the grid."""
    w, h = mask.shape
    out = np.zeros_like(mask)
    dst_x, src_x = slice(max(-dx, 0), w - max(dx, 0)), slice(max(dx, 0), w - max(-dx, 0))
    dst_y, src_y = slice(max(-dy, 0), h - max(dy, 0)), slice(max(dy, 0), h - max(-dy, 0))
    out[dst_x, dst_y] = mask[src_x, src_y]
    return out


def neighbour_any(mask: np.ndarray, offsets: Iterable[Pos] = CARDINALS) -> np.ndarray:
    """True where any neighbour at *offsets* is set in *mask*."""
    result = np.zeros(mask.shape, dtype=bool)
    for dx, dy in offsets:
        result |= _neighbour(mask, dx, dy).astype(bool)
    return result


def neighbour_count(mask: np.ndarray, offsets: Iterable[Pos] = CARDINALS) -> np.ndarray:
    """How many neighbours at *offsets* are set in *mask*, per cell."""
    result = np.zeros(mask.shape, dtype=int)
    for dx, dy in offsets:
        result += _neighbour(mask, dx, dy)
    return result
