"""Runtime death gore — place blood, oil, or debris when enemies die."""
from __future__ import annotations

import random as _random
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from game.entity import Entity
    from world.game_map import GameMap

# Default gore colors by organic flag
_DEFAULT_BLOOD = (140, 20, 20)
_DEFAULT_OIL = (50, 50, 60)

# Splatter characters by type
_BLOOD_CHARS = [ord("."), ord(","), ord("'"), ord("`")]
_DEBRIS_CHARS = [ord(","), ord("'"), ord(";"), ord("~")]

# The 9 offsets: death tile + 8 neighbours
_OFFSETS = [(dx, dy) for dx in range(-1, 2) for dy in range(-1, 2)]


def place_death_gore(
    game_map: "GameMap",
    entity: "Entity",
    rng: Optional[_random.Random] = None,
) -> None:
    """Place gore on floor tiles at *entity*'s position and adjacent tiles.

    Only plain floor tiles (default char, no existing decorations) receive
    gore.  Items on a tile are unaffected — they render on top of the tile.
    Gore type is determined by ``entity.organic`` and ``entity.gore_color``.
    Amount scales with ``entity.fighter.max_hp``.
    """
    from world import tile_types

    if rng is None:
        rng = _random.Random()

    fighter = entity.fighter
    if fighter is None:
        return

    gore_color = entity.gore_color
    if gore_color is None:
        gore_color = _DEFAULT_BLOOD if entity.organic else _DEFAULT_OIL

    chars = _BLOOD_CHARS if entity.organic else _DEBRIS_CHARS

    # All walkable floor tile types eligible for gore
    _floor_defaults = {
        int(t["tile_id"]): int(t["light"]["ch"])
        for t in (
            tile_types.floor,
            tile_types.rock_floor,
            tile_types.dirt_floor,
            tile_types.ground,
            tile_types.airlock_floor,
        )
    }

    def _is_eligible(x: int, y: int) -> bool:
        if not game_map.in_bounds(x, y):
            return False
        tid = int(game_map.tiles["tile_id"][x, y])
        if tid not in _floor_defaults:
            return False
        if int(game_map.tiles["light"]["ch"][x, y]) != _floor_defaults[tid]:
            return False  # already decorated
        return True

    # Death tile is always included if eligible
    death_tile = (entity.x, entity.y)
    death_eligible = _is_eligible(*death_tile)

    # Collect eligible neighbour tiles (8 surrounding)
    neighbours = []
    for dx, dy in _OFFSETS:
        if dx == 0 and dy == 0:
            continue
        nx, ny = entity.x + dx, entity.y + dy
        if _is_eligible(nx, ny):
            neighbours.append((nx, ny))

    if not death_eligible and not neighbours:
        return

    # Scale extra count by max_hp (capped by available neighbours)
    base = max(1, fighter.max_hp)
    extra = min(len(neighbours), rng.randint(max(0, base - 1), base + max(1, base // 2) - 1))
    chosen = ([death_tile] if death_eligible else []) + rng.sample(neighbours, extra)

    r, g, b = gore_color
    for nx, ny in chosen:
        cur_ch = int(game_map.tiles["light"]["ch"][nx, ny])
        alt = [c for c in chars if c != cur_ch]
        ch = rng.choice(alt) if alt else rng.choice(chars)
        for layer in ("dark", "light", "lit"):
            brightness = 0.4 if layer == "dark" else (1.0 if layer == "light" else 0.7)
            game_map.tiles[layer]["ch"][nx, ny] = ch
            fg = game_map.tiles[layer]["fg"][nx, ny]
            fg[0] = min(255, int(r * brightness) + rng.randint(0, 20))
            fg[1] = min(255, int(g * brightness) + rng.randint(0, 10))
            fg[2] = min(255, int(b * brightness) + rng.randint(0, 10))
