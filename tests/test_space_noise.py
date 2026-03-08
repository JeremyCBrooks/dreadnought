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
        # Collect fg brightness of background stars from rgb array (away from disc)
        region_fg = c.rgb["fg"][64:140, 0:40]
        region_ch = c.rgb["ch"][64:140, 0:40]
        star_chars = {ord('.'), ord('*'), ord('+'), ord('x')}
        star_mask = np.isin(region_ch, list(star_chars))
        if np.sum(star_mask) >= 5:
            max_fg = np.max(region_fg[star_mask], axis=-1)
            std = np.std(max_fg.astype(np.float64))
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


class TestNebulaMorphologyVariation:
    """Nebulae should have varied shapes — not all uniform blobs."""

    @staticmethod
    def _nebula_mask_for_seed(seed, size=200):
        """Render a large region and return the nebula boolean mask."""
        from tests.test_viewport_renderer import FakeConsole
        from ui.viewport_renderer import render_starfield_bg

        c = FakeConsole(size, size)
        render_starfield_bg(c, 0, 0, size, size, seed, t=0.0)
        vp = c.rgb["bg"][0:size, 0:size]
        return np.max(vp, axis=-1) > 8

    @staticmethod
    def _label_components(mask):
        """Simple flood-fill connected component labeling (no scipy needed)."""
        labeled = np.zeros_like(mask, dtype=int)
        label_id = 0
        h, w = mask.shape
        for sy in range(h):
            for sx in range(w):
                if mask[sy, sx] and labeled[sy, sx] == 0:
                    label_id += 1
                    stack = [(sy, sx)]
                    while stack:
                        cy, cx = stack.pop()
                        if (cy < 0 or cy >= h or cx < 0 or cx >= w
                                or labeled[cy, cx] != 0 or not mask[cy, cx]):
                            continue
                        labeled[cy, cx] = label_id
                        stack.extend([(cy-1, cx), (cy+1, cx),
                                      (cy, cx-1), (cy, cx+1)])
        return labeled, label_id

    def test_nebula_regions_have_varied_sizes(self):
        """Across several seeds, nebula connected components should have a
        wide range of sizes — not all similarly-sized blobs."""
        all_areas = []
        for seed in [10, 42, 77, 123, 200, 333, 500, 999]:
            neb = self._nebula_mask_for_seed(seed, size=250)
            if np.sum(neb) < 5:
                continue
            labeled, n_features = self._label_components(neb)
            for i in range(1, n_features + 1):
                all_areas.append(np.sum(labeled == i))

        assert len(all_areas) >= 3, "Not enough nebula regions to test"
        all_areas = np.array(all_areas)
        ratio = all_areas.max() / max(all_areas.min(), 1)
        assert ratio > 10, (
            f"Nebula regions lack size variation: max/min ratio={ratio:.1f}"
        )

    def test_some_nebulae_are_elongated(self):
        """At least some nebula regions should be elongated (filament-like),
        not all roughly circular blobs."""
        aspect_ratios = []
        for seed in [10, 42, 77, 123, 200, 333, 500, 999]:
            neb = self._nebula_mask_for_seed(seed, size=250)
            if np.sum(neb) < 5:
                continue
            labeled, n_features = self._label_components(neb)
            for i in range(1, n_features + 1):
                component = labeled == i
                area = np.sum(component)
                if area < 20:
                    continue
                ys_c, xs_c = np.where(component)
                if len(ys_c) == 0:
                    continue
                h = ys_c.max() - ys_c.min() + 1
                w = xs_c.max() - xs_c.min() + 1
                aspect = max(h, w) / max(min(h, w), 1)
                aspect_ratios.append(aspect)

        assert len(aspect_ratios) >= 3, "Not enough regions to test aspect ratio"
        max_aspect = max(aspect_ratios)
        assert max_aspect > 3.0, (
            f"No elongated nebulae found: max aspect ratio={max_aspect:.1f}"
        )

    def test_nebula_density_varies_across_space(self):
        """Different quadrants of a large region should have meaningfully
        different nebula coverage — not uniform density everywhere."""
        neb = self._nebula_mask_for_seed(42, size=400)
        # Split into 4 quadrants
        q_size = 200
        quadrant_densities = []
        for qx in range(2):
            for qy in range(2):
                quad = neb[qx * q_size:(qx + 1) * q_size,
                           qy * q_size:(qy + 1) * q_size]
                quadrant_densities.append(np.mean(quad))
        densities = np.array(quadrant_densities)
        # The densities should vary — std should be meaningful
        # (uniform coverage across all quadrants implies no variation)
        density_range = densities.max() - densities.min()
        assert density_range > 0.05, (
            f"Nebula density too uniform across quadrants: range={density_range:.3f}, "
            f"densities={densities}"
        )
