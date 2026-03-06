"""Tests for star type definitions and selection."""
import random

from data.star_types import STAR_TYPES, STAR_TYPE_WEIGHTS, StarType, pick_star_type


class TestStarTypeDefinitions:
    def test_all_types_are_star_type_instances(self):
        for key, st in STAR_TYPES.items():
            assert isinstance(st, StarType), f"{key} is not a StarType"

    def test_required_fields_have_correct_types(self):
        for key, st in STAR_TYPES.items():
            assert isinstance(st.name, str), f"{key}.name"
            assert isinstance(st.radius, int), f"{key}.radius"
            assert isinstance(st.core_color, tuple) and len(st.core_color) == 3, f"{key}.core_color"
            assert isinstance(st.mid_color, tuple) and len(st.mid_color) == 3, f"{key}.mid_color"
            assert isinstance(st.edge_color, tuple) and len(st.edge_color) == 3, f"{key}.edge_color"
            assert isinstance(st.corona_color, tuple) and len(st.corona_color) == 3, f"{key}.corona_color"
            assert isinstance(st.corona_width, int), f"{key}.corona_width"
            assert isinstance(st.surface_chars, str) and len(st.surface_chars) > 0, f"{key}.surface_chars"

    def test_radii_are_reasonable(self):
        for key, st in STAR_TYPES.items():
            assert 1 <= st.radius <= 20, f"{key}.radius={st.radius} out of range"

    def test_weights_match_types(self):
        assert set(STAR_TYPE_WEIGHTS.keys()) == set(STAR_TYPES.keys())
        for w in STAR_TYPE_WEIGHTS.values():
            assert w > 0

    def test_at_least_seventeen_types(self):
        assert len(STAR_TYPES) >= 17


    def test_render_hints_are_valid(self):
        valid_hints = {"", "pulsar", "black_hole"}
        for key, st in STAR_TYPES.items():
            assert st.render_hint in valid_hints, f"{key}.render_hint={st.render_hint!r}"

    def test_pulsar_and_black_hole_exist(self):
        hints = {st.render_hint for st in STAR_TYPES.values()}
        assert "pulsar" in hints
        assert "black_hole" in hints


    def test_yellow_white_dwarf_exists_and_sized_correctly(self):
        yw = STAR_TYPES["yellow_white_dwarf"]
        yd = STAR_TYPES["yellow_dwarf"]
        bg = STAR_TYPES["blue_giant"]
        assert yw.radius > yd.radius, "yellow/white dwarf should be larger than yellow dwarf"
        assert yw.radius <= bg.radius, "yellow/white dwarf should be smaller than blue giant"

    def test_yellow_white_dwarf_less_common_than_yellow_dwarf(self):
        assert STAR_TYPE_WEIGHTS["yellow_white_dwarf"] < STAR_TYPE_WEIGHTS["yellow_dwarf"]

    def test_white_star_exists_and_sized_correctly(self):
        ws = STAR_TYPES["white_star"]
        yw = STAR_TYPES["yellow_white_dwarf"]
        bg = STAR_TYPES["blue_giant"]
        assert ws.radius > yw.radius, "white star should be larger than yellow/white dwarf"
        assert ws.radius <= bg.radius, "white star should be no larger than blue giant"

    def test_white_star_rarity_between_yellow_white_and_blue_giant(self):
        assert STAR_TYPE_WEIGHTS["blue_giant"] < STAR_TYPE_WEIGHTS["white_star"]
        assert STAR_TYPE_WEIGHTS["white_star"] < STAR_TYPE_WEIGHTS["yellow_white_dwarf"]


class TestPickStarType:
    def test_deterministic_with_same_seed(self):
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        results1 = [pick_star_type(rng1) for _ in range(20)]
        results2 = [pick_star_type(rng2) for _ in range(20)]
        assert results1 == results2

    def test_returns_valid_key(self):
        rng = random.Random(99)
        for _ in range(50):
            key = pick_star_type(rng)
            assert key in STAR_TYPES

    def test_all_types_appear_over_many_draws(self):
        rng = random.Random(0)
        seen = set()
        for _ in range(5000):
            seen.add(pick_star_type(rng))
        assert seen == set(STAR_TYPES.keys()), f"Missing types: {set(STAR_TYPES.keys()) - seen}"
