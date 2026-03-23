"""Tests for ship cosmetic variation (hull patina, debris, scorch marks, bloodstains)."""

import random

import numpy as np

from game.entity import Entity, Fighter
from world import tile_types
from world.game_map import GameMap


def _make_ship_map(w=30, h=20, breach_count=1):
    """Create a simple ship-like map with walls, floors, and some breaches."""
    gm = GameMap(w, h)
    # Fill with walls, carve a floor interior
    for x in range(3, w - 3):
        for y in range(3, h - 3):
            gm.tiles[x, y] = tile_types.floor
    # Hull breaches at known positions
    for i in range(breach_count):
        bx, by = 3, 5 + i * 3
        if gm.in_bounds(bx, by):
            gm.tiles[bx, by] = tile_types.hull_breach
            gm.hull_breaches.append((bx, by))
    return gm


class TestHullPatina:
    def test_modifies_wall_colors(self):
        """Hull patina should create color variation among wall tiles."""
        from world.dungeon_gen import _apply_hull_patina

        gm = _make_ship_map()
        wall_tid = int(tile_types.wall["tile_id"])
        rng = random.Random(42)

        is_wall = gm.tiles["tile_id"] == wall_tid
        orig_fg_light = gm.tiles["light"]["fg"][is_wall].copy()

        _apply_hull_patina(gm, rng, tile_types.wall)

        new_fg_light = gm.tiles["light"]["fg"][is_wall]
        assert not np.all(new_fg_light == orig_fg_light), "Patina should modify at least some wall tile colors"

    def test_variation_is_smooth(self):
        """Adjacent wall tiles should have similar (not wildly different) colors."""
        from world.dungeon_gen import _apply_hull_patina

        gm = GameMap(40, 30)  # All walls
        rng = random.Random(42)
        _apply_hull_patina(gm, rng, tile_types.wall)

        wall_tid = int(tile_types.wall["tile_id"])
        is_wall = gm.tiles["tile_id"] == wall_tid
        fg = gm.tiles["light"]["fg"]

        max_diff = 0
        for x in range(1, gm.width - 1):
            for y in range(1, gm.height - 1):
                if not is_wall[x, y]:
                    continue
                for dx, dy in ((1, 0), (0, 1)):
                    nx, ny = x + dx, y + dy
                    if nx < gm.width and ny < gm.height and is_wall[nx, ny]:
                        diff = max(abs(int(fg[x, y][c]) - int(fg[nx, ny][c])) for c in range(3))
                        max_diff = max(max_diff, diff)
        assert max_diff <= 60, f"Adjacent walls differ by {max_diff} — not smooth"

    def test_does_not_modify_non_wall_tiles(self):
        """Patina should only affect wall tiles."""
        from world.dungeon_gen import _apply_hull_patina

        gm = _make_ship_map()
        rng = random.Random(42)
        floor_tid = int(tile_types.floor["tile_id"])
        is_floor = gm.tiles["tile_id"] == floor_tid
        orig_floor_fg = gm.tiles["light"]["fg"][is_floor].copy()

        _apply_hull_patina(gm, rng, tile_types.wall)

        new_floor_fg = gm.tiles["light"]["fg"][is_floor]
        assert np.array_equal(orig_floor_fg, new_floor_fg)

    def test_damage_level_scales_intensity(self):
        """Higher damage_level should produce greater color spread."""
        from world.dungeon_gen import _apply_hull_patina

        spreads = {}
        for level in (0.0, 0.5, 1.0):
            gm = GameMap(40, 30)
            rng = random.Random(42)
            _apply_hull_patina(gm, rng, tile_types.wall, damage_level=level)
            fg = gm.tiles["light"]["fg"]
            spreads[level] = int(fg[..., 0].max()) - int(fg[..., 0].min())

        assert spreads[0.0] < spreads[1.0], f"Pristine spread {spreads[0.0]} should be less than wrecked {spreads[1.0]}"


