"""Tests for location profile registry."""
from world.loc_profiles import get_profile, PROFILES, LocationProfile, RoomSpec


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
