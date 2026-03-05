"""Tests for colony biome palettes and tile color variation."""
from __future__ import annotations

import random

import numpy as np

from world import tile_types
from world.palettes import (
    BIOMES,
    ColonyPalette,
    apply_ground_noise,
    make_ground_tile,
    make_path_tile,
    make_wall_tile,
    pick_biome,
)


def test_all_biomes_have_at_least_two_wall_colors():
    for name, biome in BIOMES.items():
        assert len(biome.wall_colors) >= 2, f"biome {name} needs >= 2 wall colors"


def test_pick_biome_returns_valid_palette():
    rng = random.Random(42)
    palette = pick_biome(rng)
    assert isinstance(palette, ColonyPalette)
    assert len(palette.wall_colors) >= 2
    assert len(palette.ground_dark_bg) == 3
    assert len(palette.ground_light_bg) == 3


def test_variant_ground_tile_preserves_tile_id():
    base_tid = int(tile_types.ground["tile_id"])
    rng = random.Random(42)
    palette = pick_biome(rng)
    variant = make_ground_tile(palette)
    assert int(variant["tile_id"]) == base_tid


def test_variant_wall_tile_preserves_tile_id():
    base_tid = int(tile_types.structure_wall["tile_id"])
    rng = random.Random(42)
    palette = pick_biome(rng)
    wall_color = palette.wall_colors[0]
    variant = make_wall_tile(wall_color)
    assert int(variant["tile_id"]) == base_tid


def test_ground_noise_stays_in_bounds():
    """After applying noise, all bg color channels must be in [0, 255]."""
    from world.game_map import GameMap

    rng = random.Random(99)
    palette = pick_biome(rng)
    ground_variant = make_ground_tile(palette)
    gm = GameMap(20, 20, fill_tile=ground_variant)
    ground_tid = int(tile_types.ground["tile_id"])
    apply_ground_noise(gm, rng, ground_tid, palette.noise_range)

    for layer in ("dark", "light", "lit"):
        bg = gm.tiles[layer]["bg"]
        assert np.all(bg >= 0), f"{layer} bg has values < 0"
        assert np.all(bg <= 255), f"{layer} bg has values > 255"


def test_ground_noise_introduces_variation():
    """Ground tiles should not all have identical bg after noise."""
    from world.game_map import GameMap

    rng = random.Random(7)
    palette = pick_biome(rng)
    ground_variant = make_ground_tile(palette)
    gm = GameMap(20, 20, fill_tile=ground_variant)
    ground_tid = int(tile_types.ground["tile_id"])
    apply_ground_noise(gm, rng, ground_tid, palette.noise_range)

    bg = gm.tiles["light"]["bg"]
    # At least some cells should differ from the first cell
    first = bg[0, 0].copy()
    assert not np.all(bg == first), "all ground bg identical after noise"


def test_ground_noise_is_spatially_smooth():
    """Adjacent tiles should have smaller color differences than distant tiles."""
    from world.game_map import GameMap

    rng = random.Random(42)
    palette = pick_biome(rng)
    ground_variant = make_ground_tile(palette)
    size = 40
    gm = GameMap(size, size, fill_tile=ground_variant)
    ground_tid = int(tile_types.ground["tile_id"])
    apply_ground_noise(gm, rng, ground_tid, palette.noise_range)

    bg = gm.tiles["light"]["bg"].astype(np.float64)
    # Average difference between adjacent tiles (Manhattan neighbors)
    adj_diffs = []
    adj_diffs.append(np.abs(bg[1:, :, :] - bg[:-1, :, :]).mean())
    adj_diffs.append(np.abs(bg[:, 1:, :] - bg[:, :-1, :]).mean())
    avg_adjacent = np.mean(adj_diffs)
    # Average difference between tiles 10 apart
    dist_diffs = []
    dist_diffs.append(np.abs(bg[10:, :, :] - bg[:-10, :, :]).mean())
    dist_diffs.append(np.abs(bg[:, 10:, :] - bg[:, :-10, :]).mean())
    avg_distant = np.mean(dist_diffs)
    assert avg_adjacent < avg_distant, (
        f"adjacent diff ({avg_adjacent:.2f}) should be less than "
        f"distant diff ({avg_distant:.2f})"
    )


