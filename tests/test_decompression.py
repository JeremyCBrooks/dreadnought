"""Tests for explosive decompression system."""
from __future__ import annotations

import numpy as np
import pytest

from game.entity import Entity, Fighter
from game.environment import (
    _bfs_toward_breach,
    trigger_decompression,
    process_decompression_step,
    DECOMPRESSION_TILES_PER_STEP,
)
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
# BFS toward breach
# -------------------------------------------------------------------

class TestBfsTowardBreach:
    def test_straight_corridor(self):
        """Tiles in a straight corridor all pull toward the breach."""
        layout = [
            "#######",
            "#....X ",
            "#######",
        ]
        gm = _make_map(layout)
        sources = [(5, 1)]
        pull, _ = _bfs_toward_breach(gm, sources)
        # Tile at (4,1) should pull right toward breach at (5,1)
        assert pull[(4, 1)] == (1, 0)
        assert pull[(3, 1)] == (1, 0)
        assert pull[(2, 1)] == (1, 0)
        assert pull[(1, 1)] == (1, 0)

    def test_l_shaped_corridor(self):
        """Pull follows L-shaped corridor, not through walls."""
        layout = [
            "#####",
            "#...#",
            "###.#",
            "##X.#",
            "#####",
        ]
        gm = _make_map(layout)
        sources = [(2, 3)]
        pull, _ = _bfs_toward_breach(gm, sources)
        # (3,3) should pull left toward breach
        assert pull[(3, 3)] == (-1, 0)
        # (3,2) should pull down toward (3,3)
        assert pull[(3, 2)] == (0, 1)
        # (2,1) should pull right toward (3,1) which goes to (3,2)
        assert pull[(2, 1)] == (1, 0)

    def test_beyond_max_distance(self):
        """Tiles beyond max_distance are not included."""
        layout = [
            "#" + "." * 15 + "X ",
        ]
        gm = GameMap(18, 1)
        for x in range(18):
            gm.tiles[x, 0] = tile_types.floor
        gm.tiles[16, 0] = tile_types.hull_breach
        gm.tiles[17, 0] = tile_types.space
        gm.hull_breaches.append((16, 0))
        gm.has_space = True

        sources = [(16, 0)]
        pull, _ = _bfs_toward_breach(gm, sources, max_distance=5)
        # Within range
        assert (15, 0) in pull
        assert (11, 0) in pull
        # Beyond range
        assert (10, 0) not in pull

    def test_multiple_sources_uses_nearest(self):
        """With two sources, each tile pulls toward the nearest one."""
        layout = [
            "X.....X",
        ]
        gm = GameMap(7, 1)
        for x in range(7):
            gm.tiles[x, 0] = tile_types.floor
        gm.tiles[0, 0] = tile_types.hull_breach
        gm.tiles[6, 0] = tile_types.hull_breach
        gm.hull_breaches = [(0, 0), (6, 0)]
        gm.has_space = True

        sources = [(0, 0), (6, 0)]
        pull, _ = _bfs_toward_breach(gm, sources)
        # Middle tile (3,0) equidistant — BFS finds first source queued
        # Left tiles should pull left
        assert pull[(1, 0)] == (-1, 0)
        # Right tiles should pull right
        assert pull[(5, 0)] == (1, 0)


# -------------------------------------------------------------------
# trigger_decompression
# -------------------------------------------------------------------

