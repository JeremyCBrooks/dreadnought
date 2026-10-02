"""Golden test: generated maps must stay identical for a given seed.

Saves do not store maps. They rebuild them from the seed, and ship furnishings
are identified by generation-order index, so any change to the order or number
of ``rng`` draws silently changes existing saves. This test pins a digest of
everything a generated map carries for each location type and the player ship.

Each case has one digest per component so a failure names what changed:
``structure`` (tile ids and walkability; platform-stable), ``tiles`` (full
tile data including float-derived colours), ``rooms``, ``map``, ``lights``
and ``entities``.

If generation is changed ON PURPOSE, regenerate the digests with::

    python tests/test_dungeon_gen_golden.py

and say so in the commit: maps in existing saves will change.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

if __name__ == "__main__":  # allow running as a script from the project root
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world import tile_types
from world.dungeon_gen import generate_dungeon, generate_player_ship, respawn_creatures
from world.dungeon_gen.basic_layouts import _generate_fallback
from world.game_map import GameMap

DIGEST_FILE = Path(__file__).with_name("dungeon_gen_golden.json")
SEEDS = (1, 2, 3, 4, 5)
LOC_TYPES = ("derelict", "asteroid", "starbase", "colony")
# Attributes the ship generator sets ad hoc on the map.
_AD_HOC_MAP_ATTRS = ("spine_y", "hull_profile", "hull_margin_x", "branches")
# Tile fields that do not depend on float colour math, so they are stable across platforms.
_STRUCTURAL_TILE_FIELDS = ("tile_id", "walkable", "transparent")

type Generated = tuple[GameMap, list, tuple[int, int] | None]


def _jsonable(value):
    """Fallback for json.dumps: numpy scalars/arrays and sets."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, set | frozenset):
        return sorted(value)
    raise TypeError(f"cannot canonicalise {type(value).__name__}")


def _sha(payload) -> str:
    """Digest of *payload*; dict key order never matters (item dicts vary per process)."""
    raw = payload if isinstance(payload, bytes) else json.dumps(payload, sort_keys=True, default=_jsonable).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _fighter_stats(fighter) -> tuple[int, ...] | None:
    if fighter is None:
        return None
    return (fighter.hp, fighter.max_hp, fighter.defense, fighter.power, fighter.base_power)


def _entity_record(entity) -> dict:
    return {
        "name": entity.name,
        "pos": (entity.x, entity.y),
        "char": entity.char,
        "color": entity.color,
        "blocks_movement": entity.blocks_movement,
        "organic": entity.organic,
        "gore_color": entity.gore_color,
        "max_inventory": entity.max_inventory,
        "ai": type(entity.ai).__name__ if entity.ai is not None else None,
        "ai_state": entity.ai_state,
        "ai_config": entity.ai_config,
        "item": entity.item,
        "interactable": entity.interactable,
        "fighter": _fighter_stats(entity.fighter),
        "inventory": [(i.name, i.char, i.color, i.item) for i in entity.inventory],
    }


def _digest(generated: Generated) -> dict[str, str]:
    game_map, rooms, exit_pos = generated
    tiles = game_map.tiles
    structure = b"".join(np.ascontiguousarray(tiles[field]).tobytes() for field in _STRUCTURAL_TILE_FIELDS)
    map_state = {
        "size": (game_map.width, game_map.height),
        "fully_lit": game_map.fully_lit,
        "fov_radius": game_map.fov_radius,
        "has_space": game_map.has_space,
        "biome": game_map.biome,
        "airlocks": game_map.airlocks,
        "hull_breaches": game_map.hull_breaches,
        **{attr: getattr(game_map, attr, None) for attr in _AD_HOC_MAP_ATTRS},
    }
    return {
        "structure": _sha(structure),
        "tiles": _sha(np.ascontiguousarray(tiles).tobytes()),
        "rooms": _sha({"rooms": [(r.x1, r.y1, r.x2, r.y2, r.label) for r in rooms], "exit_pos": exit_pos}),
        "map": _sha(map_state),
        "lights": _sha([dataclasses.astuple(ls) for ls in game_map.light_sources]),
        "entities": _sha([_entity_record(e) for e in game_map.entities]),
    }


