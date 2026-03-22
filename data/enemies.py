"""Enemy definitions as Python dataclasses."""
from __future__ import annotations

import random as _random_mod
from dataclasses import dataclass
from typing import List, Tuple

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from game.entity import Entity


@dataclass(frozen=True)
class EnemyDef:
    char: str
    color: Tuple[int, int, int]
    name: str
    hp: int
    defense: int
    power: int
    organic: bool
    gore_color: Tuple[int, int, int]
    ai_initial_state: str
    aggro_distance: int
    sleep_aggro_distance: int
    can_open_doors: bool
    flee_threshold: float
    memory_turns: int
    vision_radius: int
    move_speed: int
    loot_table: Tuple[Tuple[str, float], ...] = ()
    max_inventory: int = 3
    can_steal: bool = False


_PIRATE_LOOT: Tuple[Tuple[str, float], ...] = (
    ("Med-kit", 0.4),
    ("Bent Pipe", 0.3),
    ("Stun Baton", 0.15),
    ("Low-power Blaster", 0.15),
    ("O2 Canister", 0.2),
)

ENEMIES: list[EnemyDef] = [
    EnemyDef(
        char="r", color=(127, 127, 0), name="Rat",
        hp=1, defense=0, power=1, organic=True, gore_color=(140, 20, 20),
        ai_initial_state="wandering", aggro_distance=5, sleep_aggro_distance=2,
        can_open_doors=False, flee_threshold=0.0, memory_turns=12, vision_radius=6, move_speed=6,
    ),
    EnemyDef(
        char="b", color=(127, 0, 180), name="Bot",
        hp=3, defense=0, power=2, organic=False, gore_color=(50, 50, 60),
        ai_initial_state="wandering", aggro_distance=8, sleep_aggro_distance=3,
        can_open_doors=True, flee_threshold=0.0, memory_turns=20, vision_radius=8, move_speed=3,
        loot_table=(("Repair Kit", 0.3),),
    ),
    EnemyDef(
        char="p", color=(200, 50, 50), name="Pirate",
        hp=5, defense=1, power=3, organic=True, gore_color=(140, 20, 20),
        ai_initial_state="wandering", aggro_distance=8, sleep_aggro_distance=4,
        can_open_doors=True, flee_threshold=0.3, memory_turns=15, vision_radius=8, move_speed=4,
        loot_table=_PIRATE_LOOT, can_steal=True,
    ),
    EnemyDef(
        char="p", color=(50, 200, 50), name="Xeno Pirate",
        hp=5, defense=1, power=3, organic=True, gore_color=(30, 120, 30),
        ai_initial_state="wandering", aggro_distance=8, sleep_aggro_distance=4,
        can_open_doors=True, flee_threshold=0.3, memory_turns=15, vision_radius=8, move_speed=4,
        loot_table=_PIRATE_LOOT, can_steal=True,
    ),
    EnemyDef(
        char="p", color=(50, 80, 200), name="Vek Pirate",
        hp=5, defense=1, power=3, organic=True, gore_color=(30, 40, 140),
        ai_initial_state="wandering", aggro_distance=8, sleep_aggro_distance=4,
        can_open_doors=True, flee_threshold=0.3, memory_turns=15, vision_radius=8, move_speed=4,
        loot_table=_PIRATE_LOOT, can_steal=True,
    ),
    EnemyDef(
        char="p", color=(180, 150, 150), name="Mech Pirate",
        hp=6, defense=2, power=3, organic=False, gore_color=(50, 50, 60),
        ai_initial_state="wandering", aggro_distance=8, sleep_aggro_distance=4,
        can_open_doors=True, flee_threshold=0.2, memory_turns=20, vision_radius=8, move_speed=3,
        loot_table=(("Repair Kit", 0.4), ("Low-power Blaster", 0.3), ("Shotgun", 0.1)),
    ),
    EnemyDef(
        char="d", color=(150, 150, 200), name="Security Drone",
        hp=4, defense=0, power=3, organic=False, gore_color=(50, 50, 60),
        ai_initial_state="sleeping", aggro_distance=10, sleep_aggro_distance=3,
        can_open_doors=True, flee_threshold=0.0, memory_turns=30, vision_radius=10, move_speed=3,
        loot_table=(("Repair Kit", 0.3),),
    ),
]


def build_enemy_inventory(defn: EnemyDef, rng: _random_mod.Random) -> List[Entity]:
    """Roll loot table and return item Entities for an enemy's starting inventory."""
    if not defn.loot_table:
        return []
    # 25% chance this enemy carries nothing
    if rng.random() < 0.25:
        return []

    from game.entity import Entity as _Entity
    from data.items import item_by_name, build_item_data

    items: List[Entity] = []
    for item_name, prob in defn.loot_table:
        if len(items) >= defn.max_inventory:
            break
        if rng.random() < prob:
            idef = item_by_name(item_name)
            item_ent = _Entity(
                x=0, y=0,
                char=idef.char, color=idef.color, name=idef.name,
                blocks_movement=False,
                item=build_item_data(idef),
            )
            items.append(item_ent)
    return items
