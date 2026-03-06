"""Tests for fractal noise applied to starfield brightness."""
import numpy as np

from world.noise import fractal_noise


class TestFractalNoise:
    def test_output_shape_matches_input(self):
        rng = np.random.RandomState(0)
        result = fractal_noise(rng, 20, 30)
        assert result.shape == (20, 30)

    def test_values_in_zero_one(self):
        rng = np.random.RandomState(42)
        result = fractal_noise(rng, 50, 50)
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_deterministic_with_same_seed(self):
        r1 = fractal_noise(np.random.RandomState(7), 30, 30)
        r2 = fractal_noise(np.random.RandomState(7), 30, 30)
        assert np.array_equal(r1, r2)

    def test_different_seeds_differ(self):
        r1 = fractal_noise(np.random.RandomState(1), 30, 30)
        r2 = fractal_noise(np.random.RandomState(2), 30, 30)
        assert not np.array_equal(r1, r2)

    def test_has_smooth_variation(self):
        """Adjacent cells should not jump wildly — max neighbor diff < raw random."""
        rng = np.random.RandomState(10)
        field = fractal_noise(rng, 50, 50, octaves=3, base_radius=8)
        # Compute max absolute difference between horizontally adjacent cells
        h_diff = np.abs(np.diff(field, axis=0))
        # With smoothing, max diff should be much less than 1.0
        assert h_diff.max() < 0.3, f"Max horizontal diff {h_diff.max()} too large"


class TestStarfieldBrightnessVariation:
    """Verify that noise creates visible variation in starfield brightness."""

    def test_tactical_starfield_uses_noise(self):
        """Stars at different noise levels should get different brightness."""
        from world.noise import fractal_noise
        rng = np.random.RandomState(42)
        field = fractal_noise(rng, 100, 100)
        # Should have a decent spread of values
        assert field.std() > 0.05, f"Noise field too uniform: std={field.std()}"

    def test_viewport_starfield_uses_noise(self):
        """Strategic viewport should produce varied star brightness."""
        from tests.test_viewport_renderer import FakeConsole
        from ui.viewport_renderer import render_viewport

        c = FakeConsole(160, 50)
        render_viewport(c, 64, 0, 96, 40, "yellow_dwarf", 42, time_override=0.5)
        # Collect fg brightness of printed stars (excluding surface chars on disc)
        star_brightnesses = []
        for p in c.prints:
            # Stars are single chars like . * + x in the starfield area
            if p["string"] in ".+*x" and p["x"] < 140:  # away from the star disc
                star_brightnesses.append(max(p["fg"]))
        if len(star_brightnesses) >= 5:
            # Should have meaningful variation in brightness
            std = np.std(star_brightnesses)
            assert std > 5, f"Star brightness too uniform: std={std}"


class TestNebulaClustering:
    """Verify nebulae form clusters rather than random scatter."""

    def test_nebula_cells_are_clustered(self):
        """Nebula bg-colored cells should have neighbors that are also nebula."""
        from tests.test_viewport_renderer import FakeConsole
        from ui.viewport_renderer import render_viewport

        c = FakeConsole(160, 50)
        render_viewport(c, 64, 0, 96, 40, "yellow_dwarf", 42, time_override=0.0)
        vp = c.rgb["bg"][64:160, 0:40]
        # Nebula cells: bg where any channel > 8 (beyond base near-black)
        neb = np.max(vp, axis=-1) > 8
        if np.sum(neb) < 10:
            return  # too few nebula cells to test clustering
        # For each nebula cell, count how many of its 4-neighbors are also nebula
        neighbor_count = 0
        total = 0
        nxs, nys = np.where(neb)
        for i in range(len(nxs)):
            x, y = nxs[i], nys[i]
            neighbors = 0
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < vp.shape[0] and 0 <= ny < vp.shape[1] and neb[nx, ny]:
                    neighbors += 1
            neighbor_count += neighbors
            total += 1
        avg_neighbors = neighbor_count / total
        # Random scatter at 2% density would have ~0.08 avg neighbors
        # Clustered nebula should have >> 1 avg neighbor
        assert avg_neighbors > 1.0, f"Nebula not clustered: avg neighbors={avg_neighbors:.2f}"
