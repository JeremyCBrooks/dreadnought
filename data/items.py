"""Item and scanner definitions as Python dataclasses."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class ItemDef:
    char: str
    color: Tuple[int, int, int]
    name: str
    type: str
    value: int
    weapon_class: Optional[str] = None
    durability: Optional[int] = None
    max_durability: Optional[int] = None
    range: Optional[int] = None
    ammo: Optional[int] = None
    max_ammo: Optional[int] = None


@dataclass(frozen=True)
class ScannerDef:
    char: str
    color: Tuple[int, int, int]
    name: str
    scanner_tier: int
    range: int
    type: str
    value: int


ITEMS: list[ItemDef] = [
    ItemDef(char="!", color=(0, 255, 100), name="Med-kit", type="heal", value=5),
    ItemDef(char="/", color=(0, 191, 255), name="Bent Pipe", type="weapon", value=2,
            weapon_class="melee", durability=5, max_durability=5),
    ItemDef(char="/", color=(220, 180, 0), name="Stun Baton", type="weapon", value=3,
            weapon_class="melee", durability=5, max_durability=5),
    ItemDef(char="}", color=(200, 80, 80), name="Low-power Blaster", type="weapon", value=3,
            weapon_class="ranged", range=5, ammo=20, max_ammo=20),
    ItemDef(char="}", color=(180, 120, 60), name="Shotgun", type="weapon", value=5,
            weapon_class="ranged", range=3, ammo=10, max_ammo=10),
    ItemDef(char="#", color=(180, 140, 80), name="Repair Kit", type="repair", value=5),
    ItemDef(char="O", color=(100, 200, 255), name="O2 Canister", type="o2", value=20),
    ItemDef(char="#", color=(80, 200, 180), name="Hull Patch", type="hull_repair", value=3),
]

SCANNERS: list[ScannerDef] = [
    ScannerDef(char="]", color=(100, 200, 255), name="Basic Scanner",
               scanner_tier=1, range=8, type="scanner", value=1),
    ScannerDef(char="]", color=(150, 230, 255), name="Advanced Scanner",
               scanner_tier=2, range=14, type="scanner", value=2),
    ScannerDef(char="]", color=(200, 255, 255), name="Military Scanner",
               scanner_tier=3, range=20, type="scanner", value=3),
]

_ALL_LOOT: list[dict[str, Any]] = [asdict(i) for i in ITEMS] + [asdict(s) for s in SCANNERS]


def all_loot() -> list[dict[str, Any]]:
    """Return a fresh copy of the merged items + scanners list."""
    return [dict(d) for d in _ALL_LOOT]

# Keys that belong in an Entity.item dict (beyond type/value).
_ITEM_EXTRA_KEYS = {"durability", "max_durability", "scanner_tier", "weapon_class", "range", "ammo", "max_ammo"}


def build_item_data(definition: Any, *, rng: Any = None) -> Dict[str, Any]:
    """Extract Entity.item dict from a loot/item definition.

    Accepts a dataclass instance or a plain dict. Pulls ``type``, ``value``,
    and any type-specific keys (durability, max_durability, scanner_tier).

    For scanners, assigns random ``uses`` (1-3) via *rng* (defaults to
    ``random`` module if not provided).
    """
    import random as _random

    # Normalise to dict
    if hasattr(definition, "__dataclass_fields__"):
        d = asdict(definition)
    elif isinstance(definition, dict):
        d = definition
    else:
        raise TypeError(f"Expected dataclass or dict, got {type(definition)}")

    result: Dict[str, Any] = {"type": d["type"], "value": d["value"]}
    for key in _ITEM_EXTRA_KEYS:
        if key in d and d[key] is not None:
            result[key] = d[key]
    # Scanners get random limited uses (hidden from player)
    if d.get("type") == "scanner" and "uses" not in result:
        r = rng if rng is not None else _random
        result["uses"] = r.randint(1, 3)
    return result
