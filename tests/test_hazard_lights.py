"""Tests for lights turning red in hazard zones."""
import random

import numpy as np

from world.game_map import GameMap
from world import tile_types
from world.lighting import LightSource
from game.entity import Entity, Fighter


def _make_breached_ship(light_x=5, light_y=5):
    """Ship map with a corridor, a light, and a hull breach.

    Layout (10x10):
      Walls around the edge, floor interior.
      Breach at (1, 5) — adjacent to floor at (2, 5).
      Light at (light_x, light_y).
    """
    gm = GameMap(10, 10)
    for x in range(1, 9):
        for y in range(1, 9):
            gm.tiles[x, y] = tile_types.floor
    # Hull breach opens vacuum into the interior
    gm.tiles[1, 5] = tile_types.hull_breach
    gm.hull_breaches.append((1, 5))
    gm.has_space = True
    # Add light
    gm.add_light_source(light_x, light_y, radius=4,
                        color=(200, 190, 170), intensity=0.5)
    return gm


class TestHazardLightColor:
    def test_light_turns_red_in_vacuum(self):
        """A light on a floor tile under vacuum should turn red."""
        from world.game_map import GameMap

        gm = _make_breached_ship(light_x=2, light_y=5)
        gm.recalculate_hazards()
        gm.update_hazard_lights()

        ls = gm.light_sources[0]
        # Should be red-ish now
        assert ls.color[0] > ls.color[1], \
            f"Light in vacuum should be red, got {ls.color}"
        assert ls.color[0] > ls.color[2], \
            f"Light in vacuum should be red, got {ls.color}"

    def test_light_stays_normal_outside_hazard(self):
        """A light far from any breach should keep its original color."""
        gm = _make_breached_ship(light_x=8, light_y=8)
        # Close the breach so vacuum doesn't flood
        gm.tiles[1, 5] = tile_types.wall
        gm.hull_breaches.clear()
        gm._hazards_dirty = True
        gm.recalculate_hazards()
        gm.update_hazard_lights()

        ls = gm.light_sources[0]
        assert ls.color == (200, 190, 170), \
            f"Light outside hazard should keep original color, got {ls.color}"

    def test_light_on_wall_adjacent_to_space_not_red(self):
        """A light on a hull wall next to space should NOT turn red.

        Only adjacent walkable (floor) tiles count for hazard detection.
        """
        gm = GameMap(10, 10)
        for x in range(1, 9):
            for y in range(1, 9):
                gm.tiles[x, y] = tile_types.floor
        # Make outer edge space (simulating hull conversion)
        for x in range(10):
            gm.tiles[x, 0] = tile_types.space
            gm.tiles[x, 9] = tile_types.space
        for y in range(10):
            gm.tiles[0, y] = tile_types.space
            gm.tiles[9, y] = tile_types.space
        # Walls at row 1 (hull boundary, adjacent to space)
        for x in range(1, 9):
            gm.tiles[x, 1] = tile_types.wall
        gm.has_space = True

        # Light on a hull wall tile — space is adjacent but NO floor is under vacuum
        gm.add_light_source(5, 1, radius=4, color=(200, 190, 170), intensity=0.5)
        gm.recalculate_hazards()
        gm.update_hazard_lights()

        ls = gm.light_sources[0]
        assert ls.color == (200, 190, 170), \
            f"Hull wall light should not turn red, got {ls.color}"

    def test_light_restores_when_hazard_cleared(self):
        """If vacuum is sealed (breach repaired), light should revert."""
        gm = _make_breached_ship(light_x=2, light_y=5)
        gm.recalculate_hazards()
        gm.update_hazard_lights()

        ls = gm.light_sources[0]
        assert ls.color[0] > ls.color[1], "Should be red while breached"

        # Seal the breach
        gm.tiles[1, 5] = tile_types.wall
        gm.hull_breaches.clear()
        gm._hazards_dirty = True
        gm.recalculate_hazards()
        gm.update_hazard_lights()

        assert ls.color == (200, 190, 170), \
            f"Light should revert after hazard cleared, got {ls.color}"

    def test_adjacent_floor_with_entity_still_checked(self):
        """Floor tiles occupied by entities should still be checked for hazard."""
        gm = _make_breached_ship(light_x=2, light_y=5)
        # Place an entity on the floor tile adjacent to the light
        gm.entities.append(Entity(
            x=3, y=5, name="Crate", char="=", color=(100, 100, 100),
            blocks_movement=False,
        ))
        gm.recalculate_hazards()
        gm.update_hazard_lights()

        ls = gm.light_sources[0]
        assert ls.color[0] > ls.color[1], \
            f"Entity on floor should not prevent hazard detection, got {ls.color}"

    def test_light_map_uses_red_color(self):
        """The computed light map should reflect the red color."""
        gm = _make_breached_ship(light_x=2, light_y=5)
        gm.recalculate_hazards()
        gm.update_hazard_lights()

        lm = gm.get_light_map()
        # At the light source position, red channel should dominate
        r, g, b = lm[2, 5]
        assert r > g and r > b, \
            f"Light map at hazard light should be red-dominant, got ({r:.2f}, {g:.2f}, {b:.2f})"