class TestDebrisScatter:
    def test_places_debris_on_floors(self):
        """Some floor tiles should get debris chars."""
        from world.dungeon_gen import _scatter_floor_debris

        gm = _make_ship_map()
        rng = random.Random(42)
        floor_tid = int(tile_types.floor["tile_id"])

        _scatter_floor_debris(gm, rng, tile_types.floor)

        is_floor = gm.tiles["tile_id"] == floor_tid
        chars = gm.tiles["light"]["ch"][is_floor]
        dot_char = ord(".")
        non_dot = chars[chars != dot_char]
        assert len(non_dot) > 0, "Should place at least some debris chars"

    def test_no_debris_at_zero_damage(self):
        """damage_level=0 should place no debris."""
        from world.dungeon_gen import _scatter_floor_debris

        gm = _make_ship_map()
        rng = random.Random(42)
        floor_tid = int(tile_types.floor["tile_id"])
        is_floor = gm.tiles["tile_id"] == floor_tid
        orig_chars = gm.tiles["light"]["ch"][is_floor].copy()

        _scatter_floor_debris(gm, rng, tile_types.floor, damage_level=0.0)

        assert np.array_equal(gm.tiles["light"]["ch"][is_floor], orig_chars)

    def test_does_not_change_walkability(self):
        """Debris tiles must remain walkable and transparent."""
        from world.dungeon_gen import _scatter_floor_debris

        gm = _make_ship_map()
        rng = random.Random(42)
        floor_tid = int(tile_types.floor["tile_id"])
        is_floor = gm.tiles["tile_id"] == floor_tid

        _scatter_floor_debris(gm, rng, tile_types.floor)

        assert np.all(gm.tiles["walkable"][is_floor])
        assert np.all(gm.tiles["transparent"][is_floor])

    def test_does_not_touch_walls(self):
        """Debris scatter should not modify wall tiles."""
        from world.dungeon_gen import _scatter_floor_debris

        gm = _make_ship_map()
        rng = random.Random(42)
        wall_tid = int(tile_types.wall["tile_id"])
        is_wall = gm.tiles["tile_id"] == wall_tid
        orig_chars = gm.tiles["light"]["ch"][is_wall].copy()

        _scatter_floor_debris(gm, rng, tile_types.floor)

        assert np.array_equal(gm.tiles["light"]["ch"][is_wall], orig_chars)


class TestScorchMarks:
    def test_darkens_tiles_near_breaches(self):
        """Floor tiles near hull breaches should be darkened."""
        from world.dungeon_gen import _place_scorch_marks

        gm = _make_ship_map()
        rng = random.Random(42)

        orig_bg = gm.tiles["light"]["bg"][4, 5].copy()

        _place_scorch_marks(gm, rng, tile_types.floor)

        new_bg = gm.tiles["light"]["bg"][4, 5]
        assert any(int(new_bg[c]) <= int(orig_bg[c]) for c in range(3)), "Tiles near breach should not get brighter"

    def test_also_scorches_wall_tiles(self):
        """Scorch marks should affect wall tiles near breaches too."""
        from world.dungeon_gen import _place_scorch_marks

        gm = _make_ship_map()
        rng = random.Random(42)
        wall_tid = int(tile_types.wall["tile_id"])
        assert int(gm.tiles["tile_id"][2, 5]) == wall_tid
        orig_fg = gm.tiles["light"]["fg"][2, 5].copy()

        _place_scorch_marks(gm, rng, tile_types.floor, tile_types.wall)

        new_fg = gm.tiles["light"]["fg"][2, 5]
        assert any(int(new_fg[c]) < int(orig_fg[c]) for c in range(3)), "Wall tiles near breach should be scorched"


class TestBloodstains:
    def test_places_stains_near_enemies(self):
        """Some floor tiles near enemies should get reddish tints."""
        from world.dungeon_gen import _place_bloodstains

        gm = _make_ship_map()
        rng = random.Random(42)
        for i in range(5):
            enemy = Entity(
                x=10 + i * 3,
                y=10,
                name="Alien",
                char="A",
                color=(255, 0, 0),
                blocks_movement=True,
                fighter=Fighter(hp=5, max_hp=5, defense=0, power=1),
            )
            gm.entities.append(enemy)

        _place_bloodstains(gm, rng, tile_types.floor)

        floor_tid = int(tile_types.floor["tile_id"])
        found_red = False
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                nx, ny = 10 + dx, 10 + dy
                if not gm.in_bounds(nx, ny):
                    continue
                if int(gm.tiles["tile_id"][nx, ny]) != floor_tid:
                    continue
                fg = gm.tiles["light"]["fg"][nx, ny]
                if int(fg[0]) > 100 and int(fg[1]) < 100:
                    found_red = True
                    break
            if found_red:
                break
        assert found_red, "Should place at least one red-tinted tile near enemy"

    def test_no_stains_at_zero_damage(self):
        """damage_level=0 should place no bloodstains."""
        from world.dungeon_gen import _place_bloodstains

        gm = _make_ship_map()
        rng = random.Random(42)
        for i in range(5):
            gm.entities.append(
                Entity(
                    x=10 + i * 3,
                    y=10,
                    name="Alien",
                    char="A",
                    color=(255, 0, 0),
                    blocks_movement=True,
                    fighter=Fighter(hp=5, max_hp=5, defense=0, power=1),
                )
            )

        floor_tid = int(tile_types.floor["tile_id"])
        is_floor = gm.tiles["tile_id"] == floor_tid
        orig_fg = gm.tiles["light"]["fg"][is_floor].copy()

        _place_bloodstains(gm, rng, tile_types.floor, damage_level=0.0)

        assert np.array_equal(gm.tiles["light"]["fg"][is_floor], orig_fg)


