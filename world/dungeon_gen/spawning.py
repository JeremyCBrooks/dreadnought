"""Enemy, item and interactable spawning."""

from __future__ import annotations

import random
from dataclasses import asdict

from data.enemies import ENEMIES, build_enemy_inventory
from data.hazards import HAZARDS
from data.interactables import FLOOR_INTERACTABLES, interactable_by_name
from data.items import ITEMS, all_loot, build_item_data
from game.ai import CreatureAI
from game.entity import Entity, Fighter
from world.dungeon_gen.rooms import RectRoom, _near_exit, _random_room_pos, _room_wall_positions
from world.game_map import GameMap

MAX_ENEMIES_PER_ROOM = 3
MAX_ENEMIES_PER_LEVEL = 12


def _spawn_enemies(
    room: RectRoom,
    game_map: GameMap,
    rng: random.Random,
    max_enemies: int = 2,
    exit_pos: tuple[int, int] | None = None,
    remaining: int | None = None,
) -> int:
    capped = min(max_enemies, MAX_ENEMIES_PER_ROOM)
    if remaining is not None:
        capped = min(capped, remaining)
    spawned = 0
    for _ in range(rng.randint(0, capped)):
        x, y = _random_room_pos(room, rng)
        if not game_map.in_bounds(x, y) or not game_map.tiles["walkable"][x, y]:
            continue
        if game_map.get_blocking_entity(x, y):
            continue
        if _near_exit(x, y, exit_pos):
            continue
        defn = rng.choice(ENEMIES)
        ai_config = defn.to_ai_config()
        entity = Entity(
            x=x,
            y=y,
            char=defn.char,
            color=defn.color,
            name=defn.name,
            blocks_movement=True,
            fighter=Fighter(hp=defn.hp, max_hp=defn.hp, defense=defn.defense, power=defn.power),
            ai=CreatureAI(),
            organic=defn.organic,
            gore_color=defn.gore_color,
        )
        entity.ai_config = ai_config
        entity.ai_state = ai_config.get("ai_initial_state", "wandering")
        entity.inventory = build_enemy_inventory(defn, rng)
        entity.max_inventory = defn.max_inventory
        from game.helpers import recalc_melee_power_ai

        recalc_melee_power_ai(entity)
        game_map.entities.append(entity)
        spawned += 1
    return spawned


def _spawn_items(
    room: RectRoom,
    game_map: GameMap,
    rng: random.Random,
    max_items: int = 1,
    exit_pos: tuple[int, int] | None = None,
) -> None:
    for _ in range(rng.randint(0, max_items)):
        x, y = _random_room_pos(room, rng)
        if not game_map.in_bounds(x, y) or not game_map.tiles["walkable"][x, y]:
            continue
        if _near_exit(x, y, exit_pos):
            continue
        if game_map.get_blocking_entity(x, y) or game_map.get_non_blocking_entity_at(x, y):
            continue
        defn = rng.choice(ITEMS)
        game_map.entities.append(
            Entity(
                x=x,
                y=y,
                char=defn.char,
                color=defn.color,
                name=defn.name,
                blocks_movement=False,
                item=build_item_data(defn),
            )
        )


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
            if not game_map.in_bounds(x, y) or not game_map.tiles["walkable"][x, y]:
                continue
            if game_map.get_blocking_entity(x, y) or game_map.get_non_blocking_entity_at(x, y):
                continue
            if _near_exit(x, y, exit_pos):
                continue

        hazard = None
        if rng.random() < hazard_chance:
            hazard = asdict(rng.choice(HAZARDS))
        loot = rng.choice(loot_pool) if rng.random() < 0.6 else None
        game_map.entities.append(
            Entity(
                x=x,
                y=y,
                char=ch,
                color=color,
                name=name,
                blocks_movement=False,
                interactable={"kind": name.lower(), "hazard": hazard, "loot": loot},
            )
        )
