"""Cosmetic variation for ship and starbase maps: patina, debris, scorch marks, bloodstains."""

from __future__ import annotations

import random

import numpy as np

from world import tile_types
from world.game_map import GameMap


def _value_noise_2d(
    width: int,
    height: int,
    rng: random.Random,
    cell_size: int = 6,
) -> np.ndarray:
    """Generate smooth 2D value noise in [0, 1] via bilinear interpolation."""
    gw = width // cell_size + 2
    gh = height // cell_size + 2
    grid = np.array([[rng.random() for _ in range(gh)] for _ in range(gw)])

    result = np.empty((width, height), dtype=np.float64)
    for x in range(width):
        gx = x / cell_size
        ix = int(gx)
        fx = gx - ix
        for y in range(height):
            gy = y / cell_size
            iy = int(gy)
            fy = gy - iy
            # Bilinear interpolation
            v00 = grid[ix, iy]
            v10 = grid[ix + 1, iy]
            v01 = grid[ix, iy + 1]
            v11 = grid[ix + 1, iy + 1]
            v0 = v00 + (v10 - v00) * fx
            v1 = v01 + (v11 - v01) * fx
            result[x, y] = v0 + (v1 - v0) * fy
    return result


def _apply_hull_patina(
    game_map: GameMap,
    rng: random.Random,
    wall_tile: np.ndarray,
    damage_level: float = 1.0,
) -> None:
    """Apply smooth color variation to wall tiles for a weathered hull look.

    Uses value noise to create panel-sized patches of lighter/darker metal
    with slight warm (rust) or cool (steel) tint shifts.  *damage_level*
    (0.0 = pristine, 1.0 = wrecked) scales the intensity.
    """
    wall_tid = int(wall_tile["tile_id"])
    is_wall = game_map.tiles["tile_id"] == wall_tid
    if not np.any(is_wall):
        return

    # Brightness noise: small cells so variation is visible on short wall runs
    brightness = _value_noise_2d(game_map.width, game_map.height, rng, cell_size=3)
    # Scale brightness range by damage: pristine ±15, wrecked ±50
    amplitude = 30 + 70 * damage_level
    bright_offset = ((brightness - 0.5) * amplitude).astype(np.int16)

    # Tint noise: separate pass with larger cells for rust vs steel patches
    tint = _value_noise_2d(game_map.width, game_map.height, rng, cell_size=6)

    for layer in ("dark", "light", "lit"):
        fg = game_map.tiles[layer]["fg"]
        bg = game_map.tiles[layer]["bg"]
        scale = 1.0 if layer == "light" else (0.7 if layer == "lit" else 0.5)
        offset = (bright_offset * scale).astype(np.int16)

        # Tint: values < 0.4 lean warm (rust), > 0.6 lean cool (steel)
        warm = (tint < 0.4) & is_wall
        cool = (tint > 0.6) & is_wall

        for ch in range(3):
            fg_ch = fg[..., ch].astype(np.int16)
            bg_ch = bg[..., ch].astype(np.int16)

            fg_ch[is_wall] += offset[is_wall]
            bg_ch[is_wall] += offset[is_wall] // 2

            # Warm tint: boost red, reduce blue — visible rust patches
            # Scale tint by damage: pristine = subtle steel variation,
            # wrecked = heavy rust/corrosion
            tint_str = 0.3 + 0.7 * damage_level
            if ch == 0:  # red
                fg_ch[warm] += int(20 * scale * tint_str)
                bg_ch[warm] += int(8 * scale * tint_str)
            elif ch == 2:  # blue
                fg_ch[warm] -= int(15 * scale * tint_str)
                bg_ch[warm] -= int(6 * scale * tint_str)

            # Cool tint: boost blue, reduce red — steel patches
            if ch == 2:  # blue
                fg_ch[cool] += int(15 * scale * tint_str)
                bg_ch[cool] += int(6 * scale * tint_str)
            elif ch == 0:  # red
                fg_ch[cool] -= int(10 * scale * tint_str)
                bg_ch[cool] -= int(4 * scale * tint_str)

            fg[..., ch] = np.clip(fg_ch, 0, 255).astype(np.uint8)
            bg[..., ch] = np.clip(bg_ch, 0, 255).astype(np.uint8)


def _scatter_floor_debris(
    game_map: GameMap,
    rng: random.Random,
    floor_tile: np.ndarray,
    damage_level: float = 1.0,
) -> None:
    """Scatter debris characters on floor tiles.

    *damage_level* (0.0 = pristine, 1.0 = wrecked) controls density:
    0.0 means no debris, 1.0 means ~5% seed coverage.
    Uses small clusters so debris looks natural (not uniformly random).
    """
    if damage_level <= 0:
        return
    floor_tid = int(floor_tile["tile_id"])
    is_floor = game_map.tiles["tile_id"] == floor_tid
    floor_positions = list(zip(*np.where(is_floor)))
    if not floor_positions:
        return

    debris_chars = [
        (ord(","), "Loose cable"),
        (ord("'"), "Metal shard"),
        (ord("`"), "Chip of plating"),
        (ord(";"), "Twisted bracket"),
    ]
    # Slightly muted variations of floor colors
    color_shifts = [
        (-20, -20, -10),  # darker/warmer
        (-10, -15, -20),  # darker/cooler
        (10, 5, -10),  # slightly warm
        (-15, -10, -5),  # slightly dim
    ]

    # Seed density scales with damage: 0% at pristine, ~5% at wrecked
    entity_positions = {(e.x, e.y) for e in game_map.entities}
    seed_count = max(1, int(len(floor_positions) * 0.05 * damage_level))
    seeds = rng.sample(floor_positions, min(seed_count, len(floor_positions)))

    for sx, sy in seeds:
        # Small cluster: seed + 0-3 neighbors
        cluster_size = rng.randint(1, 4)
        cluster = [(sx, sy)]
        for _ in range(cluster_size - 1):
            bx, by = cluster[-1]
            dx, dy = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
            nx, ny = bx + dx, by + dy
            if game_map.in_bounds(nx, ny) and int(game_map.tiles["tile_id"][nx, ny]) == floor_tid:
                cluster.append((nx, ny))

        for cx, cy in cluster:
            if (cx, cy) in entity_positions:
                continue
            ch, _ = rng.choice(debris_chars)
            shift = rng.choice(color_shifts)
            for layer in ("dark", "light", "lit"):
                game_map.tiles[layer]["ch"][cx, cy] = ch
                fg = game_map.tiles[layer]["fg"][cx, cy]
                for c in range(3):
                    fg[c] = max(0, min(255, int(fg[c]) + shift[c]))


