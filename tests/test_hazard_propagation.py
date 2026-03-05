"""Tests for per-tile hazard propagation and hull breaches."""
from __future__ import annotations

import numpy as np
import pytest

from game.entity import Entity, Fighter
from game.environment import _flood_fill_hazard, apply_environment_tick, apply_environment_tick_entity
from game.suit import Suit
from tests.conftest import MockEngine
from world import tile_types
from world.game_map import GameMap


def _make_map(layout: list[str]) -> GameMap:
    """Build a GameMap from an ASCII layout.

    Legend:
        '#' = wall
        '.' = floor
        '+' = closed door
        '/' = open door
        'X' = hull_breach
        ' ' = space
    """
    height = len(layout)
    width = max(len(row) for row in layout)
    gm = GameMap(width, height)
    tile_map = {
        "#": tile_types.wall,
        ".": tile_types.floor,
        "+": tile_types.door_closed,
        "/": tile_types.door_open,
        "X": tile_types.hull_breach,
        " ": tile_types.space,
    }
    for y, row in enumerate(layout):
        for x, ch in enumerate(row):
            gm.tiles[x, y] = tile_map.get(ch, tile_types.wall)
            if ch == "X":
                gm.hull_breaches.append((x, y))
    gm.has_space = True
    return gm


def _make_engine(gm: GameMap, px: int, py: int, env=None, suit=None):
    player = Entity(x=px, y=py, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player, suit=suit, environment=env)
    return engine


# -------------------------------------------------------------------
# Flood fill
# -------------------------------------------------------------------

class TestFloodFill:
    def test_sealed_room_no_vacuum(self):
        """Sealed room with closed doors has no vacuum inside."""
        layout = [
            "#######",
            "#....##",
            "#....+X",
            "#....##",
            "#######",
        ]
        gm = _make_map(layout)
        gm.recalculate_hazards()
        overlay = gm.hazard_overlays["vacuum"]
        # Interior floor tiles should NOT have vacuum (door is closed)
        assert not overlay[1, 1]
        assert not overlay[2, 1]
        assert not overlay[3, 2]
        # The hull breach itself should have vacuum
        assert overlay[6, 2]

    def test_open_door_floods_vacuum(self):
        """Opening a door adjacent to a breach floods connected rooms."""
        layout = [
            "######",
            "#....#",
            "#....#",
            "#/##X ",
            "######",
        ]
        gm = _make_map(layout)
        gm.recalculate_hazards()
        overlay = gm.hazard_overlays["vacuum"]
        # Breach is vacuum source
        assert overlay[4, 3]
        # Open door lets vacuum through — interior should be flooded
        assert overlay[1, 1]
        assert overlay[2, 2]

    def test_closed_door_blocks_propagation(self):
        """Closed door blocks vacuum from reaching sealed room."""
        layout = [
            "#########",
            "#...+...#",
            "#...#...#",
            "#...#..X ",
            "#########",
        ]
        gm = _make_map(layout)
        gm.recalculate_hazards()
        overlay = gm.hazard_overlays["vacuum"]
        # Right side (has breach) should have vacuum
        assert overlay[5, 1]
        assert overlay[7, 3]
        # Left side (sealed by door) should not
        assert not overlay[1, 1]
        assert not overlay[2, 2]

    def test_hull_breach_is_vacuum_source(self):
        """Hull breach tile itself is marked as vacuum."""
        layout = [
            "###",
            "#X ",
            "###",
        ]
        gm = _make_map(layout)
        gm.recalculate_hazards()
        assert gm.hazard_overlays["vacuum"][1, 1]

    def test_no_sources_no_vacuum(self):
        """Map with no breaches or open airlocks has no vacuum overlay."""
        layout = [
            "###",
            "#.#",
            "###",
        ]
        gm = _make_map(layout)
        gm.recalculate_hazards()
        # No vacuum sources — overlay removed
        assert "vacuum" not in gm.hazard_overlays


