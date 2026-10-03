"""Creatures spawn where they live, at the depth they belong, in the numbers they travel in."""

from __future__ import annotations

import random
from collections import Counter

import numpy as np
import pytest

from data.enemies import BOARDING, ENEMIES, creatures_for, enemy_by_name
from world.dungeon_gen import generate_dungeon, respawn_creatures
from world.loc_profiles import PROFILES

SEEDS = range(1, 31)
_BY_NAME = {c.name: c for c in ENEMIES}


def _creatures(game_map) -> list:
    return [e for e in game_map.entities if e.ai is not None]


def _census(loc_type: str, depth: int, seeds=SEEDS) -> Counter:
    counts: Counter = Counter()
    for seed in seeds:
        game_map, _, _ = generate_dungeon(seed=seed, loc_type=loc_type, depth=depth, max_enemies=3)
        counts.update(e.ai_config.get("species", e.name) for e in _creatures(game_map))
    return counts


@pytest.mark.parametrize("loc_type", tuple(PROFILES))
def test_only_native_creatures_spawn(loc_type):
    native = {c.name for c in creatures_for(loc_type, depth=5)}
    seen = set(_census(loc_type, depth=5))
    assert seen, f"nothing spawned in any {loc_type}"
    assert seen <= native, f"strays in {loc_type}: {seen - native}"


@pytest.mark.parametrize("loc_type", tuple(PROFILES))
def test_deep_creatures_stay_out_of_shallow_locations(loc_type):
    seen = set(_census(loc_type, depth=0))
    assert all(_BY_NAME[name].min_depth == 0 for name in seen)


def test_deep_creatures_appear_deeper_down():
    seen = set(_census("starbase", depth=5))
    assert any(_BY_NAME[name].min_depth > 0 for name in seen)


def test_variety_within_a_location_type():
    assert len(_census("derelict", depth=5)) >= 5


@pytest.mark.parametrize("max_enemies", [1, 3])
def test_swarms_spawn_together(max_enemies):
    """A swarm is one encounter: even a shallow, quiet room gets the whole swarm."""
    mites = enemy_by_name("Hull Mite")
    found_group = False
    for seed in SEEDS:
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="asteroid", depth=0, max_enemies=max_enemies)
        positions = [(e.x, e.y) for e in _creatures(game_map) if e.ai_config.get("species") == mites.name]
        for x, y in positions:
            neighbours = [p for p in positions if p != (x, y) and max(abs(p[0] - x), abs(p[1] - y)) <= 2]
            if neighbours:
                found_group = True
    assert found_group, "hull mites never spawned as a swarm"


def test_level_cap_holds_with_swarms():
    for seed in SEEDS:
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="asteroid", depth=5, max_enemies=3, max_total_enemies=4)
        assert len(_creatures(game_map)) <= 4


def test_creatures_never_change_the_layout():
    """Creatures draw from their own random stream: the same seed builds the same place."""
    for loc_type in PROFILES:
        with_life, _, _ = generate_dungeon(seed=4, loc_type=loc_type, depth=5, max_enemies=3)
        empty, _, _ = generate_dungeon(seed=4, loc_type=loc_type, depth=0, max_enemies=0)
        assert np.array_equal(with_life.tiles["tile_id"], empty.tiles["tile_id"])


def test_respawn_uses_the_location_s_own_creatures():
    game_map, rooms, _ = generate_dungeon(seed=3, loc_type="colony", depth=0)
    native = {c.name for c in creatures_for("colony", depth=0)}
    for seed in range(10):
        respawn_creatures(game_map, rooms, max_enemies=3, seed=seed, loc_type="colony", depth=0)
        assert {e.ai_config.get("species") for e in _creatures(game_map)} <= native


def test_boarding_crews_come_from_the_boarding_pool():
    from game.interdiction import _spawn_pirates_in_room
    from world import tile_types
    from world.dungeon_gen.rooms import RectRoom
    from world.game_map import GameMap

    game_map = GameMap(20, 20, fill_tile=tile_types.floor)
    crew_pool = {c.name for c in creatures_for(BOARDING, depth=0)}
    for seed in range(20):
        crew = _spawn_pirates_in_room(RectRoom(1, 1, 10, 10), game_map, random.Random(seed), 4)
        assert crew and {p.name for p in crew} <= crew_pool


def test_every_creature_records_its_species():
    for seed in range(1, 6):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="derelict", depth=5, max_enemies=3)
        for creature in _creatures(game_map):
            assert creature.ai_config.get("species") in _BY_NAME
