"""Item and scanner definitions as Python dataclasses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import random as _random_mod


@dataclass(frozen=True, slots=True)
class ItemDef:
    char: str
    color: tuple[int, int, int]
    name: str
    type: str
    value: int
    weapon_class: str | None = None
    durability: int | None = None
    max_durability: int | None = None
    range: int | None = None
    ammo: int | None = None
    max_ammo: int | None = None


@dataclass(frozen=True, slots=True)
class ScannerDef:
    char: str
    color: tuple[int, int, int]
    name: str
    scanner_tier: int
    range: int
    type: str
    value: int


ITEMS: list[ItemDef] = [
    ItemDef(char="!", color=(0, 255, 100), name="Med-kit", type="heal", value=5),
    ItemDef(
        char="/",
        color=(0, 191, 255),
        name="Bent Pipe",
        type="weapon",
        value=2,
        weapon_class="melee",
        durability=5,
        max_durability=5,
    ),
    ItemDef(
        char="/",
        color=(220, 180, 0),
        name="Stun Baton",
        type="weapon",
        value=3,
        weapon_class="melee",
        durability=5,
        max_durability=5,
    ),
    ItemDef(
        char="}",
        color=(200, 80, 80),
        name="Low-power Blaster",
        type="weapon",
        value=3,
        weapon_class="ranged",
        range=5,
        ammo=20,
        max_ammo=20,
    ),
    ItemDef(
        char="}",
        color=(180, 120, 60),
        name="Shotgun",
        type="weapon",
        value=5,
        weapon_class="ranged",
        range=3,
        ammo=10,
        max_ammo=10,
    ),
    ItemDef(char="#", color=(180, 140, 80), name="Repair Kit", type="repair", value=5),
    ItemDef(char="O", color=(100, 200, 255), name="O2 Canister", type="o2", value=20),
    ItemDef(char="#", color=(80, 200, 180), name="Hull Patch", type="hull_repair", value=3),
]

SCANNERS: list[ScannerDef] = [
    ScannerDef(char="]", color=(100, 200, 255), name="Basic Scanner", scanner_tier=1, range=8, type="scanner", value=1),
    ScannerDef(
        char="]", color=(150, 230, 255), name="Advanced Scanner", scanner_tier=2, range=14, type="scanner", value=2
    ),
    ScannerDef(
        char="]", color=(200, 255, 255), name="Military Scanner", scanner_tier=3, range=20, type="scanner", value=3
    ),
]

_ITEMS_BY_NAME: dict[str, ItemDef] = {i.name: i for i in ITEMS}
_SCANNERS_BY_NAME: dict[str, ScannerDef] = {s.name: s for s in SCANNERS}

assert len(_ITEMS_BY_NAME) == len(ITEMS), "Duplicate item name detected"
assert len(_SCANNERS_BY_NAME) == len(SCANNERS), "Duplicate scanner name detected"


def item_by_name(name: str) -> ItemDef:
    """Look up an ItemDef by its name. Raises KeyError if not found."""
    return _ITEMS_BY_NAME[name]


def scanner_by_name(name: str) -> ScannerDef:
    """Look up a ScannerDef by its name. Raises KeyError if not found."""
    return _SCANNERS_BY_NAME[name]


_ALL_LOOT: list[dict[str, Any]] = [
    {k: v for k, v in asdict(d).items() if v is not None} for d in [*ITEMS, *SCANNERS]
]


def all_loot() -> list[dict[str, Any]]:
    """Return a fresh copy of the merged items + scanners list."""
    return [dict(d) for d in _ALL_LOOT]


# Keys that belong in an Entity.item dict (beyond type/value/uses).
_ITEM_EXTRA_KEYS = {"durability", "max_durability", "scanner_tier", "weapon_class", "range", "ammo", "max_ammo"}


def build_item_data(
    definition: ItemDef | ScannerDef | dict[str, Any],
    *,
    rng: _random_mod.Random | None = None,
) -> dict[str, Any]:
    """Extract Entity.item dict from a loot/item definition.

    Accepts a dataclass instance or a plain dict. Pulls ``type``, ``value``,
    and any type-specific keys (durability, max_durability, scanner_tier).

    For scanners, assigns random ``uses`` (1-3) via *rng* (defaults to
    ``random`` module if not provided) unless ``uses`` is already present.
    """
    import random as _random

    # Normalise to dict
    if is_dataclass(definition) and not isinstance(definition, type):
        d = asdict(definition)
    elif isinstance(definition, dict):
        d = definition
    else:
        raise TypeError(f"Expected dataclass or dict, got {type(definition)}")

    result: dict[str, Any] = {"type": d["type"], "value": d["value"]}
    for key in _ITEM_EXTRA_KEYS:
        if key in d and d[key] is not None:
            result[key] = d[key]
    # Scanners get random limited uses (hidden from player)
    if d.get("type") == "scanner" and "uses" not in d:
        r = rng if rng is not None else _random
        result["uses"] = r.randint(1, 3)
    elif "uses" in d:
        result["uses"] = d["uses"]
    return result
