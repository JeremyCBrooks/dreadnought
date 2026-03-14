"""Enemy definitions as Python dataclasses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


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
    ),
    EnemyDef(
        char="p", color=(200, 50, 50), name="Pirate",
        hp=5, defense=1, power=3, organic=True, gore_color=(140, 20, 20),
        ai_initial_state="wandering", aggro_distance=8, sleep_aggro_distance=4,
        can_open_doors=True, flee_threshold=0.3, memory_turns=15, vision_radius=8, move_speed=4,
    ),
    EnemyDef(
        char="p", color=(50, 200, 50), name="Xeno Pirate",
        hp=5, defense=1, power=3, organic=True, gore_color=(30, 120, 30),
        ai_initial_state="wandering", aggro_distance=8, sleep_aggro_distance=4,
        can_open_doors=True, flee_threshold=0.3, memory_turns=15, vision_radius=8, move_speed=4,
    ),
    EnemyDef(
        char="p", color=(50, 80, 200), name="Vek Pirate",
        hp=5, defense=1, power=3, organic=True, gore_color=(30, 40, 140),
        ai_initial_state="wandering", aggro_distance=8, sleep_aggro_distance=4,
        can_open_doors=True, flee_threshold=0.3, memory_turns=15, vision_radius=8, move_speed=4,
    ),
    EnemyDef(
        char="p", color=(180, 150, 150), name="Mech Pirate",
        hp=6, defense=2, power=3, organic=False, gore_color=(50, 50, 60),
        ai_initial_state="wandering", aggro_distance=8, sleep_aggro_distance=4,
        can_open_doors=True, flee_threshold=0.2, memory_turns=20, vision_radius=8, move_speed=3,
    ),
    EnemyDef(
        char="d", color=(150, 150, 200), name="Security Drone",
        hp=4, defense=0, power=3, organic=False, gore_color=(50, 50, 60),
        ai_initial_state="sleeping", aggro_distance=10, sleep_aggro_distance=3,
        can_open_doors=True, flee_threshold=0.0, memory_turns=30, vision_radius=10, move_speed=3,
    ),
]
