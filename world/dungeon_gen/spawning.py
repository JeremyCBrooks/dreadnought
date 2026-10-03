"""Enemy, item and interactable spawning."""

from __future__ import annotations

import random
from dataclasses import asdict

from data.enemies import EnemyDef, creatures_for
from data.hazards import HAZARDS
from data.interactables import FLOOR_INTERACTABLES, interactable_by_name
from data.items import ITEMS, all_loot
from game.entity import Entity
from game.factories import build_enemy, build_item_entity
from world.dungeon_gen.rooms import RectRoom, _near_exit, _random_room_pos, _room_wall_positions
from world.game_map import GameMap

MAX_ENEMIES_PER_ROOM = 3
MAX_ENEMIES_PER_LEVEL = 12


def _can_spawn_at(
    game_map: GameMap,
    x: int,
    y: int,
    exit_pos: tuple[int, int] | None,
    *,
    allow_non_blocking: bool = False,
) -> bool:
    """Return True if something may be spawned on (x, y).

    The tile must be walkable floor away from the exit with nothing blocking
    it. Items and furnishings also need the tile clear of other non-blocking
    entities; enemies (``allow_non_blocking``) may stand on those.
    """
    if not game_map.in_bounds(x, y) or not game_map.tiles["walkable"][x, y]:
        return False
    if _near_exit(x, y, exit_pos) or game_map.get_blocking_entity(x, y):
        return False
    return allow_non_blocking or not game_map.get_non_blocking_entity_at(x, y)


def _make_interactable(
    x: int,
    y: int,
    char: str,
    color: tuple[int, int, int],
    name: str,
    hazard: dict | None,
    loot: dict | None,
) -> Entity:
    """Build a searchable furnishing (locker, console, crate) with an optional hazard and loot."""
    return Entity(
        x=x,
        y=y,
        char=char,
        color=color,
        name=name,
        blocks_movement=False,
        interactable={"kind": name.lower(), "hazard": hazard, "loot": loot},
    )


# How far from the first member of a group the rest may spawn.
_GROUP_SPREAD = 2


def _spawn_enemies(
    room: RectRoom,
    game_map: GameMap,
    rng: random.Random,
    max_enemies: int = 2,
    exit_pos: tuple[int, int] | None = None,
    remaining: int | None = None,
    loc_type: str = "derelict",
    depth: int = 0,
) -> int:
    """Spawn native creatures of *loc_type* at *depth* into *room*; returns how many.

    Each encounter is one creature or a whole group (a swarm, a pack). The
    room holds at most ``max_enemies`` creatures (and never more than
    ``MAX_ENEMIES_PER_ROOM``, or *remaining* for the level), so groups grow
    with depth.
    """
    pool = creatures_for(loc_type, depth)
    if not pool:
        return 0
    weights = [c.spawn_weight for c in pool]
    budget = min(max_enemies, MAX_ENEMIES_PER_ROOM)
    if remaining is not None:
        budget = min(budget, remaining)
    spawned = 0
    for _ in range(rng.randint(0, budget)):
        if spawned >= budget:
            break
        x, y = _random_room_pos(room, rng)
        if not _can_spawn_at(game_map, x, y, exit_pos, allow_non_blocking=True):
            continue
        defn = rng.choices(pool, weights=weights)[0]
        size = min(rng.randint(*defn.group), budget - spawned)
        spawned += _spawn_group(defn, size, (x, y), game_map, rng, exit_pos)
    return spawned


def _spawn_group(
    defn: EnemyDef,
    size: int,
    leader_at: tuple[int, int],
    game_map: GameMap,
    rng: random.Random,
    exit_pos: tuple[int, int] | None,
) -> int:
    """Place *size* creatures of *defn*: the first at *leader_at*, the rest close by."""
    lx, ly = leader_at
    nearby = [
        (lx + dx, ly + dy)
        for dx in range(-_GROUP_SPREAD, _GROUP_SPREAD + 1)
        for dy in range(-_GROUP_SPREAD, _GROUP_SPREAD + 1)
        if (dx, dy) != (0, 0)
    ]
    rng.shuffle(nearby)
    spots = iter([leader_at, *nearby])
    placed = 0
    while placed < size:
        spot = next((p for p in spots if _can_spawn_at(game_map, *p, exit_pos, allow_non_blocking=True)), None)
        if spot is None:
            break
        game_map.entities.append(build_enemy(defn, *spot, rng))
        placed += 1
    return placed


def _spawn_items(
    room: RectRoom,
    game_map: GameMap,
    rng: random.Random,
    max_items: int = 1,
    exit_pos: tuple[int, int] | None = None,
) -> None:
    for _ in range(rng.randint(0, max_items)):
        x, y = _random_room_pos(room, rng)
        if not _can_spawn_at(game_map, x, y, exit_pos):
            continue
        defn = rng.choice(ITEMS)
        game_map.entities.append(build_item_entity(defn, x, y))


def _spawn_interactables(
    room: RectRoom,
    game_map: GameMap,
    rng: random.Random,
    count: int = 1,
    hazard_chance: float = 0.2,
    wall_interactable_name: str | None = None,
    exit_pos: tuple[int, int] | None = None,
) -> None:
    floor_pool = list(FLOOR_INTERACTABLES)
    wall_defn = interactable_by_name(wall_interactable_name) if wall_interactable_name else None
    pool = floor_pool + ([wall_defn] if wall_defn else [])
    if not pool:
        return

    loot_pool = all_loot()
    for _ in range(count):
        defn = rng.choice(pool)
        ch, color, name = defn.char, defn.color, defn.name
        is_wall = defn.placement == "wall"

        if is_wall:
            candidates = [
                (wx, wy)
                for wx, wy in _room_wall_positions(room)
                if game_map.in_bounds(wx, wy)
                and not game_map.tiles["walkable"][wx, wy]
                and not game_map.get_non_blocking_entity_at(wx, wy)
                and not _near_exit(wx, wy, exit_pos)
            ]
            if not candidates:
                continue
            x, y = rng.choice(candidates)
        else:
            x, y = _random_room_pos(room, rng)
            if not _can_spawn_at(game_map, x, y, exit_pos):
                continue

        hazard = None
        if rng.random() < hazard_chance:
            hazard = asdict(rng.choice(HAZARDS))
        loot = rng.choice(loot_pool) if rng.random() < 0.6 else None
        game_map.entities.append(_make_interactable(x, y, ch, color, name, hazard, loot))
