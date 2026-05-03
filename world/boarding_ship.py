"""Generate a full-size pirate ship for boarding interdictions.

Reuses ``generate_player_ship`` so pirate vessels share the same hull
constraints (no breaches, no random enemies) and look like real ships.
The seed comes from ``Interdiction.pirate_ship_seed`` so save/load can
deterministically rebuild the same pirate ship layout.
"""

from __future__ import annotations

from world.dungeon_gen import RectRoom, generate_player_ship
from world.game_map import GameMap


def generate_pirate_ship(seed: int) -> tuple[GameMap, list[RectRoom], tuple[int, int] | None]:
    """Return (game_map, rooms, exit_pos) for a pirate vessel."""
    return generate_player_ship(seed=seed)