def _place_scorch_marks(
    game_map: GameMap,
    rng: random.Random,
    floor_tile: np.ndarray,
    wall_tile: np.ndarray | None = None,
) -> None:
    """Darken floor and wall tiles near hull breaches and engine-room reactors."""
    floor_tid = int(floor_tile["tile_id"])
    wall_tid = int(wall_tile["tile_id"]) if wall_tile is not None else -1
    scorch_sources: list[tuple[int, int]] = list(game_map.hull_breaches)

    # Also add reactor cores as scorch sources
    reactor_tid = int(tile_types.reactor_core["tile_id"])
    rxs, rys = np.where(game_map.tiles["tile_id"] == reactor_tid)
    for i in range(len(rxs)):
        scorch_sources.append((int(rxs[i]), int(rys[i])))

    if not scorch_sources:
        return

    scorchable = {floor_tid, wall_tid} - {-1}
    radius = 6
    for sx, sy in scorch_sources:
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                nx, ny = sx + dx, sy + dy
                if not game_map.in_bounds(nx, ny):
                    continue
                tid = int(game_map.tiles["tile_id"][nx, ny])
                if tid not in scorchable:
                    continue
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > radius:
                    continue
                # Stronger darkening closer to source, quadratic falloff
                intensity = (1.0 - (dist / radius)) ** 1.5
                for layer in ("dark", "light", "lit"):
                    fg = game_map.tiles[layer]["fg"][nx, ny]
                    bg = game_map.tiles[layer]["bg"][nx, ny]
                    darken = int(80 * intensity)
                    # Orange/red tint near center, fading to dark gray
                    orange = int(40 * intensity) if dist < radius * 0.5 else 0
                    for c in range(3):
                        tint = orange if c == 0 else 0
                        fg[c] = max(0, int(fg[c]) - darken + tint)
                        bg[c] = max(0, int(bg[c]) - int(darken * 0.6))


def _place_bloodstains(
    game_map: GameMap,
    rng: random.Random,
    floor_tile: np.ndarray,
    damage_level: float = 1.0,
) -> None:
    """Place dark reddish floor stains near enemy spawn positions.

    *damage_level* scales the chance each enemy gets stains.
    """
    if damage_level <= 0:
        return
    floor_tid = int(floor_tile["tile_id"])
    enemies = [e for e in game_map.entities if e.blocks_movement and getattr(e, "fighter", None)]
    if not enemies:
        return

    stain_chars = [ord("."), ord(","), ord("'"), ord("`")]
    stain_chance = 0.6 * damage_level
    for enemy in enemies:
        if rng.random() > stain_chance:
            continue
        count = rng.randint(1, 3)
        for _ in range(count):
            dx = rng.randint(-2, 2)
            dy = rng.randint(-2, 2)
            nx, ny = enemy.x + dx, enemy.y + dy
            if not game_map.in_bounds(nx, ny):
                continue
            if int(game_map.tiles["tile_id"][nx, ny]) != floor_tid:
                continue
            # Dark red tint
            red = rng.randint(100, 140)
            for layer in ("dark", "light", "lit"):
                ch = rng.choice(stain_chars)
                game_map.tiles[layer]["ch"][nx, ny] = ch
                fg = game_map.tiles[layer]["fg"][nx, ny]
                base_brightness = 0.4 if layer == "dark" else (1.0 if layer == "light" else 0.7)
                fg[0] = min(255, int(red * base_brightness) + rng.randint(0, 20))
                fg[1] = max(0, int(fg[1] * 0.3))
                fg[2] = max(0, int(fg[2] * 0.3))


def _apply_ship_cosmetics(
    game_map: GameMap,
    rng: random.Random,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> None:
    """Apply cosmetic variation scaled by damage (hull breach count).

    0 breaches = pristine (subtle patina, no debris/stains).
    3 breaches = fully wrecked (heavy patina, lots of debris/stains).
    """
    breach_count = len(game_map.hull_breaches)
    damage_level = min(1.0, breach_count / 3.0)

    _apply_hull_patina(game_map, rng, wall_tile, damage_level)
    _scatter_floor_debris(game_map, rng, floor_tile, damage_level)
    _place_scorch_marks(game_map, rng, floor_tile, wall_tile)
    _place_bloodstains(game_map, rng, floor_tile, damage_level)
