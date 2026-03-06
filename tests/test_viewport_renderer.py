"""Tests for the strategic viewport renderer."""
import numpy as np

from data.star_types import STAR_TYPES
from ui.viewport_renderer import render_viewport


class FakeConsole:
    """Minimal console mock that tracks print calls and has an rgb array."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.rgb = np.zeros((width, height), dtype=[("ch", np.int32),
                            ("fg", "3u1"), ("bg", "3u1")])
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
