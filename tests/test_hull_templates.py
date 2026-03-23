"""Tests for data.hull_templates — hull profile data integrity and selection."""

import random

import pytest

from data.hull_templates import (
    BOWS,
    MIDS,
    STERNS,
    HullSection,
    get_random_hull,
)

# --- HullSection dataclass ---


def test_hull_section_is_frozen():
    """HullSection instances should be immutable."""
    section = BOWS[0]
    with pytest.raises(AttributeError):
        section.name = "changed"


def test_hull_section_fields():
    section = HullSection(name="test", profile=(1, 2, 3), room_type="bridge")
    assert section.name == "test"
    assert section.profile == (1, 2, 3)
    assert section.room_type == "bridge"


# --- Template collections ---


def test_bows_all_bridge():
    for bow in BOWS:
        assert bow.room_type == "bridge", f"{bow.name} should be bridge"


def test_mids_all_none():
    for mid in MIDS:
        assert mid.room_type is None, f"{mid.name} should have room_type=None"


def test_sterns_all_engine_room():
    for stern in STERNS:
        assert stern.room_type == "engine_room", f"{stern.name} should be engine_room"


def test_all_profiles_non_empty():
    for section in (*BOWS, *MIDS, *STERNS):
        assert len(section.profile) > 0, f"{section.name} has empty profile"


def test_all_profile_values_positive():
    for section in (*BOWS, *MIDS, *STERNS):
        for val in section.profile:
            assert val > 0, f"{section.name} has non-positive value {val}"


def test_all_sections_have_unique_names_within_group():
    for label, group in [("BOWS", BOWS), ("MIDS", MIDS), ("STERNS", STERNS)]:
        names = [s.name for s in group]
        assert len(names) == len(set(names)), f"Duplicate names in {label}"


def test_profiles_are_tuples():
    """Profiles should be tuples (immutable) not lists."""
    for section in (*BOWS, *MIDS, *STERNS):
        assert isinstance(section.profile, tuple), f"{section.name} profile is not a tuple"


def test_collections_are_tuples():
    """Module-level collections should be tuples (immutable)."""
    assert isinstance(BOWS, tuple)
    assert isinstance(MIDS, tuple)
    assert isinstance(STERNS, tuple)


# --- Bow profiles should be non-decreasing (growing hull shape) ---


def test_bow_profiles_non_decreasing():
    for bow in BOWS:
        for i in range(1, len(bow.profile)):
            assert bow.profile[i] >= bow.profile[i - 1], f"Bow {bow.name} decreases at index {i}"


# --- Section transition smoothness ---


def test_mid_profiles_start_at_bow_end_value():
    """Mid sections should start at the same value bows end at (smooth join)."""
    bow_end = {b.profile[-1] for b in BOWS}
    assert len(bow_end) == 1, f"Bows end at different values: {bow_end}"
    expected = bow_end.pop()
    for mid in MIDS:
        assert mid.profile[0] == expected, (
            f"Mid {mid.name} starts at {mid.profile[0]}, bows end at {expected}"
        )


def test_mid_profiles_end_at_stern_start_value():
    """Mid sections should end at the same value sterns start at (smooth join)."""
    stern_start = {s.profile[0] for s in STERNS}
    assert len(stern_start) == 1, f"Sterns start at different values: {stern_start}"
    expected = stern_start.pop()
    for mid in MIDS:
        assert mid.profile[-1] == expected, (
            f"Mid {mid.name} ends at {mid.profile[-1]}, sterns start at {expected}"
        )


# --- get_random_hull ---


def test_get_random_hull_returns_three_sections():
    rng = random.Random(42)
    bow, mid, stern = get_random_hull(rng)
    assert isinstance(bow, HullSection)
    assert isinstance(mid, HullSection)
    assert isinstance(stern, HullSection)


def test_get_random_hull_correct_room_types():
    rng = random.Random(42)
    bow, mid, stern = get_random_hull(rng)
    assert bow.room_type == "bridge"
    assert mid.room_type is None
    assert stern.room_type == "engine_room"


def test_get_random_hull_deterministic_with_seed():
    result1 = get_random_hull(random.Random(123))
    result2 = get_random_hull(random.Random(123))
    assert result1 == result2


def test_get_random_hull_varies_with_different_seeds():
    """Different seeds should eventually produce different hulls."""
    results = {get_random_hull(random.Random(i)) for i in range(50)}
    assert len(results) > 1


def test_get_random_hull_all_combinations_reachable():
    """Every bow, mid, and stern should be selectable."""
    seen_bows = set()
    seen_mids = set()
    seen_sterns = set()
    for i in range(200):
        bow, mid, stern = get_random_hull(random.Random(i))
        seen_bows.add(bow.name)
        seen_mids.add(mid.name)
        seen_sterns.add(stern.name)
    assert seen_bows == {b.name for b in BOWS}
    assert seen_mids == {m.name for m in MIDS}
    assert seen_sterns == {s.name for s in STERNS}


# --- Profile concatenation (as used by dungeon_gen) ---


def test_profile_concatenation_produces_valid_sequence():
    """Concatenated bow+mid+stern profile should be all positive ints."""
    rng = random.Random(42)
    bow, mid, stern = get_random_hull(rng)
    full = bow.profile + mid.profile + stern.profile
    assert len(full) == len(bow.profile) + len(mid.profile) + len(stern.profile)
    assert all(v > 0 for v in full)
