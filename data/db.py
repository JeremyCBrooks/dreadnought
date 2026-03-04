"""Data-driven entity definition loader.

Reads entities.json once on first access, converts color arrays to tuples,
and provides helper functions for building entity dicts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_DATA_FILE = Path(__file__).parent / "entities.json"
_NAMES_FILE = Path(__file__).parent / "names.json"
_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None
_names_cache: Optional[Dict[str, Any]] = None

# Keys that belong in an Entity.item dict (beyond type/value).
_ITEM_EXTRA_KEYS = {"durability", "max_durability", "scanner_tier", "weapon_class", "range", "ammo", "max_ammo"}


def _load() -> Dict[str, List[Dict[str, Any]]]:
    global _cache
    if _cache is not None:
        return _cache
    with open(_DATA_FILE) as f:
        raw = json.load(f)
    # Convert color arrays to tuples in-place.
    for category in ("enemies", "items", "scanners", "interactables"):
        for entry in raw[category]:
            if "color" in entry:
                entry["color"] = tuple(entry["color"])
    _cache = raw
    return _cache


def _load_names() -> Dict[str, Any]:
    global _names_cache
    if _names_cache is not None:
        return _names_cache
    with open(_NAMES_FILE) as f:
        _names_cache = json.load(f)
    return _names_cache


def reload() -> None:
    """Clear the cache so the next access re-reads from disk."""
    global _cache, _names_cache
    _cache = None
    _names_cache = None


def enemies() -> List[Dict[str, Any]]:
    return _load()["enemies"]


def items() -> List[Dict[str, Any]]:
    return _load()["items"]


def scanners() -> List[Dict[str, Any]]:
    return _load()["scanners"]


def interactables() -> List[Dict[str, Any]]:
    return _load()["interactables"]


def floor_interactables() -> List[Dict[str, Any]]:
    """Return interactables with floor placement (Console, Crate, etc.)."""
    return [i for i in interactables() if i.get("placement", "floor") == "floor"]


def interactable_by_name(name: str) -> Dict[str, Any]:
    """Look up a single interactable definition by name."""
    for i in interactables():
        if i["name"] == name:
            return i
    raise KeyError(f"No interactable named {name!r}")


def hazards() -> List[Dict[str, Any]]:
    return _load()["hazards"]


def all_loot() -> List[Dict[str, Any]]:
    """Merged items + scanners list, scanners normalized with type/value keys."""
    result = [dict(i) for i in items()]
    for s in scanners():
        entry = dict(s)
        entry["type"] = "scanner"
        entry["value"] = entry["scanner_tier"]
        result.append(entry)
    return result


def build_item_data(definition: Dict[str, Any]) -> Dict[str, Any]:
    """Extract Entity.item dict from a loot/item definition.

    Pulls ``type``, ``value``, and any type-specific keys (durability,
    max_durability, scanner_tier) — replaces scattered conditionals.
    """
    result: Dict[str, Any] = {"type": definition["type"], "value": definition["value"]}
    for key in _ITEM_EXTRA_KEYS:
        if key in definition:
            result[key] = definition[key]
    return result


def system_words() -> Dict[str, List[str]]:
    return _load_names()["system_words"]


def location_types() -> List[str]:
    return _load_names()["location_types"]


def location_words() -> Dict[str, Dict[str, List[str]]]:
    return _load_names()["location_words"]
