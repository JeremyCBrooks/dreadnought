"""Shared helper functions used across game modules."""
from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from game.entity import Entity
    from world.game_map import GameMap


def chebyshev(x1: int, y1: int, x2: int, y2: int) -> int:
    """Chebyshev (chessboard) distance between two points."""
    return max(abs(x1 - x2), abs(y1 - y2))


def get_equipped_ranged_weapon(entity: Entity) -> Entity | None:
    """Return equipped ranged weapon with ammo, checking loadout then inventory."""
    if getattr(entity, "loadout", None):
        wpn = entity.loadout.get_ranged_weapon()
        if wpn:
            return wpn
    for e in entity.inventory:
        if (
            e.item
            and e.item.get("type") == "weapon"
            and e.item.get("weapon_class") == "ranged"
            and e.item.get("ammo", 0) > 0
        ):
            return e
    return None


def has_usable_ranged(entity: Entity) -> bool:
    """Return True if entity has a ranged weapon with ammo remaining."""
    return get_equipped_ranged_weapon(entity) is not None


def is_door_closed(game_map: GameMap, x: int, y: int) -> bool:
    """Return True if the tile at (x, y) is a closed door."""
    from world import tile_types
    return int(game_map.tiles["tile_id"][x, y]) == int(tile_types.door_closed["tile_id"])


def is_door_open(game_map: GameMap, x: int, y: int) -> bool:
    """Return True if the tile at (x, y) is an open door."""
    from world import tile_types
    return int(game_map.tiles["tile_id"][x, y]) == int(tile_types.door_open["tile_id"])


def get_door_tile_ids() -> Tuple[int, int]:
    """Return (closed_id, open_id) for standard doors."""
    from world import tile_types
    return (
        int(tile_types.door_closed["tile_id"]),
        int(tile_types.door_open["tile_id"]),
    )


def is_diagonal_blocked(game_map: GameMap, x: int, y: int, dx: int, dy: int) -> bool:
    """Return True if diagonal movement from (x,y) by (dx,dy) is blocked by a closed door.

    Only closed doors block diagonal movement — walls do not, so players
    and creatures can still squeeze past wall corners as normal.
    """
    if dx == 0 or dy == 0:
        return False  # cardinal movement, not diagonal
    return is_door_closed(game_map, x + dx, y) or is_door_closed(game_map, x, y + dy)
