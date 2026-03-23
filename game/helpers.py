"""Shared helper functions used across game modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.entity import Entity
    from world.game_map import GameMap


def chebyshev(x1: int, y1: int, x2: int, y2: int) -> int:
    """Chebyshev (chessboard) distance between two points."""
    return max(abs(x1 - x2), abs(y1 - y2))


def get_equipped_ranged_weapon(entity: Entity) -> Entity | None:
    """Return a usable ranged weapon with ammo.

    For entities with a loadout (player): only checks equipped loadout slots.
    For entities without a loadout (AI): falls back to inventory search.
    """
    if getattr(entity, "loadout", None):
        return entity.loadout.get_ranged_weapon()
    for e in entity.inventory:
        if (
            e.item
            and e.item.get("type") == "weapon"
            and e.item.get("weapon_class") == "ranged"
            and not e.item.get("damaged")
            and e.item.get("ammo", 0) > 0
        ):
            return e
    return None


def has_ranged_weapon(entity: Entity) -> bool:
    """Return True if entity has any ranged weapon (regardless of ammo).

    For entities with a loadout (player): only checks equipped loadout slots.
    For entities without a loadout (AI): falls back to inventory search.
    """
    if getattr(entity, "loadout", None):
        return any(s.item and s.item.get("weapon_class") == "ranged" for s in entity.loadout.all_items())
    return any(
        e.item and e.item.get("type") == "weapon" and e.item.get("weapon_class") == "ranged" for e in entity.inventory
    )


def has_usable_ranged(entity: Entity) -> bool:
    """Return True if entity has a ranged weapon with ammo remaining."""
    return get_equipped_ranged_weapon(entity) is not None


def is_door_closed(game_map: GameMap, x: int, y: int) -> bool:
    """Return True if the tile at (x, y) is a closed door."""
    if not (0 <= x < game_map.width and 0 <= y < game_map.height):
        return False
    from world import tile_types

    return int(game_map.tiles["tile_id"][x, y]) == int(tile_types.door_closed["tile_id"])


def is_door_open(game_map: GameMap, x: int, y: int) -> bool:
    """Return True if the tile at (x, y) is an open door."""
    if not (0 <= x < game_map.width and 0 <= y < game_map.height):
        return False
    from world import tile_types

    return int(game_map.tiles["tile_id"][x, y]) == int(tile_types.door_open["tile_id"])


def get_door_tile_ids() -> tuple[int, int]:
    """Return (closed_id, open_id) for standard doors."""
    from world import tile_types

    return (
        int(tile_types.door_closed["tile_id"]),
        int(tile_types.door_open["tile_id"]),
    )


def has_clear_shot(game_map: GameMap, x1: int, y1: int, x2: int, y2: int) -> bool:
    """Return True if no non-walkable tile lies between (x1,y1) and (x2,y2).

    Uses Bresenham's line algorithm.  Only *intermediate* tiles are checked —
    the start and end positions are excluded so that the shooter's and
    target's own tiles don't block the shot.
    """
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx - dy
    cx, cy = x1, y1
    while True:
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy
        # Stop before we reach the target tile
        if cx == x2 and cy == y2:
            break
        if not game_map.tiles["walkable"][cx, cy]:
            return False
    return True


def find_drop_tile(game_map: GameMap, x: int, y: int) -> tuple[int, int] | None:
    """Find a walkable tile at (x,y) or adjacent with no items."""
    if not game_map.get_items_at(x, y):
        return (x, y)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if game_map.in_bounds(nx, ny) and game_map.is_walkable(nx, ny) and not game_map.get_items_at(nx, ny):
                return (nx, ny)
    return None


def drop_all_inventory(entity: Entity, game_map: GameMap) -> None:
    """Drop all inventory items at or near entity's position."""
    for item in list(entity.inventory):
        tile = find_drop_tile(game_map, entity.x, entity.y)
        if tile is None:
            break
        entity.inventory.remove(item)
        item.x, item.y = tile
        game_map.entities.append(item)


def recalc_melee_power_ai(entity: Entity) -> None:
    """Recalculate melee power for AI entities from inventory (no Loadout needed)."""
    if not entity.fighter:
        return
    best_value = 0
    for e in entity.inventory:
        if (
            e.item
            and e.item.get("type") == "weapon"
            and e.item.get("weapon_class") == "melee"
            and not e.item.get("damaged")
        ):
            best_value = max(best_value, e.item.get("value", 0))
    entity.fighter.power = entity.fighter.base_power + best_value


def is_diagonal_blocked(game_map: GameMap, x: int, y: int, dx: int, dy: int) -> bool:
    """Return True if diagonal movement from (x,y) by (dx,dy) is blocked by a closed door.

    Only closed doors block diagonal movement — walls do not, so players
    and creatures can still squeeze past wall corners as normal.
    """
    if dx == 0 or dy == 0:
        return False  # cardinal movement, not diagonal
    return is_door_closed(game_map, x + dx, y) or is_door_closed(game_map, x, y + dy)
