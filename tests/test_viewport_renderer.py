"""Tests for the strategic viewport renderer."""

import numpy as np

from data.star_types import STAR_TYPES
from ui.viewport_renderer import render_viewport


class FakeConsole:
    """Minimal console mock that tracks print calls and has an rgb array."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.rgb = np.zeros((width, height), dtype=[("ch", np.int32), ("fg", "3u1"), ("bg", "3u1")])
        self.prints = []

    def print(self, *, x, y, string, fg=(255, 255, 255)):
        self.prints.append({"x": x, "y": y, "string": string, "fg": fg})


class TestStarfieldDeterminism:
    def test_same_seed_same_starfield(self):
        c1 = FakeConsole(160, 50)
        c2 = FakeConsole(160, 50)
        render_viewport(c1, 64, 0, 96, 42, "yellow_dwarf", 12345, time_override=100.0)
        render_viewport(c2, 64, 0, 96, 42, "yellow_dwarf", 12345, time_override=100.0)
        assert np.array_equal(c1.rgb["bg"], c2.rgb["bg"])
        assert np.array_equal(c1.rgb["ch"], c2.rgb["ch"])
        assert np.array_equal(c1.rgb["fg"], c2.rgb["fg"])
        assert c1.prints == c2.prints

    def test_different_seeds_differ(self):
        c1 = FakeConsole(160, 50)
        c2 = FakeConsole(160, 50)
        render_viewport(c1, 64, 0, 96, 42, "yellow_dwarf", 111, time_override=0.0)
        render_viewport(c2, 64, 0, 96, 42, "yellow_dwarf", 222, time_override=0.0)
        # Background patterns should differ
        assert not np.array_equal(c1.rgb["bg"], c2.rgb["bg"])


class TestViewportBounds:
    def test_all_prints_within_viewport(self):
        c = FakeConsole(160, 50)
        render_viewport(c, 64, 0, 96, 42, "red_giant", 42, time_override=0.0)
        for p in c.prints:
            assert 64 <= p["x"] < 160, f"x={p['x']} out of bounds"
            assert 0 <= p["y"] < 42, f"y={p['y']} out of bounds"

    def test_bg_only_set_in_viewport(self):
        c = FakeConsole(160, 50)
        render_viewport(c, 64, 0, 96, 42, "yellow_dwarf", 1, time_override=0.0)
        # Outside viewport bg should remain zero
        assert np.all(c.rgb["bg"][:64, :] == 0)
        assert np.all(c.rgb["bg"][:, 42:] == 0)


class TestStarDisc:
    def test_near_star_uses_bright_color(self):
        c = FakeConsole(160, 50)
        render_viewport(c, 64, 0, 96, 42, "yellow_dwarf", 1, time_override=0.0)
        # Star is in upper-right corner: cx = 64 + 96 - 2 = 158, cy = 1
        # Check a cell near the star center (within the disc)
        bg = tuple(c.rgb["bg"][155, 0])
        # Should be bright — at least one channel > 150
        assert max(bg) > 150, f"Near-star bg too dim: {bg}"

    def test_red_giant_fills_more_than_white_dwarf(self):
        c_rg = FakeConsole(160, 50)
        c_wd = FakeConsole(160, 50)
        render_viewport(c_rg, 64, 0, 96, 42, "red_giant", 1, time_override=0.0)
        render_viewport(c_wd, 64, 0, 96, 42, "white_dwarf", 1, time_override=0.0)
        # Count cells with bright bg (any channel > 50) in viewport
        vp_rg = c_rg.rgb["bg"][64:160, 0:42]
        vp_wd = c_wd.rgb["bg"][64:160, 0:42]
        bright_rg = np.sum(np.max(vp_rg, axis=-1) > 50)
        bright_wd = np.sum(np.max(vp_wd, axis=-1) > 50)
        assert bright_rg > bright_wd, f"red_giant ({bright_rg}) should fill more than white_dwarf ({bright_wd})"


class TestSpecialStars:
    def test_black_hole_center_is_dark(self):
        """Black hole center should be darker than surrounding space."""
        c = FakeConsole(160, 50)
        render_viewport(c, 64, 0, 96, 42, "black_hole", 1, time_override=0.0)
        # Star center: cx=158, cy=1 — check a cell very near center
        center_bg = c.rgb["bg"][157, 0]
        center_brightness = int(center_bg[0]) + int(center_bg[1]) + int(center_bg[2])
        # Should be very dark (near 0)
        assert center_brightness < 20, f"Black hole center too bright: {tuple(center_bg)}"

    def test_black_hole_has_accretion_glow(self):
        """Black hole should have some bright cells around it (accretion disc)."""
        c = FakeConsole(160, 50)
        render_viewport(c, 64, 0, 96, 42, "black_hole", 1, time_override=0.0)
        # Check region around star for bright cells
        region = c.rgb["bg"][140:158, 0:15]
        max_brightness = np.max(region)
        assert max_brightness > 30, f"No accretion glow found, max={max_brightness}"

    def test_pulsar_brightness_changes_over_time(self):
        """Pulsar should pulse, producing different brightness at different times."""
        c1 = FakeConsole(160, 50)
        c2 = FakeConsole(160, 50)
        render_viewport(c1, 64, 0, 96, 42, "pulsar", 1, time_override=0.0)
        render_viewport(c2, 64, 0, 96, 42, "pulsar", 1, time_override=1.0)
        region1 = c1.rgb["bg"][140:158, 0:10]
        region2 = c2.rgb["bg"][140:158, 0:10]
        assert not np.array_equal(region1, region2), "Pulsar should pulse brightness"

    def test_all_star_types_render_without_error(self):
        """Smoke test: every star type renders without crashing."""
        for key in STAR_TYPES:
            c = FakeConsole(160, 50)
            render_viewport(c, 64, 0, 96, 42, key, 42, time_override=0.0)


class TestFlares:
    def test_flares_change_over_time(self):
        """Flares should animate — different times produce different output."""
        c1 = FakeConsole(160, 50)
        c2 = FakeConsole(160, 50)
        render_viewport(c1, 64, 0, 96, 42, "yellow_dwarf", 42, time_override=0.0)
        render_viewport(c2, 64, 0, 96, 42, "yellow_dwarf", 42, time_override=15.0)
        # The bg around the star should differ due to flare movement
        # Check the corona/glow region (near but not at the star center)
        region1 = c1.rgb["bg"][120:155, 0:20]
        region2 = c2.rgb["bg"][120:155, 0:20]
        assert not np.array_equal(region1, region2), "Flares should cause different bg over time"

    def test_flares_stay_in_viewport(self):
        """All flare effects must remain within viewport bounds."""
        c = FakeConsole(160, 50)
        render_viewport(c, 64, 0, 96, 42, "orange_giant", 99, time_override=5.0)
        # Outside viewport bg should remain zero
        assert np.all(c.rgb["bg"][:64, :] == 0)
        assert np.all(c.rgb["bg"][:, 42:] == 0)


class TestStarColors:
    def test_background_stars_have_color_variation(self):
        """Background stars should not all be the same hue — some yellow/red."""
        c = FakeConsole(160, 50)
        # Use white_dwarf (small radius) so most prints are background stars
        render_viewport(c, 64, 0, 96, 42, "white_dwarf", 42, time_override=0.0)
        # Check star fg colors in the rgb array (away from star disc)
        # Star disc is at upper-right; check left portion of viewport
        region_fg = c.rgb["fg"][64:140, 0:42]
        region_ch = c.rgb["ch"][64:140, 0:42]
        star_chars = {ord("."), ord("*"), ord("+"), ord("x")}
        has_warm = False
        has_cool = False
        xs, ys = np.where(np.isin(region_ch, list(star_chars)))
        for i in range(len(xs)):
            r, _g, b = int(region_fg[xs[i], ys[i]][0]), int(region_fg[xs[i], ys[i]][1]), int(region_fg[xs[i], ys[i]][2])
            if r > b + 5:
                has_warm = True
            elif b >= r:
                has_cool = True
        assert has_cool, "No cool/white background stars found"
        assert has_warm, "No warm (yellow/red) background stars found"

    def test_star_colors_are_deterministic(self):
        """Same seed should produce same star colors."""
        c1 = FakeConsole(160, 50)
        c2 = FakeConsole(160, 50)
        render_viewport(c1, 64, 0, 96, 42, "yellow_dwarf", 42, time_override=0.0)
        render_viewport(c2, 64, 0, 96, 42, "yellow_dwarf", 42, time_override=0.0)
        assert np.array_equal(c1.rgb["ch"], c2.rgb["ch"])
        assert np.array_equal(c1.rgb["fg"], c2.rgb["fg"])

    def test_flares_are_deterministic(self):
        """Same seed + same time = same flares."""
        c1 = FakeConsole(160, 50)
        c2 = FakeConsole(160, 50)
        render_viewport(c1, 64, 0, 96, 42, "red_dwarf", 77, time_override=10.0)
        render_viewport(c2, 64, 0, 96, 42, "red_dwarf", 77, time_override=10.0)
        assert np.array_equal(c1.rgb["bg"], c2.rgb["bg"])
