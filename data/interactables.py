"""Interactable definitions as Python dataclasses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class InteractableDef:
    char: str
    color: Tuple[int, int, int]
    name: str
    placement: str


INTERACTABLES: list[InteractableDef] = [
    InteractableDef(char="&", color=(100, 200, 255), name="Console", placement="floor"),
    InteractableDef(char="=", color=(180, 160, 100), name="Crate", placement="floor"),
    InteractableDef(char="%", color=(80, 200, 80), name="Mineral seam", placement="wall"),
    InteractableDef(char="[", color=(150, 160, 180), name="Locker", placement="wall"),
    InteractableDef(char="[", color=(140, 120, 90), name="Storage cabinet", placement="wall"),
]

FLOOR_INTERACTABLES: list[InteractableDef] = [i for i in INTERACTABLES if i.placement == "floor"]


def interactable_by_name(name: str) -> InteractableDef:
    """Look up a single interactable definition by name."""
    for i in INTERACTABLES:
        if i.name == name:
            return i
    raise KeyError(f"No interactable named {name!r}")
