"""Corridor and tunnel carving."""

from __future__ import annotations

import random

import numpy as np

from world import tile_types
from world.game_map import GameMap


def _carve_h_tunnel(
    game_map: GameMap,
    x1: int,
    x2: int,
    y: int,
    floor_tile: np.ndarray | None = None,
) -> None:
    ft = floor_tile if floor_tile is not None else tile_types.floor
    for x in range(min(x1, x2), max(x1, x2) + 1):
        if game_map.in_bounds(x, y):
            game_map.tiles[x, y] = ft


def _carve_v_tunnel(
    game_map: GameMap,
    y1: int,
    y2: int,
    x: int,
    floor_tile: np.ndarray | None = None,
) -> None:
    ft = floor_tile if floor_tile is not None else tile_types.floor
    for y in range(min(y1, y2), max(y1, y2) + 1):
        if game_map.in_bounds(x, y):
            game_map.tiles[x, y] = ft


def _carve_wide_h_tunnel(
    game_map: GameMap,
    x1: int,
    x2: int,
    y: int,
    floor_tile: np.ndarray | None = None,
) -> None:
    """Carve a 2-tile wide horizontal corridor."""
    _carve_h_tunnel(game_map, x1, x2, y, floor_tile)
    if y + 1 < game_map.height:
        _carve_h_tunnel(game_map, x1, x2, y + 1, floor_tile)


def _carve_wide_v_tunnel(
    game_map: GameMap,
    y1: int,
    y2: int,
    x: int,
    floor_tile: np.ndarray | None = None,
) -> None:
    """Carve a 2-tile wide vertical corridor."""
    _carve_v_tunnel(game_map, y1, y2, x, floor_tile)
    if x + 1 < game_map.width:
        _carve_v_tunnel(game_map, y1, y2, x + 1, floor_tile)


def _connect_l_corridor(
    game_map: GameMap,
    rng: random.Random,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    floor_tile: np.ndarray | None = None,
    wide: bool = False,
) -> None:
    """Connect two points with a randomly-oriented L-shaped corridor."""
    carve_h = _carve_wide_h_tunnel if wide else _carve_h_tunnel
    carve_v = _carve_wide_v_tunnel if wide else _carve_v_tunnel
    if rng.random() < 0.5:
        carve_h(game_map, x1, x2, y1, floor_tile)
        carve_v(game_map, y1, y2, x2, floor_tile)
    else:
        carve_v(game_map, y1, y2, x1, floor_tile)
        carve_h(game_map, x1, x2, y2, floor_tile)


def _carve_winding_tunnel(
    game_map: GameMap,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    rng: random.Random,
    floor_tile: np.ndarray | None = None,
) -> None:
    """Biased drunkard's walk from (x1,y1) to (x2,y2)."""
    ft = floor_tile if floor_tile is not None else tile_types.floor
    cx, cy = x1, y1
    max_steps = 3 * (abs(x2 - x1) + abs(y2 - y1))
    max_steps = max(max_steps, 10)

    for _ in range(max_steps):
        if game_map.in_bounds(cx, cy):
            game_map.tiles[cx, cy] = ft
        if cx == x2 and cy == y2:
            return

        roll = rng.random()
        if roll < 0.60:
            # Move toward target
            dx = 1 if x2 > cx else (-1 if x2 < cx else 0)
            dy = 1 if y2 > cy else (-1 if y2 < cy else 0)
            if rng.random() < 0.5 and dx != 0:
                cx += dx
            elif dy != 0:
                cy += dy
            elif dx != 0:
                cx += dx
        elif roll < 0.90:
            # Move perpendicular
            dx = 1 if x2 > cx else (-1 if x2 < cx else 0)
            dy = 1 if y2 > cy else (-1 if y2 < cy else 0)
            if dx != 0 and dy != 0:
                if rng.random() < 0.5:
                    cy += rng.choice([-1, 1])
                else:
                    cx += rng.choice([-1, 1])
            elif dx != 0:
                cy += rng.choice([-1, 1])
            else:
                cx += rng.choice([-1, 1])
        # else: 10% pause — no move

        # 15% chance to carve a 3x3 alcove
        if rng.random() < 0.15:
            for ax in range(cx - 1, cx + 2):
                for ay in range(cy - 1, cy + 2):
                    if game_map.in_bounds(ax, ay):
                        game_map.tiles[ax, ay] = ft

        cx = max(1, min(cx, game_map.width - 2))
        cy = max(1, min(cy, game_map.height - 2))

    # Fallback: straight corridors if we didn't reach target
    _carve_h_tunnel(game_map, cx, x2, cy, ft)
    _carve_v_tunnel(game_map, cy, y2, x2, ft)