# -------------------------------------------------------------------
# Dirty flag
# -------------------------------------------------------------------

class TestDirtyFlag:
    def test_toggle_door_sets_dirty(self):
        """Opening/closing a door sets the hazards dirty flag."""
        layout = [
            "#####",
            "#.+.#",
            "#####",
        ]
        gm = _make_map(layout)
        gm._hazards_dirty = False

        from game.actions import ToggleDoorAction
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player)
        engine.environment = {}
        engine.suit = Suit("Test", {})

        ToggleDoorAction(1, 0).perform(engine, player)
        assert gm._hazards_dirty

    def test_recalculate_clears_dirty(self):
        """recalculate_hazards clears the dirty flag."""
        gm = _make_map(["###", "#.#", "###"])
        assert gm._hazards_dirty
        gm.recalculate_hazards()
        assert not gm._hazards_dirty

    def test_recalculate_updates_overlay(self):
        """After toggling door, recalculate produces correct overlay."""
        layout = [
            "#####",
            "#.+X ",
            "#####",
        ]
        gm = _make_map(layout)
        gm.recalculate_hazards()
        # Door is closed — floor at (1,1) should be safe
        assert not gm.hazard_overlays["vacuum"][1, 1]

        # Open the door
        gm.tiles[2, 1] = tile_types.door_open
        gm._hazards_dirty = True
        gm.recalculate_hazards()
        # Now vacuum should flood in
        assert gm.hazard_overlays["vacuum"][1, 1]


# -------------------------------------------------------------------
# Player environment tick (per-tile)
# -------------------------------------------------------------------

class TestPlayerHazardTick:
    def test_player_on_vacuum_tile_takes_damage(self):
        """Player standing on a vacuum tile with depleted suit takes damage."""
        layout = [
            "####",
            "#.X ",
            "####",
        ]
        gm = _make_map(layout)
        suit = Suit("Empty", {"vacuum": 0})
        engine = _make_engine(gm, 1, 1, env={"vacuum": 1}, suit=suit)
        gm.recalculate_hazards()
        # Player at (1,1) — vacuum has flooded through open hull breach
        assert gm.hazard_overlays["vacuum"][1, 1]
        apply_environment_tick(engine)
        assert engine.player.fighter.hp < 10

    def test_player_on_safe_tile_no_damage(self):
        """Player in sealed room takes no damage even with vacuum env."""
        layout = [
            "######",
            "#..+X ",
            "######",
        ]
        gm = _make_map(layout)
        suit = Suit("Empty", {"vacuum": 0})
        engine = _make_engine(gm, 1, 1, env={"vacuum": 1}, suit=suit)
        gm.recalculate_hazards()
        assert not gm.hazard_overlays["vacuum"][1, 1]
        apply_environment_tick(engine)
        assert engine.player.fighter.hp == 10


# -------------------------------------------------------------------
# Enemy environment tick
# -------------------------------------------------------------------

class TestEnemyHazardTick:
    def test_enemy_on_vacuum_takes_damage(self):
        """Enemy on vacuum tile takes 1 HP damage."""
        layout = [
            "####",
            "#.X ",
            "####",
        ]
        gm = _make_map(layout)
        enemy = Entity(x=1, y=1, name="Drone", fighter=Fighter(3, 3, 0, 1))
        gm.entities.append(enemy)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player, environment={"vacuum": 1}, suit=Suit("Test", {"vacuum": 50}))
        gm.recalculate_hazards()
        apply_environment_tick_entity(engine, enemy)
        assert enemy.fighter.hp == 2

    def test_enemy_dies_from_vacuum(self):
        """Enemy with 1 HP on vacuum tile dies and is removed."""
        layout = [
            "####",
            "#.X ",
            "####",
        ]
        gm = _make_map(layout)
        enemy = Entity(x=1, y=1, name="Drone", fighter=Fighter(1, 1, 0, 1))
        gm.entities.append(enemy)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player, environment={"vacuum": 1}, suit=Suit("Test", {"vacuum": 50}))
        gm.recalculate_hazards()
        apply_environment_tick_entity(engine, enemy)
        assert enemy.fighter.hp <= 0
        assert enemy not in gm.entities

    def test_enemy_on_safe_tile_no_damage(self):
        """Enemy in sealed room takes no damage."""
        layout = [
            "######",
            "#..+X ",
            "######",
        ]
        gm = _make_map(layout)
        enemy = Entity(x=1, y=1, name="Drone", fighter=Fighter(3, 3, 0, 1))
        gm.entities.append(enemy)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player, environment={"vacuum": 1}, suit=Suit("Test", {"vacuum": 50}))
        gm.recalculate_hazards()
        apply_environment_tick_entity(engine, enemy)
        assert enemy.fighter.hp == 3