class TestTriggerDecompression:
    def test_entities_in_newly_exposed_area_get_tagged(self):
        """Entities on newly-exposed tiles get decompression_moves set."""
        layout = [
            "#######",
            "#....X ",
            "#######",
        ]
        gm = _make_map(layout)
        enemy = Entity(x=2, y=1, name="Drone", fighter=Fighter(5, 5, 0, 1))
        gm.entities.append(enemy)
        engine = _make_engine(gm, 1, 1, env={"vacuum": 1}, suit=Suit("EVA", {"vacuum": 50}))

        newly_exposed = np.full((gm.width, gm.height), False, order="F")
        newly_exposed[1:6, 1] = True  # all corridor tiles exposed

        trigger_decompression(engine, [(5, 1)], newly_exposed)
        # Moves = distance_to_breach + 1 (enough to reach space)
        assert enemy.decompression_moves == 4  # dist 3 from breach + 1
        assert engine.player.decompression_moves == 5  # dist 4 from breach + 1

    def test_interactables_not_affected(self):
        """Interactable entities are NOT moved by decompression."""
        layout = [
            "#####",
            "#..X ",
            "#####",
        ]
        gm = _make_map(layout)
        console = Entity(x=1, y=1, name="Console", blocks_movement=False,
                         interactable={"kind": "console"})
        gm.entities.append(console)
        engine = _make_engine(gm, 2, 1, env={"vacuum": 1}, suit=Suit("EVA", {"vacuum": 50}))

        newly_exposed = np.full((gm.width, gm.height), False, order="F")
        newly_exposed[1:4, 1] = True

        trigger_decompression(engine, [(3, 1)], newly_exposed)
        assert console.decompression_moves == 0

    def test_items_are_affected(self):
        """Loose items ARE moved by decompression."""
        layout = [
            "#####",
            "#..X ",
            "#####",
        ]
        gm = _make_map(layout)
        item = Entity(x=1, y=1, name="Medkit", blocks_movement=False,
                      item={"type": "heal", "value": 5})
        gm.entities.append(item)
        engine = _make_engine(gm, 2, 1, env={"vacuum": 1}, suit=Suit("EVA", {"vacuum": 50}))

        newly_exposed = np.full((gm.width, gm.height), False, order="F")
        newly_exposed[1:4, 1] = True

        trigger_decompression(engine, [(3, 1)], newly_exposed)
        assert item.decompression_moves > 0

    def test_entities_not_on_newly_exposed_not_affected(self):
        """Entities outside newly-exposed area are not affected."""
        layout = [
            "#######",
            "#.+..X ",
            "#######",
        ]
        gm = _make_map(layout)
        # Entity on left side of closed door, NOT newly exposed
        safe_enemy = Entity(x=1, y=1, name="Safe", fighter=Fighter(5, 5, 0, 1))
        gm.entities.append(safe_enemy)
        engine = _make_engine(gm, 4, 1, env={"vacuum": 1}, suit=Suit("EVA", {"vacuum": 50}))

        newly_exposed = np.full((gm.width, gm.height), False, order="F")
        newly_exposed[3:6, 1] = True  # only right side exposed

        trigger_decompression(engine, [(5, 1)], newly_exposed)
        assert safe_enemy.decompression_moves == 0

    def test_entities_on_pressurized_side_pulled_toward_breach(self):
        """Entities on pressurized side of a newly-opened door get pulled."""
        layout = [
            "#########",
            "#.../.X  ",
            "#########",
        ]
        gm = _make_map(layout)
        # Player at (1,1), enemy at (2,1) on pressurized side.
        # Open door at (4,1), room at (5,1), breach at (6,1), space at (7,8).
        enemy = Entity(x=2, y=1, name="Drone", fighter=Fighter(5, 5, 0, 1))
        gm.entities.append(enemy)
        engine = _make_engine(gm, 1, 1, env={"vacuum": 1}, suit=Suit("EVA", {"vacuum": 50}))

        # Set up vacuum overlay (after door opened, entire area is vacuum)
        vacuum = np.full((gm.width, gm.height), False, order="F")
        vacuum[1:7, 1] = True
        gm.hazard_overlays["vacuum"] = vacuum

        # Corridor was pressurized; room was already vacuum
        newly_exposed = np.full((gm.width, gm.height), False, order="F")
        newly_exposed[1:5, 1] = True  # corridor + door newly exposed

        trigger_decompression(engine, [(6, 1)], newly_exposed)
        # Both player and enemy should be tagged — they're within range of the door
        assert engine.player.decompression_moves > 0
        assert enemy.decompression_moves > 0

    def test_message_logged(self):
        """Decompression event logs a message."""
        layout = [
            "#####",
            "#..X ",
            "#####",
        ]
        gm = _make_map(layout)
        engine = _make_engine(gm, 1, 1, env={"vacuum": 1}, suit=Suit("EVA", {"vacuum": 50}))

        newly_exposed = np.full((gm.width, gm.height), False, order="F")
        newly_exposed[1:4, 1] = True

        trigger_decompression(engine, [(3, 1)], newly_exposed)
        messages = [text for text, color in engine.message_log.messages]
        assert any("DECOMPRESSION" in m for m in messages)


