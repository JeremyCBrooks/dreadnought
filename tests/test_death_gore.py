"""Tests for runtime death gore — blood/oil/debris placed when enemies die."""
import random
import random as _random

import numpy as np

from tests.conftest import make_arena, make_creature, MockEngine
from game.entity import Entity, Fighter
from world import tile_types


def _make_gore_map(w=20, h=20):
    """Floor arena suitable for gore tests."""
    return make_arena(w, h)


def _count_modified_floor_tiles(gm):
    """Count floor tiles whose light-layer char differs from the default."""
    floor_ch = int(tile_types.floor["light"]["ch"])
    floor_tid = int(tile_types.floor["tile_id"])
    is_floor = gm.tiles["tile_id"] == floor_tid
    return int(np.sum(gm.tiles["light"]["ch"][is_floor] != floor_ch))


class TestPlaceDeathGore:
    """Unit tests for the place_death_gore helper."""

    def test_death_tile_always_gets_gore(self):
        """The tile the enemy dies on must always receive gore."""
        from game.gore import place_death_gore

        # Run with many seeds to ensure it's not just luck
        for seed in range(50):
            gm = _make_gore_map()
            ex, ey = 10, 10
            enemy = Entity(
                x=ex, y=ey, char="p", color=(200, 50, 50), name="Pirate",
                blocks_movement=True,
                fighter=Fighter(hp=0, max_hp=1, defense=0, power=1),
                organic=True, gore_color=(140, 20, 20),
            )
            floor_ch = int(tile_types.floor["light"]["ch"])
            place_death_gore(gm, enemy, random.Random(seed))
            assert int(gm.tiles["light"]["ch"][ex, ey]) != floor_ch, \
                f"Death tile must always get gore (seed={seed})"

    def test_organic_enemy_leaves_red_blood(self):
        """Organic enemies should leave red-tinted splatter on the floor."""
        from game.gore import place_death_gore

        gm = _make_gore_map()
        enemy = Entity(
            x=5, y=5, char="p", color=(200, 50, 50), name="Pirate",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=5, defense=1, power=3),
            organic=True, gore_color=(140, 20, 20),
        )
        rng = random.Random(42)
        place_death_gore(gm, enemy, rng)

        # Check the death tile and its 8 neighbours for red-tinted fg
        found_red = False
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = enemy.x + dx, enemy.y + dy
                if not gm.in_bounds(nx, ny):
                    continue
                fg = gm.tiles["light"]["fg"][nx, ny]
                if int(fg[0]) > 80 and int(fg[0]) > int(fg[1]) * 2:
                    found_red = True
                    break
            if found_red:
                break
        assert found_red, "Organic enemy death should leave red blood"

    def test_inorganic_enemy_leaves_oil_debris(self):
        """Inorganic enemies should leave grayish oil/debris."""
        from game.gore import place_death_gore

        gm = _make_gore_map()
        enemy = Entity(
            x=5, y=5, char="b", color=(127, 0, 180), name="Bot",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=3, defense=0, power=2),
            organic=False, gore_color=(50, 50, 60),
        )
        rng = random.Random(42)
        place_death_gore(gm, enemy, rng)

        # Check for non-default tile modifications within 1-tile radius
        found_debris = False
        floor_ch = int(tile_types.floor["light"]["ch"])
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = enemy.x + dx, enemy.y + dy
                if not gm.in_bounds(nx, ny):
                    continue
                ch = int(gm.tiles["light"]["ch"][nx, ny])
                if ch != floor_ch and ch != ord(" "):
                    found_debris = True
                    break
            if found_debris:
                break
        assert found_debris, "Inorganic enemy death should leave debris"

    def test_gore_confined_to_adjacent_tiles(self):
        """Gore must only appear on the death tile and its 8 neighbours."""
        from game.gore import place_death_gore

        gm = _make_gore_map()
        ex, ey = 10, 10
        enemy = Entity(
            x=ex, y=ey, char="p", color=(200, 50, 50), name="Pirate",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=5, defense=1, power=3),
            organic=True, gore_color=(140, 20, 20),
        )
        rng = random.Random(42)
        floor_ch = int(tile_types.floor["light"]["ch"])
        floor_tid = int(tile_types.floor["tile_id"])

        place_death_gore(gm, enemy, rng)

        # Every modified tile must be within 1 step of (ex, ey)
        for x in range(gm.width):
            for y in range(gm.height):
                if int(gm.tiles["tile_id"][x, y]) != floor_tid:
                    continue
                if int(gm.tiles["light"]["ch"][x, y]) != floor_ch:
                    assert abs(x - ex) <= 1 and abs(y - ey) <= 1, \
                        f"Gore at ({x},{y}) is too far from death at ({ex},{ey})"

    def test_gore_only_on_floor_tiles(self):
        """Gore should not modify wall tiles."""
        from game.gore import place_death_gore

        gm = _make_gore_map()
        # Place enemy near wall edge
        enemy = Entity(
            x=1, y=1, char="p", color=(200, 50, 50), name="Pirate",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=5, defense=1, power=3),
            organic=True, gore_color=(140, 20, 20),
        )
        wall_tid = int(tile_types.wall["tile_id"])
        orig_wall_fg = gm.tiles["light"]["fg"][gm.tiles["tile_id"] == wall_tid].copy()

        rng = random.Random(42)
        place_death_gore(gm, enemy, rng)

        new_wall_fg = gm.tiles["light"]["fg"][gm.tiles["tile_id"] == wall_tid]
        assert np.array_equal(orig_wall_fg, new_wall_fg), \
            "Gore should not modify wall tiles"

    def test_gore_allowed_under_items(self):
        """Gore modifies the tile underneath items — items render on top."""
        from game.gore import place_death_gore

        gm = _make_gore_map()
        ex, ey = 10, 10
        # Place an item on a neighbour tile
        item = Entity(
            x=ex + 1, y=ey, char="!", color=(0, 255, 0),
            name="Medkit", blocks_movement=False,
            item={"type": "heal", "value": 5},
        )
        gm.entities.append(item)

        enemy = Entity(
            x=ex, y=ey, char="p", color=(200, 50, 50), name="Pirate",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=5, defense=1, power=3),
            organic=True, gore_color=(140, 20, 20),
        )
        rng = random.Random(42)

        place_death_gore(gm, enemy, rng)

        # The item tile CAN receive gore (tile data, not entity)
        floor_ch = int(tile_types.floor["light"]["ch"])
        gore_found = _count_modified_floor_tiles(gm) > 0
        assert gore_found, "Gore should be placed even when items are nearby"
        # The item entity is still present
        assert item in gm.entities

    def test_gore_skips_decorated_tiles(self):
        """Tiles that already have non-default chars (debris/decorations) should be skipped."""
        from game.gore import place_death_gore

        gm = _make_gore_map()
        ex, ey = 10, 10
        # Pre-decorate all neighbours with existing debris
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                for layer in ("dark", "light", "lit"):
                    gm.tiles[layer]["ch"][ex + dx, ey + dy] = ord(",")
                    gm.tiles[layer]["fg"][ex + dx, ey + dy] = (80, 80, 80)

        enemy = Entity(
            x=ex, y=ey, char="p", color=(200, 50, 50), name="Pirate",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=5, defense=1, power=3),
            organic=True, gore_color=(140, 20, 20),
        )
        rng = random.Random(42)

        place_death_gore(gm, enemy, rng)

        # Neighbour tiles should still have their original decoration color
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                fg = gm.tiles["light"]["fg"][ex + dx, ey + dy]
                assert tuple(fg) == (80, 80, 80), \
                    f"Decorated tile ({ex+dx},{ey+dy}) should not be overwritten"

    def test_gore_scales_with_max_hp(self):
        """Higher max_hp enemies should produce more gore tiles."""
        from game.gore import place_death_gore

        counts = {}
        for max_hp in (1, 5):
            gm = _make_gore_map()
            enemy = Entity(
                x=10, y=10, char="x", color=(200, 50, 50), name="Test",
                blocks_movement=True,
                fighter=Fighter(hp=0, max_hp=max_hp, defense=0, power=1),
                organic=True, gore_color=(140, 20, 20),
            )
            rng = random.Random(42)
            place_death_gore(gm, enemy, rng)
            counts[max_hp] = _count_modified_floor_tiles(gm)

        assert counts[5] > counts[1], \
            f"max_hp=5 should produce more gore ({counts[5]}) than max_hp=1 ({counts[1]})"

    def test_gore_modifies_all_lighting_layers(self):
        """Gore should update dark, light, and lit layers."""
        from game.gore import place_death_gore

        gm = _make_gore_map()
        enemy = Entity(
            x=10, y=10, char="p", color=(200, 50, 50), name="Pirate",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=5, defense=1, power=3),
            organic=True, gore_color=(140, 20, 20),
        )
        rng = random.Random(42)
        place_death_gore(gm, enemy, rng)

        floor_ch = int(tile_types.floor["light"]["ch"])
        # Find a modified tile
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = 10 + dx, 10 + dy
                if not gm.in_bounds(nx, ny):
                    continue
                if int(gm.tiles["light"]["ch"][nx, ny]) != floor_ch:
                    # This tile was modified — check all layers
                    assert int(gm.tiles["dark"]["ch"][nx, ny]) != int(tile_types.floor["dark"]["ch"]) or \
                           int(gm.tiles["lit"]["ch"][nx, ny]) != int(tile_types.floor["lit"]["ch"]), \
                        "Gore should modify dark/lit layers too"
                    return
        assert False, "Should have found at least one gore tile"

    def test_does_not_change_walkability(self):
        """Gore tiles must remain walkable."""
        from game.gore import place_death_gore

        gm = _make_gore_map()
        enemy = Entity(
            x=10, y=10, char="p", color=(200, 50, 50), name="Pirate",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=5, defense=1, power=3),
            organic=True, gore_color=(140, 20, 20),
        )
        rng = random.Random(42)
        floor_tid = int(tile_types.floor["tile_id"])
        is_floor = gm.tiles["tile_id"] == floor_tid

        place_death_gore(gm, enemy, rng)

        assert np.all(gm.tiles["walkable"][is_floor]), \
            "Gore should not change floor walkability"

    def test_default_gore_color_for_organic(self):
        """Entity with no explicit gore_color should default based on organic flag."""
        from game.gore import place_death_gore

        gm = _make_gore_map()
        enemy = Entity(
            x=10, y=10, char="r", color=(127, 127, 0), name="Rat",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=1, defense=0, power=1),
            organic=True,
        )
        rng = random.Random(42)
        place_death_gore(gm, enemy, rng)

        assert _count_modified_floor_tiles(gm) > 0, \
            "Should place gore even without explicit gore_color"

    def test_alien_green_blood(self):
        """Aliens with green gore_color should leave green-tinted splatter."""
        from game.gore import place_death_gore

        gm = _make_gore_map()
        enemy = Entity(
            x=10, y=10, char="a", color=(0, 200, 0), name="Alien",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=4, defense=0, power=2),
            organic=True, gore_color=(20, 140, 20),
        )
        rng = random.Random(42)
        place_death_gore(gm, enemy, rng)

        found_green = False
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = 10 + dx, 10 + dy
                if not gm.in_bounds(nx, ny):
                    continue
                fg = gm.tiles["light"]["fg"][nx, ny]
                if int(fg[1]) > 80 and int(fg[1]) > int(fg[0]) * 2:
                    found_green = True
                    break
            if found_green:
                break
        assert found_green, "Alien with green gore_color should leave green blood"


