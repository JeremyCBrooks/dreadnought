"""Door placement at room entrances."""

from __future__ import annotations

import random

import numpy as np

from world import tile_types
from world.dungeon_gen.rooms import RectRoom
from world.game_map import GameMap


def _is_room_adjacent(x: int, y: int, rooms: list[RectRoom]) -> bool:
    """Return True if (x, y) is cardinally adjacent to any room's inner area."""
    for room in rooms:
        ix, iy = room.inner
        # Check if any cardinal neighbor falls inside the room interior
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            if ix.start <= nx < ix.stop and iy.start <= ny < iy.stop:
                return True
    return False


def _place_doors(
    game_map: GameMap,
    rng: random.Random,
    floor_tile: np.ndarray,
    rooms: list[RectRoom],
    door_chance: float = 0.65,
    min_spacing: int = 3,
) -> None:
    """Place closed doors at room entrances — chokepoints adjacent to a room's
    inner area, with minimum spacing to avoid door clusters."""
    floor_tid = int(floor_tile["tile_id"])
    w, h = game_map.width, game_map.height

    candidates: list[tuple[int, int]] = []
    for x in range(1, w - 1):
        for y in range(1, h - 1):
            if int(game_map.tiles["tile_id"][x, y]) != floor_tid:
                continue
            n = bool(game_map.tiles["walkable"][x, y - 1])
            s = bool(game_map.tiles["walkable"][x, y + 1])
            e = bool(game_map.tiles["walkable"][x + 1, y])
            w_ = bool(game_map.tiles["walkable"][x - 1, y])

            is_chokepoint = False
            # Vertical chokepoint: walls E+W, floor N+S
            if not e and not w_ and n and s:
                is_chokepoint = True
            # Horizontal chokepoint: walls N+S, floor E+W
            elif not n and not s and e and w_:
                is_chokepoint = True

            if is_chokepoint and _is_room_adjacent(x, y, rooms):
                candidates.append((x, y))

    # Place doors with minimum spacing
    placed: list[tuple[int, int]] = []
    entity_positions = {(e.x, e.y) for e in game_map.entities}
    rng.shuffle(candidates)
    for x, y in candidates:
        if rng.random() >= door_chance:
            continue
        if (x, y) in entity_positions:
            continue
        # Enforce minimum spacing from already-placed doors
        too_close = False
        for px, py in placed:
            if abs(x - px) + abs(y - py) < min_spacing:
                too_close = True
                break
        if not too_close:
            game_map.tiles[x, y] = tile_types.door_closed
            placed.append((x, y))