# -------------------------------------------------------------------
# process_decompression_step
# -------------------------------------------------------------------

class TestProcessDecompressionStep:
    def test_moves_toward_breach(self):
        """Entity moves tiles_per_step tiles toward breach in one step."""
        layout = [
            "###########",
            "#........X ",
            "###########",
        ]
        gm = _make_map(layout)
        entity = Entity(x=1, y=1, name="Drone", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(entity)

        pull, _ = _bfs_toward_breach(gm, [(9, 1)])
        entity.decompression_moves = 9

        process_decompression_step(gm, entity, pull)
        # Should have moved 3 tiles right
        assert entity.x == 4
        assert entity.decompression_moves == 6

    def test_three_steps_moves_nine_tiles(self):
        """Over 3 turns of processing, entity moves 9 tiles total."""
        # Corridor: 1..10 are floor, 11 is breach (distance 10 from x=1)
        gm = GameMap(13, 3)
        for x in range(13):
            for y in range(3):
                gm.tiles[x, y] = tile_types.wall
        for x in range(1, 12):
            gm.tiles[x, 1] = tile_types.floor
        gm.tiles[11, 1] = tile_types.hull_breach
        gm.hull_breaches.append((11, 1))

        entity = Entity(x=1, y=1, name="Drone", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(entity)

        pull, _ = _bfs_toward_breach(gm, [(11, 1)])
        entity.decompression_moves = 9

        process_decompression_step(gm, entity, pull)
        assert entity.x == 4
        process_decompression_step(gm, entity, pull)
        assert entity.x == 7
        process_decompression_step(gm, entity, pull)
        assert entity.x == 10
        assert entity.decompression_moves == 0

    def test_wall_impact_damage(self):
        """Entity that hits a wall takes 1 HP * remaining decompression moves."""
        layout = [
            "#####",
            "#.#X ",
            "#####",
        ]
        gm = _make_map(layout)
        # Entity at (1,1), wall at (2,1), breach at (3,1)
        entity = Entity(x=1, y=1, name="Drone", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(entity)

        pull, _ = _bfs_toward_breach(gm, [(3, 1)])
        entity.decompression_moves = 9
        entity.decompression_direction = (1, 0)

        process_decompression_step(gm, entity, pull)
        # Can't move right (wall), can't slide (walls above/below), takes impact
        assert entity.decompression_moves == 0
        assert entity.fighter.hp < 10

    def test_perpendicular_slide(self):
        """Entity slides along wall when partially blocked."""
        layout = [
            "#######",
            "#.....#",
            "#..#..#",
            "#..#X  ",
            "#######",
        ]
        gm = _make_map(layout)
        # Entity at (2,2), wall at (3,2), breach at (4,3)
        entity = Entity(x=2, y=2, name="Drone", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(entity)

        pull, _ = _bfs_toward_breach(gm, [(4, 3)])
        entity.decompression_moves = 3

        process_decompression_step(gm, entity, pull)
        # Entity should have moved — exact position depends on BFS path
        assert entity.decompression_moves < 3 or entity.fighter.hp < 10

    def test_transition_to_drifting(self):
        """Entity reaching a space tile starts drifting."""
        # Breach tile is walkable, space is next to it
        gm = GameMap(5, 3)
        for x in range(5):
            for y in range(3):
                gm.tiles[x, y] = tile_types.wall
        gm.tiles[1, 1] = tile_types.floor
        gm.tiles[2, 1] = tile_types.hull_breach
        gm.tiles[3, 1] = tile_types.space
        gm.hull_breaches.append((2, 1))

        entity = Entity(x=1, y=1, name="Drone", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(entity)

        pull, _ = _bfs_toward_breach(gm, [(2, 1)])
        entity.decompression_moves = 9

        process_decompression_step(gm, entity, pull)
        # Entity should reach the breach and potentially space
        assert entity.x >= 2

    def test_blocking_entity_causes_impact(self):
        """Entity stops and takes damage when hitting another blocking entity."""
        layout = [
            "#######",
            "#....X ",
            "#######",
        ]
        gm = _make_map(layout)
        blocker = Entity(x=3, y=1, name="Wall-bot", fighter=Fighter(20, 20, 0, 1),
                         blocks_movement=True)
        gm.entities.append(blocker)
        entity = Entity(x=1, y=1, name="Drone", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(entity)

        pull, _ = _bfs_toward_breach(gm, [(5, 1)])
        entity.decompression_moves = 9

        process_decompression_step(gm, entity, pull)
        # Entity should stop before/at blocker and take impact damage
        assert entity.decompression_moves == 0
        assert entity.fighter.hp < 10

    def test_player_death_from_impact(self):
        """Player killed by wall impact has hp <= 0."""
        layout = [
            "#####",
            "#.#X ",
            "#####",
        ]
        gm = _make_map(layout)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(3, 10, 0, 1))
        gm.entities.append(player)

        pull, _ = _bfs_toward_breach(gm, [(3, 1)])
        player.decompression_moves = 9
        player.decompression_direction = (1, 0)

        process_decompression_step(gm, player, pull)
        assert player.fighter.hp <= 0


# -------------------------------------------------------------------
# Integration: recalculate_hazards sets pending decompression
# -------------------------------------------------------------------

class TestPendingDecompression:
    def test_opening_airlock_sets_pending(self):
        """Opening an airlock door causes pending decompression to be set."""
        gm = GameMap(7, 3)
        for x in range(7):
            for y in range(3):
                gm.tiles[x, y] = tile_types.wall
        gm.tiles[1, 1] = tile_types.floor
        gm.tiles[2, 1] = tile_types.floor
        gm.tiles[3, 1] = tile_types.airlock_floor
        gm.tiles[4, 1] = tile_types.airlock_ext_closed
        gm.tiles[5, 1] = tile_types.space
        gm.has_space = True

        # First recalculate with closed airlock — no vacuum
        gm.recalculate_hazards()
        assert gm._pending_decompression is None

        # Open the airlock
        gm.tiles[4, 1] = tile_types.airlock_ext_open
        gm._hazards_dirty = True
        gm.recalculate_hazards()

        # Should have pending decompression
        assert gm._pending_decompression is not None
        assert np.any(gm._pending_decompression["newly_exposed"])

    def test_no_pending_when_already_exposed(self):
        """Re-recalculating without changes does not create pending decompression."""
        layout = [
            "#####",
            "#..X ",
            "#####",
        ]
        gm = _make_map(layout)
        gm.recalculate_hazards()
        # First time: no pending (no baseline to compare against)
        pending1 = gm._pending_decompression
        assert pending1 is None

        # Clear it and re-dirty
        gm._pending_decompression = None
        gm._hazards_dirty = True
        gm.recalculate_hazards()
        # No new tiles exposed — no pending
        assert gm._pending_decompression is None

    def test_first_recalculate_with_breach_no_decompression(self):
        """First recalculate on a map with hull breach does NOT trigger decompression."""
        layout = [
            "#######",
            "#....X ",
            "#######",
        ]
        gm = _make_map(layout)
        gm.recalculate_hazards()
        assert gm._pending_decompression is None

    def test_entities_already_in_vacuum_not_affected(self):
        """Entities on tiles that were already vacuum are not tagged."""
        layout = [
            "#######",
            "#../.X ",
            "#######",
        ]
        gm = _make_map(layout)
        # Establish baseline vacuum (breach already open)
        gm.recalculate_hazards()

        # Place entity in the already-vacuum area
        enemy = Entity(x=4, y=1, name="Drone", fighter=Fighter(5, 5, 0, 1))
        gm.entities.append(enemy)
        engine = _make_engine(gm, 1, 1, env={"vacuum": 1}, suit=Suit("EVA", {"vacuum": 50}))

        # newly_exposed covers only the breach tile area
        newly_exposed = np.full((gm.width, gm.height), False, order="F")
        newly_exposed[5, 1] = True  # only the breach itself is "new"

        trigger_decompression(engine, [(5, 1)], newly_exposed)
        # Enemy at (4,1) was already in vacuum — should NOT be tagged
        assert enemy.decompression_moves == 0

    def test_entity_blown_past_breach_into_space(self):
        """Entity near breach gets pushed through into space with drifting=True."""
        gm = GameMap(6, 3)
        for x in range(6):
            for y in range(3):
                gm.tiles[x, y] = tile_types.wall
        gm.tiles[1, 1] = tile_types.floor
        gm.tiles[2, 1] = tile_types.floor
        gm.tiles[3, 1] = tile_types.hull_breach
        gm.tiles[4, 1] = tile_types.space
        gm.hull_breaches.append((3, 1))
        gm.has_space = True

        entity = Entity(x=1, y=1, name="Drone", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(entity)

        pull, _ = _bfs_toward_breach(gm, [(3, 1)])
        entity.decompression_moves = 9
        entity.decompression_direction = (1, 0)

        process_decompression_step(gm, entity, pull)
        # Entity should end up on space tile, drifting
        assert entity.x == 4
        assert entity.y == 1
        assert entity.drifting is True
        assert entity.drift_direction == (1, 0)
        assert entity.decompression_moves == 0

    def test_entity_at_breach_source_continues_into_space(self):
        """Entity on breach tile with decompression_moves continues into adjacent space."""
        gm = GameMap(5, 3)
        for x in range(5):
            for y in range(3):
                gm.tiles[x, y] = tile_types.wall
        gm.tiles[1, 1] = tile_types.floor
        gm.tiles[2, 1] = tile_types.hull_breach
        gm.tiles[3, 1] = tile_types.space
        gm.hull_breaches.append((2, 1))
        gm.has_space = True

        # Entity starts ON the breach tile
        entity = Entity(x=2, y=1, name="Drone", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(entity)

        pull, _ = _bfs_toward_breach(gm, [(2, 1)])
        entity.decompression_moves = 9
        entity.decompression_direction = (1, 0)  # original pull direction

        process_decompression_step(gm, entity, pull)
        # Should find adjacent space tile and move into it
        assert entity.x == 3
        assert entity.y == 1
        assert entity.drifting is True
        assert entity.decompression_moves == 0

    def test_entity_at_breach_blown_toward_perpendicular_space(self):
        """Entity at breach finds space in perpendicular direction."""
        # Space is above the breach, entity approaches from the right
        #   S
        #  .X.
        gm = GameMap(5, 5)
        for x in range(5):
            for y in range(5):
                gm.tiles[x, y] = tile_types.wall
        gm.tiles[1, 2] = tile_types.floor
        gm.tiles[2, 2] = tile_types.hull_breach
        gm.tiles[3, 2] = tile_types.floor
        gm.tiles[2, 1] = tile_types.space  # space above breach
        gm.hull_breaches.append((2, 2))
        gm.has_space = True

        entity = Entity(x=2, y=2, name="Drone", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(entity)

        pull, _ = _bfs_toward_breach(gm, [(2, 2)])
        entity.decompression_moves = 9
        entity.decompression_direction = (-1, 0)  # original approach from right

        process_decompression_step(gm, entity, pull)
        # Should find space above and be blown into it
        assert entity.x == 2
        assert entity.y == 1
        assert entity.drifting is True
        assert entity.decompression_moves == 0


# -------------------------------------------------------------------
# Integration: door opens to vacuum room with hull breach
# -------------------------------------------------------------------

class TestDoorToVacuumRoom:
    """Model the full scenario: pressurized corridor, door opens to a vacuum
    room that has a hull breach to space.  Entity in the corridor should be
    blown through the door, across the room, out the breach, into space."""

    def _setup(self, corridor_len: int = 3, room_len: int = 3):
        """Build corridor+door+room+breach+space and return (engine, entity).

        Layout (y=1): corridor(1..corridor_len) + door + room + breach + space
        """
        door_x = 1 + corridor_len
        room_start = door_x + 1
        breach_x = room_start + room_len
        space_x = breach_x + 1
        width = space_x + 2  # +wall+space buffer

        gm = GameMap(width, 3)
        for x in range(width):
            for y in range(3):
                gm.tiles[x, y] = tile_types.wall
        # Corridor
        for x in range(1, door_x):
            gm.tiles[x, 1] = tile_types.floor
        # Door (starts closed)
        gm.tiles[door_x, 1] = tile_types.door_closed
        # Room
        for x in range(room_start, breach_x):
            gm.tiles[x, 1] = tile_types.floor
        # Breach + space
        gm.tiles[breach_x, 1] = tile_types.hull_breach
        gm.hull_breaches.append((breach_x, 1))
        gm.tiles[space_x, 1] = tile_types.space
        gm.has_space = True

        # Establish baseline vacuum (room is vacuum through breach)
        gm.recalculate_hazards()
        assert gm._pending_decompression is None  # first call, no decompression

        # Place entity at start of corridor
        entity = Entity(x=1, y=1, name="Drone", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(entity)

        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player, suit=Suit("EVA", {"vacuum": 50}),
                            environment={"vacuum": 1})

        return engine, entity, door_x, breach_x, space_x

    def test_small_room_entity_reaches_space(self):
        """With a small vacuum room, entity is blown all the way to space."""
        engine, entity, door_x, breach_x, space_x = self._setup(
            corridor_len=3, room_len=3,
        )
        gm = engine.game_map

        # Open the door
        gm.tiles[door_x, 1] = tile_types.door_open
        gm._hazards_dirty = True
        gm.recalculate_hazards()

        pending = gm._pending_decompression
        assert pending is not None, "Door opening should trigger decompression"

        pull_dirs = trigger_decompression(
            engine, pending["breach_sources"], pending["newly_exposed"],
        )

        # Entity should be tagged
        assert entity.decompression_moves > 0
        # Moves = distance to breach + 1 (to exit into space)
        assert entity.decompression_moves == breach_x - 1 + 1  # entity at x=1

        # Process decompression over multiple steps
        while entity.decompression_moves > 0:
            process_decompression_step(gm, entity, pull_dirs)

        # Entity should be in space, drifting
        assert entity.x == space_x
        assert entity.drifting is True

    def test_large_room_entity_tagged_but_stops_short(self):
        """With a large vacuum room, entity near the door IS tagged (range is
        from door) but stops after DECOMPRESSION_RANGE tiles, not at space."""
        engine, entity, door_x, breach_x, space_x = self._setup(
            corridor_len=2, room_len=12,
        )
        gm = engine.game_map

        # Open the door
        gm.tiles[door_x, 1] = tile_types.door_open
        gm._hazards_dirty = True
        gm.recalculate_hazards()

        pending = gm._pending_decompression
        assert pending is not None

        pull_dirs = trigger_decompression(
            engine, pending["breach_sources"], pending["newly_exposed"],
        )

        # Entity at x=1, breach at x=15.  Distance = 14.
        # Old code would miss this entirely (range measured from breach).
        assert entity.decompression_moves > 0, (
            "Entity near door should be tagged even when breach is far"
        )
        from game.environment import DECOMPRESSION_RANGE
        assert entity.decompression_moves == DECOMPRESSION_RANGE

        start_x = entity.x
        while entity.decompression_moves > 0:
            process_decompression_step(gm, entity, pull_dirs)

        # Entity moved exactly DECOMPRESSION_RANGE tiles, stops short of space
        assert entity.x == start_x + DECOMPRESSION_RANGE
        assert entity.x < space_x
        assert not entity.drifting

    def test_entity_far_from_door_not_tagged(self):
        """Entity far from the door (beyond DECOMPRESSION_RANGE) is not tagged."""
        # Build a very long corridor
        engine, entity, door_x, breach_x, space_x = self._setup(
            corridor_len=15, room_len=3,
        )
        gm = engine.game_map
        # Move entity to far end of corridor (15 tiles from door)
        entity.x = 1

        gm.tiles[door_x, 1] = tile_types.door_open
        gm._hazards_dirty = True
        gm.recalculate_hazards()

        pending = gm._pending_decompression
        assert pending is not None

        trigger_decompression(
            engine, pending["breach_sources"], pending["newly_exposed"],
        )

        # Entity at x=1, door at x=16, distance=15 > DECOMPRESSION_RANGE=10
        assert entity.decompression_moves == 0, (
            "Entity too far from door should not be tagged"
        )