class TestGoreOnAlternateFloors:
    """Gore should work on all floor types, not just standard ship floor."""

    def _make_arena_with_tile(self, tile_type, w=20, h=20):
        """Create a GameMap with the given tile for interior."""
        from world.game_map import GameMap
        gm = GameMap(w, h)
        for x in range(1, w - 1):
            for y in range(1, h - 1):
                gm.tiles[x, y] = tile_type
        return gm

    def _has_gore(self, gm, tile_type, cx, cy):
        """Check if any tile near (cx,cy) has been modified from its default char."""
        default_ch = int(tile_type["light"]["ch"])
        tid = int(tile_type["tile_id"])
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = cx + dx, cy + dy
                if not gm.in_bounds(nx, ny):
                    continue
                if int(gm.tiles["tile_id"][nx, ny]) != tid:
                    continue
                if int(gm.tiles["light"]["ch"][nx, ny]) != default_ch:
                    return True
        return False

    def test_gore_on_dirt_floor(self):
        """Enemies killed on colony dirt floors should leave gore."""
        from game.gore import place_death_gore

        gm = self._make_arena_with_tile(tile_types.dirt_floor)
        enemy = Entity(
            x=10, y=10, char="p", color=(200, 50, 50), name="Pirate",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=5, defense=1, power=3),
            organic=True, gore_color=(140, 20, 20),
        )
        place_death_gore(gm, enemy, _random.Random(42))
        assert self._has_gore(gm, tile_types.dirt_floor, 10, 10), \
            "Gore should appear on dirt_floor tiles (colonies)"

    def test_gore_on_rock_floor(self):
        """Enemies killed on asteroid rock floors should leave gore."""
        from game.gore import place_death_gore

        gm = self._make_arena_with_tile(tile_types.rock_floor)
        enemy = Entity(
            x=10, y=10, char="b", color=(127, 0, 180), name="Bot",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=3, defense=0, power=2),
            organic=False,
        )
        place_death_gore(gm, enemy, _random.Random(42))
        assert self._has_gore(gm, tile_types.rock_floor, 10, 10), \
            "Gore should appear on rock_floor tiles (asteroids)"

    def test_gore_on_ground_tile(self):
        """Enemies killed on ground tiles should leave gore."""
        from game.gore import place_death_gore

        gm = self._make_arena_with_tile(tile_types.ground)
        enemy = Entity(
            x=10, y=10, char="a", color=(0, 200, 0), name="Alien",
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=4, defense=0, power=2),
            organic=True, gore_color=(20, 140, 20),
        )
        place_death_gore(gm, enemy, _random.Random(42))
        assert self._has_gore(gm, tile_types.ground, 10, 10), \
            "Gore should appear on ground tiles"