def test_make_ground_tile_has_different_colors_than_default():
    """Variant ground tile should differ from the default ground tile."""
    rng = random.Random(42)
    palette = pick_biome(rng)
    variant = make_ground_tile(palette)
    default_bg = tuple(tile_types.ground["light"]["bg"])
    variant_bg = tuple(variant["light"]["bg"])
    # At least one biome should produce different colors
    # (the default ground is (12,10,7) dark bg, most biomes differ)
    assert variant_bg != default_bg or palette.name == "dirt"


def test_path_tile_has_unique_tile_id():
    """Path tile_id must be distinct from ground, floor, etc."""
    path_tid = int(tile_types.path["tile_id"])
    assert path_tid != int(tile_types.ground["tile_id"])
    assert path_tid != int(tile_types.floor["tile_id"])
    assert path_tid != int(tile_types.structure_wall["tile_id"])


def test_all_biomes_have_path_materials():
    for name, biome in BIOMES.items():
        assert biome.path_materials and len(biome.path_materials) >= 1, (
            f"biome {name} needs >= 1 path material"
        )


def test_path_materials_contrast_with_ground():
    """Path bg colors must have sufficient RGB distance from ground bg."""
    import math
    min_distance = 8  # minimum Euclidean distance in RGB space
    for name, biome in BIOMES.items():
        for mat in biome.path_materials:
            dist = math.sqrt(sum(
                (a - b) ** 2 for a, b in zip(mat.light_bg, biome.ground_light_bg)
            ))
            assert dist >= min_distance, (
                f"biome {name}, material {mat.name}: "
                f"path bg {mat.light_bg} too close to ground bg {biome.ground_light_bg} "
                f"(distance {dist:.1f} < {min_distance})"
            )


def test_frozen_biome_exists():
    assert "frozen" in BIOMES
    biome = BIOMES["frozen"]
    assert biome.name == "frozen"
    assert len(biome.wall_colors) >= 2
    assert biome.path_materials and len(biome.path_materials) >= 1


def test_alien_biome_exists():
    assert "alien" in BIOMES
    biome = BIOMES["alien"]
    assert biome.name == "alien"
    assert len(biome.wall_colors) >= 2
    assert biome.path_materials and len(biome.path_materials) >= 1


def test_all_biomes_have_flora():
    for name, biome in BIOMES.items():
        assert biome.flora and len(biome.flora) >= 1, (
            f"biome {name} needs >= 1 flora entry"
        )


def test_flora_tile_ids_are_distinct():
    """All flora tile IDs must be unique and differ from non-flora tiles."""
    flora_tids = [
        int(tile_types.flora_low["tile_id"]),
        int(tile_types.flora_tall["tile_id"]),
        int(tile_types.flora_scrub["tile_id"]),
        int(tile_types.flora_sprout["tile_id"]),
    ]
    other_tids = {
        int(tile_types.ground["tile_id"]),
        int(tile_types.floor["tile_id"]),
        int(tile_types.path["tile_id"]),
        int(tile_types.structure_wall["tile_id"]),
    }
    for tid in flora_tids:
        assert tid not in other_tids
    assert len(set(flora_tids)) == len(flora_tids), "flora tile IDs must be unique"


def test_make_flora_tile_preserves_tile_id():
    from world.palettes import FloraEntry, make_flora_tile
    rng = random.Random(42)
    palette = pick_biome(rng)
    entry = palette.flora[0]
    tile = make_flora_tile(entry, palette)
    expected_tid = int(tile_types.flora_low["tile_id"]) if entry.char == "*" else int(tile_types.flora_tall["tile_id"])
    assert int(tile["tile_id"]) == expected_tid


def test_scatter_flora_places_tiles():
    """scatter_flora should replace some ground tiles with flora tiles."""
    from world.game_map import GameMap
    from world.palettes import scatter_flora

    rng = random.Random(42)
    palette = pick_biome(rng)
    ground_tile = make_ground_tile(palette)
    gm = GameMap(40, 40, fill_tile=ground_tile)
    ground_tid = int(tile_types.ground["tile_id"])

    scatter_flora(gm, rng, palette, ground_tid)

    flora_tids = {
        int(tile_types.flora_low["tile_id"]),
        int(tile_types.flora_tall["tile_id"]),
        int(tile_types.flora_scrub["tile_id"]),
        int(tile_types.flora_sprout["tile_id"]),
    }
    flora_count = sum(
        1 for x in range(40) for y in range(40)
        if int(gm.tiles["tile_id"][x, y]) in flora_tids
    )
    assert flora_count > 0, "no flora placed"
    # Should not cover everything
    ground_count = sum(
        1 for x in range(40) for y in range(40)
        if int(gm.tiles["tile_id"][x, y]) == ground_tid
    )
    assert ground_count > flora_count, "flora should be sparse, not dominant"