# -------------------------------------------------------------------
# Low gravity remains global
# -------------------------------------------------------------------

class TestLowGravityGlobal:
    def test_low_gravity_unaffected_by_per_tile(self):
        """low_gravity is in GLOBAL_HAZARDS and NON_DAMAGING — unaffected by overlays."""
        from game.environment import GLOBAL_HAZARDS, NON_DAMAGING_HAZARDS
        assert "low_gravity" in GLOBAL_HAZARDS
        assert "low_gravity" in NON_DAMAGING_HAZARDS


# -------------------------------------------------------------------
# BumpAction from hull_breach to space
# -------------------------------------------------------------------

class TestBumpFromBreach:
    def test_step_into_space_from_breach(self):
        """Player on hull_breach tile can step into adjacent space tile."""
        layout = [
            "###",
            "#X ",
            "###",
        ]
        gm = _make_map(layout)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player)
        engine.environment = {"vacuum": 1}
        engine.suit = Suit("EVA", {"vacuum": 50})

        from game.actions import BumpAction
        result = BumpAction(1, 0).perform(engine, player)
        assert result == 1
        assert player.x == 2
        assert player.y == 1
        assert player.drifting

    def test_cannot_step_into_space_from_floor(self):
        """Player on regular floor cannot step into space."""
        layout = [
            "###",
            "#. ",
            "###",
        ]
        gm = _make_map(layout)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player)
        engine.environment = {}
        engine.suit = Suit("Test", {})

        from game.actions import BumpAction
        result = BumpAction(1, 0).perform(engine, player)
        # Space is not walkable, MovementAction should fail
        assert result == 0
        assert player.x == 1


# -------------------------------------------------------------------
# get_hazards_at
# -------------------------------------------------------------------

class TestGetHazardsAt:
    def test_returns_hazard_names(self):
        layout = [
            "###",
            "#X ",
            "###",
        ]
        gm = _make_map(layout)
        gm.recalculate_hazards()
        hazards = gm.get_hazards_at(1, 1)
        assert "vacuum" in hazards

    def test_returns_empty_for_safe_tile(self):
        layout = [
            "#####",
            "#.+X ",
            "#####",
        ]
        gm = _make_map(layout)
        gm.recalculate_hazards()
        hazards = gm.get_hazards_at(1, 1)
        assert len(hazards) == 0


# -------------------------------------------------------------------
# Airlock as vacuum source
# -------------------------------------------------------------------

