"""Tests for location profile registry."""

from dataclasses import replace

from world import tile_types
from world.dungeon_gen import generate_dungeon
from world.loc_profiles import PROFILES, LocationProfile, get_profile

SEEDS = range(8)


def test_all_four_profiles_exist():
    assert "derelict" in PROFILES
    assert "asteroid" in PROFILES
    assert "starbase" in PROFILES
    assert "colony" in PROFILES


def test_get_profile_returns_correct_type():
    profile = get_profile("derelict")
    assert isinstance(profile, LocationProfile)
    assert profile.loc_type == "derelict"


def test_get_profile_unknown_defaults_to_derelict():
    profile = get_profile("unknown_stuff")
    assert profile.loc_type == "derelict"


def test_derelict_profile():
    p = get_profile("derelict")
    assert p.generator == "ship"
    assert p.wall_tile == "wall"
    assert p.floor_tile == "floor"
    labels = [s.label for s in p.room_specs]
    assert "bridge" in labels
    assert "engine_room" in labels


def test_asteroid_profile():
    p = get_profile("asteroid")
    assert p.generator == "organic"
    assert p.wall_tile == "rock_wall"
    assert p.floor_tile == "rock_floor"
    assert p.corridor_style == "winding"


def test_starbase_profile():
    p = get_profile("starbase")
    assert p.generator == "standard"
    assert p.wall_tile == "wall"
    assert p.floor_tile == "floor"


def test_colony_profile():
    p = get_profile("colony")
    assert p.generator == "village"
    assert p.wall_tile == "structure_wall"
    assert p.floor_tile == "dirt_floor"
    assert p.corridor_style == "open"


def test_room_specs_have_valid_dimensions():
    for name, profile in PROFILES.items():
        for spec in profile.room_specs:
            assert spec.min_w <= spec.max_w, f"{name}/{spec.label}: min_w > max_w"
            assert spec.min_h <= spec.max_h, f"{name}/{spec.label}: min_h > max_h"


def test_required_specs_have_max_count():
    for name, profile in PROFILES.items():
        for spec in profile.room_specs:
            if spec.required:
                assert spec.max_count >= 1, f"{name}/{spec.label}: required but max_count < 1"


def _generate(monkeypatch, profile, seed: int):
    """Generate a map for a made-up location type that uses *profile*."""
    monkeypatch.setitem(PROFILES, "custom", profile)
    return generate_dungeon(width=120, height=42, seed=seed, loc_type="custom")[0]


def _closed_doors(game_map) -> int:
    return int((game_map.tiles["tile_id"] == int(tile_types.door_closed["tile_id"])).sum())


def test_a_hulled_profile_with_no_breach_chance_never_breaches(monkeypatch):
    sealed = replace(PROFILES["derelict"], hull_breach_chance=0.0)

    for seed in SEEDS:
        game_map = _generate(monkeypatch, sealed, seed)
        assert game_map.hull_breaches == []
        assert game_map.airlocks != []


def test_a_hulled_profile_with_certain_breach_chance_always_breaches(monkeypatch):
    wrecked = replace(PROFILES["starbase"], hull_breach_chance=1.0)

    for seed in SEEDS:
        assert _generate(monkeypatch, wrecked, seed).hull_breaches != []


def test_a_profile_without_a_hull_gets_no_airlocks_and_no_space(monkeypatch):
    landlocked = replace(PROFILES["starbase"], has_hull=False)

    for seed in SEEDS:
        game_map = _generate(monkeypatch, landlocked, seed)
        assert game_map.airlocks == []
        assert game_map.has_space is False


def test_a_profile_can_turn_room_doors_off(monkeypatch):
    # A colony has no hull, so every closed door on it is a room door (16-32 per map on these seeds).
    with_doors = PROFILES["colony"]
    without_doors = replace(with_doors, places_doors=False)

    for seed in SEEDS:
        assert _closed_doors(_generate(monkeypatch, with_doors, seed)) > 0
        assert _closed_doors(_generate(monkeypatch, without_doors, seed)) == 0
