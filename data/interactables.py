"""Interactable definitions as Python dataclasses."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class InteractableDef:
    char: str
    color: tuple[int, int, int]
    name: str
    placement: Literal["floor", "wall"]


INTERACTABLES: list[InteractableDef] = [
    InteractableDef(char="&", color=(100, 200, 255), name="Console", placement="floor"),
    InteractableDef(char="=", color=(180, 160, 100), name="Crate", placement="floor"),
    InteractableDef(char="%", color=(80, 200, 80), name="Mineral seam", placement="wall"),
    InteractableDef(char="[", color=(150, 160, 180), name="Locker", placement="wall"),
    InteractableDef(char="[", color=(140, 120, 90), name="Storage cabinet", placement="wall"),
]

FLOOR_INTERACTABLES: list[InteractableDef] = [i for i in INTERACTABLES if i.placement == "floor"]
WALL_INTERACTABLES: list[InteractableDef] = [i for i in INTERACTABLES if i.placement == "wall"]

_INTERACTABLES_BY_NAME: dict[str, InteractableDef] = {i.name: i for i in INTERACTABLES}

assert len(_INTERACTABLES_BY_NAME) == len(INTERACTABLES), "Duplicate interactable name detected"


def interactable_by_name(name: str) -> InteractableDef:
    """Look up a single interactable definition by name. Raises KeyError if not found."""
    return _INTERACTABLES_BY_NAME[name]
