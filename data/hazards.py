"""Hazard definitions as Python dataclasses."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
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

HAZARD_BY_TYPE: dict[str, HazardDef] = {h.type: h for h in HAZARDS}

assert len(HAZARD_BY_TYPE) == len(HAZARDS), "Duplicate hazard type detected"