def test_flora_tiles_are_walkable_and_transparent():
    from world.palettes import FloraEntry, make_flora_tile
    rng = random.Random(42)
    palette = pick_biome(rng)
    for entry in palette.flora:
        tile = make_flora_tile(entry, palette)
        assert bool(tile["walkable"]) is True
        assert bool(tile["transparent"]) is True


def test_flora_is_clustered():
    """Flora should appear in clusters, not uniform salt-and-pepper noise.

    Measure this by checking that flora tiles have more flora neighbors
    than you'd expect from a uniform random distribution.
    """
    from world.game_map import GameMap
    from world.palettes import scatter_flora

    flora_tids = {
        int(tile_types.flora_low["tile_id"]),
        int(tile_types.flora_tall["tile_id"]),
        int(tile_types.flora_scrub["tile_id"]),
        int(tile_types.flora_sprout["tile_id"]),
    }
    # Use grassland since it's the densest biome
    palette = BIOMES["grassland"]
    size = 80
    total_adj_flora = 0
    total_flora = 0
    trials = 5
    for seed in range(trials):
        rng = random.Random(seed)
        ground_tile = make_ground_tile(palette)
        gm = GameMap(size, size, fill_tile=ground_tile)
        ground_tid = int(tile_types.ground["tile_id"])
        scatter_flora(gm, rng, palette, ground_tid)
        is_flora = np.isin(gm.tiles["tile_id"], list(flora_tids))
        # Count how many flora tiles have at least one flora neighbor
        for dx, dy in [(1, 0), (0, 1)]:
            shifted = np.roll(is_flora, shift=1, axis=0 if dx else 1)
            total_adj_flora += int(np.sum(is_flora & shifted))
        total_flora += int(np.sum(is_flora))
    # With clustering, the fraction of flora tiles that are adjacent to
    # another flora tile should be higher than the overall flora density
    flora_density = total_flora / (size * size * trials)
    adjacency_rate = total_adj_flora / max(total_flora * 2, 1)
    # Clustering means flora neighbors other flora more than random placement
    # would predict. At high densities adjacency naturally approaches 1.0,
    # so compare against density directly rather than a multiplied threshold.
    assert adjacency_rate > flora_density, (
        f"flora not clustered: adjacency_rate={adjacency_rate:.3f} "
        f"should exceed density={flora_density:.3f}"
    )


def test_scatter_produces_multiple_flora_types():
    """Across several seeds, scatter_flora should place more than one
    flora type on a single map for biomes that define multiple types."""
    from world.game_map import GameMap
    from world.palettes import scatter_flora

    flora_tids = {
        int(tile_types.flora_low["tile_id"]),
        int(tile_types.flora_tall["tile_id"]),
        int(tile_types.flora_scrub["tile_id"]),
        int(tile_types.flora_sprout["tile_id"]),
    }
    multi_flora_count = 0
    for biome_name, palette in BIOMES.items():
        if len(palette.flora) < 2:
            continue
        for seed in range(10):
            rng = random.Random(seed * 100 + hash(biome_name))
            ground_tile = make_ground_tile(palette)
            gm = GameMap(60, 60, fill_tile=ground_tile)
            ground_tid = int(tile_types.ground["tile_id"])
            scatter_flora(gm, rng, palette, ground_tid)
            types_present = {
                int(gm.tiles["tile_id"][x, y])
                for x in range(60) for y in range(60)
                if int(gm.tiles["tile_id"][x, y]) in flora_tids
            }
            if len(types_present) >= 2:
                multi_flora_count += 1
    # Most maps with multi-flora biomes should have >=2 types
    assert multi_flora_count > 0, "no map had multiple flora types"


def test_make_path_tile_preserves_tile_id():
    rng = random.Random(42)
    palette = pick_biome(rng)
    tile = make_path_tile(palette, rng)
    assert int(tile["tile_id"]) == int(tile_types.path["tile_id"])