def _respawned() -> Generated:
    game_map, rooms, exit_pos = generate_dungeon(seed=3, loc_type="derelict")
    respawn_creatures(game_map, rooms, max_enemies=2, seed=99)
    return game_map, rooms, exit_pos


def _fallback() -> Generated:
    """The fallback generator is unreachable through generate_dungeon, so call it directly."""
    game_map = GameMap(60, 40, fill_tile=tile_types.wall)
    rooms = _generate_fallback(game_map, random.Random(7), 10, 4, 10, tile_types.floor)
    return game_map, rooms, None


def _cases() -> dict[str, Callable[[], Generated]]:
    cases: dict[str, Callable[[], Generated]] = {}
    for loc_type in LOC_TYPES:
        for seed in SEEDS:
            cases[f"{loc_type}-{seed}"] = lambda s=seed, lt=loc_type: generate_dungeon(seed=s, loc_type=lt)
    for seed in SEEDS:
        cases[f"player_ship-{seed}"] = lambda s=seed: generate_player_ship(seed=s)
    cases["derelict-nav_unit"] = lambda: generate_dungeon(seed=11, loc_type="derelict", has_nav_unit=True)
    cases["derelict-enemy_cap_2"] = lambda: generate_dungeon(seed=12, loc_type="derelict", max_total_enemies=2)
    cases["starbase-no_enemies"] = lambda: generate_dungeon(seed=13, loc_type="starbase", max_enemies=0)
    cases["asteroid-three_items"] = lambda: generate_dungeon(seed=14, loc_type="asteroid", max_items=3)
    cases["colony-three_items"] = lambda: generate_dungeon(seed=15, loc_type="colony", max_items=3)
    cases["derelict-small_map"] = lambda: generate_dungeon(width=40, height=25, seed=16, loc_type="derelict")
    cases["asteroid-small_map"] = lambda: generate_dungeon(width=40, height=25, seed=17, loc_type="asteroid")
    cases["derelict-respawned"] = _respawned
    cases["fallback"] = _fallback
    return cases


CASES = _cases()


def _recorded() -> dict[str, dict[str, str]]:
    return json.loads(DIGEST_FILE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", list(CASES))
def test_generated_map_matches_recorded_digest(name):
    assert _digest(CASES[name]()) == _recorded()[name]


def test_every_recorded_digest_has_a_case():
    """A stale entry in the digest file would mean a case was dropped unnoticed."""
    assert set(_recorded()) == set(CASES)


def test_starbase_cases_cover_both_breached_and_intact_hulls():
    """A 20% roll decides whether a starbase gets hull breaches; pin both outcomes."""
    breached = [bool(CASES[f"starbase-{seed}"]()[0].hull_breaches) for seed in SEEDS]
    assert any(breached) and not all(breached)


def test_digest_ignores_dict_key_order():
    assert _sha({"a": 1, "b": [2, 3]}) == _sha({"b": [2, 3], "a": 1})


def test_digest_detects_a_single_changed_tile():
    generated = CASES["player_ship-1"]()
    before = _digest(generated)
    generated[0].tiles[0, 0] = tile_types.reactor_core
    after = _digest(generated)
    assert after["structure"] != before["structure"]
    assert after["entities"] == before["entities"]


def test_digest_detects_a_moved_entity():
    generated = CASES["player_ship-1"]()
    before = _digest(generated)
    generated[0].entities[0].x += 1
    after = _digest(generated)
    assert after["entities"] != before["entities"]
    assert after["structure"] == before["structure"]


if __name__ == "__main__":
    DIGEST_FILE.write_text(
        json.dumps({name: _digest(build()) for name, build in CASES.items()}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(CASES)} digests to {DIGEST_FILE}")