class TestDeathIntegration:
    """Integration: _apply_damage_and_death should trigger gore."""

    def test_killing_enemy_places_gore(self):
        """When an enemy dies via _apply_damage_and_death, gore should appear."""
        from game.actions import _apply_damage_and_death

        gm = _make_gore_map()
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 3))
        enemy = Entity(
            x=6, y=5, char="p", color=(200, 50, 50), name="Pirate",
            blocks_movement=True,
            fighter=Fighter(hp=1, max_hp=5, defense=0, power=2),
            organic=True, gore_color=(140, 20, 20),
        )
        gm.entities.extend([player, enemy])
        engine = MockEngine(gm, player)

        _apply_damage_and_death(engine, player, enemy, damage=5)

        assert enemy not in gm.entities
        assert _count_modified_floor_tiles(gm) > 0, \
            "Killing enemy should leave gore on the floor"

    def test_player_death_no_gore(self):
        """Player death should NOT place gore (different handling)."""
        from game.actions import _apply_damage_and_death

        gm = _make_gore_map()
        player = Entity(
            x=5, y=5, name="Player",
            fighter=Fighter(hp=1, max_hp=10, defense=0, power=1),
            organic=True, gore_color=(140, 20, 20),
        )
        enemy = Entity(
            x=6, y=5, char="p", color=(200, 50, 50), name="Pirate",
            blocks_movement=True,
            fighter=Fighter(hp=5, max_hp=5, defense=0, power=3),
        )
        gm.entities.extend([player, enemy])
        engine = MockEngine(gm, player)

        floor_tid = int(tile_types.floor["tile_id"])
        is_floor = gm.tiles["tile_id"] == floor_tid
        orig_chars = gm.tiles["light"]["ch"][is_floor].copy()

        _apply_damage_and_death(engine, enemy, player, damage=10)

        assert np.array_equal(gm.tiles["light"]["ch"][is_floor], orig_chars), \
            "Player death should not place gore"