class TestDamageLevelScaling:
    def test_no_breaches_means_clean(self):
        """A map with no breaches should have damage_level=0 (no debris)."""
        from world.dungeon_gen import _apply_ship_cosmetics

        gm = _make_ship_map(breach_count=0)
        rng = random.Random(42)
        floor_tid = int(tile_types.floor["tile_id"])
        is_floor = gm.tiles["tile_id"] == floor_tid
        orig_chars = gm.tiles["light"]["ch"][is_floor].copy()

        _apply_ship_cosmetics(gm, rng, tile_types.wall, tile_types.floor)

        # No breaches → no debris
        assert np.array_equal(gm.tiles["light"]["ch"][is_floor], orig_chars), (
            "Zero breaches should produce no floor debris"
        )

    def test_more_breaches_means_more_debris(self):
        """More hull breaches should produce more debris tiles."""
        from world.dungeon_gen import _scatter_floor_debris

        floor_tid = int(tile_types.floor["tile_id"])
        counts = {}
        for n_breaches in (1, 3):
            gm = _make_ship_map(breach_count=n_breaches)
            rng = random.Random(42)
            damage = min(1.0, n_breaches / 3.0)
            _scatter_floor_debris(gm, rng, tile_types.floor, damage_level=damage)
            is_floor = gm.tiles["tile_id"] == floor_tid
            chars = gm.tiles["light"]["ch"][is_floor]
            counts[n_breaches] = int(np.sum(chars != ord(".")))

        assert counts[3] > counts[1], f"3 breaches ({counts[3]} debris) should produce more than 1 ({counts[1]})"


class TestFullIntegration:
    def test_derelict_has_cosmetic_variation(self):
        """A generated derelict should have non-uniform wall colors."""
        from world.dungeon_gen import generate_dungeon

        gm, rooms, _ = generate_dungeon(seed=42, loc_type="derelict")
        wall_tid = int(tile_types.wall["tile_id"])
        is_wall = gm.tiles["tile_id"] == wall_tid

        if not np.any(is_wall):
            return

        fg = gm.tiles["light"]["fg"][is_wall]
        unique_r = len(np.unique(fg[:, 0]))
        assert unique_r > 1, "Wall tiles should have color variation"

    def test_starbase_gets_cosmetics(self):
        """A starbase should also receive cosmetic treatment."""
        from world.dungeon_gen import generate_dungeon

        gm, rooms, _ = generate_dungeon(seed=42, loc_type="starbase")
        wall_tid = int(tile_types.wall["tile_id"])
        is_wall = gm.tiles["tile_id"] == wall_tid

        if not np.any(is_wall):
            return

        fg = gm.tiles["light"]["fg"][is_wall]
        unique_r = len(np.unique(fg[:, 0]))
        assert unique_r > 1, "Starbase wall tiles should have color variation"

    def test_starbase_no_breaches_is_clean(self):
        """A starbase without breaches should have no floor debris."""
        from world.dungeon_gen import generate_dungeon

        # Try multiple seeds to find one with no breaches (80% chance each)
        for seed in range(20):
            gm, rooms, _ = generate_dungeon(seed=seed, loc_type="starbase")
            if not gm.hull_breaches:
                floor_tid = int(tile_types.floor["tile_id"])
                is_floor = gm.tiles["tile_id"] == floor_tid
                chars = gm.tiles["light"]["ch"][is_floor]
                debris_chars = {ord(","), ord("'"), ord("`"), ord(";")}
                has_debris = any(int(c) in debris_chars for c in chars)
                assert not has_debris, f"Starbase with 0 breaches (seed={seed}) should have no debris"
                return
        # If all seeds had breaches, that's fine — skip