class TestAirlockVacuumSource:
    def _make_airlock_map(self, ext_open: bool):
        """Build a map with an airlock chamber and optional open exterior door."""
        ext_tile = tile_types.airlock_ext_open if ext_open else tile_types.airlock_ext_closed
        gm = GameMap(7, 3)
        # ###E S##  (E=exterior door, S=space)
        # #./.=.##  (. floor, / open door, = airlock floor)
        # #######
        for x in range(7):
            for y in range(3):
                gm.tiles[x, y] = tile_types.wall
        gm.tiles[1, 1] = tile_types.floor
        gm.tiles[2, 1] = tile_types.door_open
        gm.tiles[3, 1] = tile_types.airlock_floor
        gm.tiles[4, 1] = ext_tile
        gm.tiles[5, 1] = tile_types.space
        gm.has_space = True
        return gm

    def test_open_airlock_floods_vacuum(self):
        """Open exterior airlock door is a vacuum source."""
        gm = self._make_airlock_map(ext_open=True)
        gm.recalculate_hazards()
        overlay = gm.hazard_overlays["vacuum"]
        # Airlock floor and connected interior should have vacuum
        assert overlay[3, 1]  # airlock floor
        assert overlay[1, 1]  # interior floor (through open door)

    def test_closed_airlock_no_interior_vacuum(self):
        """Closed exterior airlock door does not produce vacuum on interior tiles.

        Space tiles still have vacuum (they always do), but the interior
        and airlock floor should be safe.
        """
        gm = self._make_airlock_map(ext_open=False)
        gm.recalculate_hazards()
        overlay = gm.hazard_overlays.get("vacuum")
        # Space tiles have vacuum, so overlay exists
        assert overlay is not None
        assert overlay[5, 1]   # space tile has vacuum
        # But interior and airlock tiles do NOT
        assert not overlay[1, 1]  # interior floor
        assert not overlay[3, 1]  # airlock floor


# -------------------------------------------------------------------
# Switch dirty flag
# -------------------------------------------------------------------

class TestSwitchDirtyFlag:
    def test_toggle_switch_sets_dirty(self):
        """Toggling an airlock switch sets the hazards dirty flag."""
        gm = GameMap(7, 3)
        for x in range(7):
            for y in range(3):
                gm.tiles[x, y] = tile_types.wall
        gm.tiles[1, 1] = tile_types.floor
        gm.tiles[2, 1] = tile_types.airlock_floor
        gm.tiles[3, 1] = tile_types.airlock_switch_off
        gm.tiles[4, 1] = tile_types.airlock_ext_closed
        gm.tiles[5, 1] = tile_types.space
        gm.has_space = True
        gm.airlocks = [{"switch": (3, 1), "exterior_door": (4, 1), "direction": (1, 0)}]
        gm._hazards_dirty = False

        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player)
        engine.environment = {"vacuum": 1}
        engine.suit = Suit("EVA", {"vacuum": 50})

        from game.actions import ToggleSwitchAction
        result = ToggleSwitchAction(2, 0).perform(engine, player)
        assert result == 1
        assert gm._hazards_dirty


# -------------------------------------------------------------------
# Suit pool drains on vacuum tile, then damages
# -------------------------------------------------------------------

class TestSuitPoolDrain:
    def test_suit_pool_drains_on_vacuum_tile(self):
        """Suit pool decrements when player is on a vacuum tile."""
        layout = [
            "####",
            "#.X ",
            "####",
        ]
        gm = _make_map(layout)
        suit = Suit("EVA", {"vacuum": 10})
        engine = _make_engine(gm, 1, 1, env={"vacuum": 1}, suit=suit)
        gm.recalculate_hazards()
        for _ in range(Suit.DRAIN_INTERVAL):
            apply_environment_tick(engine)
        assert suit.current_pools["vacuum"] == 9
        assert engine.player.fighter.hp == 10  # still protected

    def test_suit_pool_no_drain_on_safe_tile(self):
        """Suit pool does NOT drain when player is on a safe tile."""
        layout = [
            "######",
            "#..+X ",
            "######",
        ]
        gm = _make_map(layout)
        suit = Suit("EVA", {"vacuum": 10})
        engine = _make_engine(gm, 1, 1, env={"vacuum": 1}, suit=suit)
        gm.recalculate_hazards()
        apply_environment_tick(engine)
        assert suit.current_pools["vacuum"] == 10  # no drain — sealed room
        assert engine.player.fighter.hp == 10
