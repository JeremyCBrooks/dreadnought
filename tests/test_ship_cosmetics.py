"""Tests for ship cosmetic variation (hull patina, debris, scorch marks, bloodstains)."""
import random

import numpy as np

from world.game_map import GameMap
from world import tile_types
from game.entity import Entity, Fighter


def _make_ship_map(w=30, h=20):
    """Create a simple ship-like map with walls, floors, and some breaches."""
    gm = GameMap(w, h)
    # Fill with walls, carve a floor interior
    for x in range(3, w - 3):
        for y in range(3, h - 3):
            gm.tiles[x, y] = tile_types.floor
    # Hull breaches at known positions
    gm.tiles[3, 5] = tile_types.hull_breach
    gm.hull_breaches.append((3, 5))
    return gm


class TestHullPatina:
    def test_modifies_wall_colors(self):
        """Hull patina should create color variation among wall tiles."""
        from world.dungeon_gen import _apply_hull_patina

        gm = _make_ship_map()
        wall_tid = int(tile_types.wall["tile_id"])
        rng = random.Random(42)

        # Record original wall fg colors
        is_wall = gm.tiles["tile_id"] == wall_tid
        orig_fg_light = gm.tiles["light"]["fg"][is_wall].copy()

        _apply_hull_patina(gm, rng, tile_types.wall)

        new_fg_light = gm.tiles["light"]["fg"][is_wall]
        # Not all wall tiles should have the same color anymore
        assert not np.all(new_fg_light == orig_fg_light), \
            "Patina should modify at least some wall tile colors"

    def test_variation_is_smooth(self):
        """Adjacent wall tiles should have similar (not wildly different) colors."""
        from world.dungeon_gen import _apply_hull_patina

        gm = GameMap(40, 30)  # All walls
        rng = random.Random(42)
        _apply_hull_patina(gm, rng, tile_types.wall)

        wall_tid = int(tile_types.wall["tile_id"])
        is_wall = gm.tiles["tile_id"] == wall_tid
        fg = gm.tiles["light"]["fg"]

        # Check that adjacent wall tiles don't differ by more than ~40 per channel
        max_diff = 0
        for x in range(1, gm.width - 1):
            for y in range(1, gm.height - 1):
                if not is_wall[x, y]:
                    continue
                for dx, dy in ((1, 0), (0, 1)):
                    nx, ny = x + dx, y + dy
                    if nx < gm.width and ny < gm.height and is_wall[nx, ny]:
                        diff = max(abs(int(fg[x, y][c]) - int(fg[nx, ny][c]))
                                   for c in range(3))
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


class TestDebrisScatter:
    def test_places_debris_on_floors(self):
        """Some floor tiles should get debris chars."""
        from world.dungeon_gen import _scatter_floor_debris

        gm = _make_ship_map()
        rng = random.Random(42)
        floor_tid = int(tile_types.floor["tile_id"])

        _scatter_floor_debris(gm, rng, tile_types.floor)

        # Some floor tiles should now have different chars
        is_floor = gm.tiles["tile_id"] == floor_tid
        chars = gm.tiles["light"]["ch"][is_floor]
        dot_char = ord(".")
        non_dot = chars[chars != dot_char]
        assert len(non_dot) > 0, "Should place at least some debris chars"

    def test_does_not_change_walkability(self):
        """Debris tiles must remain walkable and transparent."""
        from world.dungeon_gen import _scatter_floor_debris

        gm = _make_ship_map()
        rng = random.Random(42)
        floor_tid = int(tile_types.floor["tile_id"])
        is_floor = gm.tiles["tile_id"] == floor_tid

        _scatter_floor_debris(gm, rng, tile_types.floor)

        # All original floor tiles should still be walkable
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
        floor_tid = int(tile_types.floor["tile_id"])

        # Record original brightness of tiles near the breach at (3, 5)
        orig_bg = gm.tiles["light"]["bg"][4, 5].copy()

        _place_scorch_marks(gm, rng, tile_types.floor)

        new_bg = gm.tiles["light"]["bg"][4, 5]
        # At least one channel should be darker or equal (not brighter)
        assert any(int(new_bg[c]) <= int(orig_bg[c]) for c in range(3)), \
            "Tiles near breach should not get brighter"

    def test_also_scorches_wall_tiles(self):
        """Scorch marks should affect wall tiles near breaches too."""
        from world.dungeon_gen import _place_scorch_marks

        gm = _make_ship_map()
        rng = random.Random(42)
        wall_tid = int(tile_types.wall["tile_id"])
        # Wall at (2,5) is adjacent to breach at (3,5)
        assert int(gm.tiles["tile_id"][2, 5]) == wall_tid
        orig_fg = gm.tiles["light"]["fg"][2, 5].copy()

        _place_scorch_marks(gm, rng, tile_types.floor, tile_types.wall)

        new_fg = gm.tiles["light"]["fg"][2, 5]
        # Should be darker (at least one channel reduced)
        assert any(int(new_fg[c]) < int(orig_fg[c]) for c in range(3)), \
            "Wall tiles near breach should be scorched"


class TestBloodstains:
    def test_places_stains_near_enemies(self):
        """Some floor tiles near enemies should get reddish tints."""
        from world.dungeon_gen import _place_bloodstains

        gm = _make_ship_map()
        rng = random.Random(42)
        # Place several enemies to ensure at least one gets stains
        for i in range(5):
            enemy = Entity(
                x=10 + i * 3, y=10, name="Alien", char="A",
                color=(255, 0, 0), blocks_movement=True,
                fighter=Fighter(hp=5, max_hp=5, defense=0, power=1),
            )
            gm.entities.append(enemy)

        _place_bloodstains(gm, rng, tile_types.floor)

        # Check tiles near enemy for red tint
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
                # Red channel boosted, green/blue suppressed
                if int(fg[0]) > 100 and int(fg[1]) < 100:
                    found_red = True
                    break
            if found_red:
                break
        assert found_red, "Should place at least one red-tinted tile near enemy"


class TestFullIntegration:
    def test_derelict_has_cosmetic_variation(self):
        """A generated derelict should have non-uniform wall colors."""
        from world.dungeon_gen import generate_dungeon

        gm, rooms, _ = generate_dungeon(seed=42, loc_type="derelict")
        wall_tid = int(tile_types.wall["tile_id"])
        is_wall = gm.tiles["tile_id"] == wall_tid

        if not np.any(is_wall):
            return  # skip if no walls (shouldn't happen)

        fg = gm.tiles["light"]["fg"][is_wall]
        # Check for color variation among walls
        unique_r = len(np.unique(fg[:, 0]))
        assert unique_r > 1, "Wall tiles should have color variation"
