"""Hazard definitions as Python dataclasses."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HazardDef:
    type: str
    damage: int
    equipment_damage: bool
    dot: int
    duration: int


HAZARDS: list[HazardDef] = [
    HazardDef(type="electric", damage=2, equipment_damage=True, dot=0, duration=0),
    HazardDef(type="radiation", damage=1, equipment_damage=False, dot=1, duration=3),
    HazardDef(type="explosive", damage=3, equipment_damage=False, dot=0, duration=0),
    HazardDef(type="gas", damage=1, equipment_damage=False, dot=0, duration=0),
    HazardDef(type="structural", damage=2, equipment_damage=False, dot=0, duration=0),
]
