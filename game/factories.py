"""Build item and enemy entities from their data definitions."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

from data.items import ItemDef, ScannerDef, build_item_data, item_by_name
from game.ai import CreatureAI
from game.entity import Entity, Fighter
from game.helpers import recalc_melee_power_ai

if TYPE_CHECKING:
    import random

    from data.enemies import EnemyDef


def build_item_entity(
    definition: ItemDef | ScannerDef | dict[str, Any],
    x: int = 0,
    y: int = 0,
    *,
    rng: random.Random | None = None,
) -> Entity:
    """An item lying at (x, y), from an item/scanner definition or a loot dict."""
    d = asdict(definition) if is_dataclass(definition) else definition
    return Entity(
        x=x,
        y=y,
        char=d["char"],
        color=d["color"],
        name=d["name"],
        blocks_movement=False,
        item=build_item_data(definition, rng=rng),
    )


def build_enemy_inventory(defn: EnemyDef, rng: random.Random) -> list[Entity]:
    """Roll loot table and return item Entities for an enemy's starting inventory."""
    if not defn.loot_table:
        return []
    # 25% chance this enemy carries nothing
    if rng.random() < 0.25:
        return []

    items: list[Entity] = []
    for item_name, prob in defn.loot_table:
        if len(items) >= defn.max_inventory:
            break
        if rng.random() < prob:
            items.append(build_item_entity(item_by_name(item_name)))
    return items


def build_enemy(defn: EnemyDef, x: int, y: int, rng: random.Random) -> Entity:
    """A creature of type *defn* at (x, y), with rolled inventory and melee power to match."""
    enemy = Entity(
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
    enemy.ai_config = defn.to_ai_config()
    enemy.ai_state = enemy.ai_config.get("ai_initial_state", "wandering")
    enemy.inventory = build_enemy_inventory(defn, rng)
    enemy.max_inventory = defn.max_inventory
    recalc_melee_power_ai(enemy)
    return enemy
