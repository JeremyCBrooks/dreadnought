"""Tests for reactor core pickup and fuel conversion."""
import numpy as np

from tests.conftest import make_arena, make_engine, MockEngine
from world import tile_types
from world.game_map import GameMap
from game.entity import Entity, Fighter
from game.actions import TakeReactorCoreAction


def _place_reactor(gm, x, y):
    """Place a reactor core tile with a light source at (x, y)."""
    gm.tiles[x, y] = tile_types.reactor_core
    gm.add_light_source(x, y, radius=4, color=(180, 80, 255), intensity=0.8)


def test_take_reactor_core_adds_to_inventory():
    engine = make_engine()
    _place_reactor(engine.game_map, 6, 5)
    result = TakeReactorCoreAction(1, 0).perform(engine, engine.player)
    assert result == 1
    assert len(engine.player.inventory) == 1
    item = engine.player.inventory[0]
    assert item.name == "Reactor Core"
    assert item.item["type"] == "reactor_core"
    assert item.item["value"] == 5


def test_take_reactor_core_replaces_tile():
    engine = make_engine()
    _place_reactor(engine.game_map, 6, 5)
    TakeReactorCoreAction(1, 0).perform(engine, engine.player)
    tid = int(engine.game_map.tiles["tile_id"][6, 5])
    assert tid == int(tile_types.floor["tile_id"])


def test_take_reactor_core_removes_light():
    engine = make_engine()
    _place_reactor(engine.game_map, 6, 5)
    assert len(engine.game_map.light_sources) == 1
    TakeReactorCoreAction(1, 0).perform(engine, engine.player)
    assert len(engine.game_map.light_sources) == 0


def test_take_reactor_core_blocked_full_inventory():
    engine = make_engine()
    _place_reactor(engine.game_map, 6, 5)
    # Set a capacity limit then fill to it
    engine.player.max_inventory = 6
    for i in range(engine.player.max_inventory):
        engine.player.inventory.append(
            Entity(char="x", color=(255, 255, 255), name=f"Junk {i}",
                   blocks_movement=False, item={"type": "junk"})
        )
    result = TakeReactorCoreAction(1, 0).perform(engine, engine.player)
    assert result == 0
    # Tile should remain reactor_core
    tid = int(engine.game_map.tiles["tile_id"][6, 5])
    assert tid == int(tile_types.reactor_core["tile_id"])


def test_take_reactor_core_not_reactor_tile():
    """Trying to take from a non-reactor tile does nothing."""
    engine = make_engine()
    result = TakeReactorCoreAction(1, 0).perform(engine, engine.player)
    assert result == 0


def test_reactor_core_converts_to_fuel_on_exit():
    from game.ship import Ship
    from ui.tactical_state import TacticalState

    engine = make_engine()
    engine.ship = Ship(fuel=3, max_fuel=10)
    # Give player a reactor core item
    core = Entity(char="\xea", color=(180, 80, 255), name="Reactor Core",
                  blocks_movement=False,
                  item={"type": "reactor_core", "value": 5})
    engine.player.inventory.append(core)

    state = TacticalState.__new__(TacticalState)
    state.location = None
    state.depth = 0
    state.exit_pos = None
    state._death_cause = None
    state.on_exit(engine)

    assert engine.ship.fuel == 8  # 3 + 5
    # Core should be removed from saved inventory
    saved_inv = engine._saved_player["inventory"]
    assert all(i.item.get("type") != "reactor_core" for i in saved_inv)


def test_reactor_core_fuel_capped_at_max():
    from game.ship import Ship
    from ui.tactical_state import TacticalState

    engine = make_engine()
    engine.ship = Ship(fuel=7, max_fuel=10)
    core = Entity(char="\xea", color=(180, 80, 255), name="Reactor Core",
                  blocks_movement=False,
                  item={"type": "reactor_core", "value": 5})
    engine.player.inventory.append(core)

    state = TacticalState.__new__(TacticalState)
    state.location = None
    state.depth = 0
    state.exit_pos = None
    state._death_cause = None
    state.on_exit(engine)

    assert engine.ship.fuel == 10  # capped at max


def test_reactor_core_no_conversion_without_ship():
    from ui.tactical_state import TacticalState

    engine = make_engine()
    engine.ship = None
    core = Entity(char="\xea", color=(180, 80, 255), name="Reactor Core",
                  blocks_movement=False,
                  item={"type": "reactor_core", "value": 5})
    engine.player.inventory.append(core)

    state = TacticalState.__new__(TacticalState)
    state.location = None
    state.depth = 0
    state.exit_pos = None
    state._death_cause = None
    state.on_exit(engine)

    # Core stays in inventory, no crash
    saved_inv = engine._saved_player["inventory"]
    assert any(i.item.get("type") == "reactor_core" for i in saved_inv)


def test_take_reactor_core_marks_hazards_dirty():
    """Extracting reactor core should trigger vacuum recalculation.

    A reactor_core tile (walkable=False) blocks vacuum propagation.
    When extracted and replaced with floor (walkable=True), vacuum must
    propagate through the now-open tile.
    """
    # Build a small map: space | breach wall | reactor | player room
    #   #######
    #   # .R.##
    #   #  .+X
    #   # ..###
    #   #######
    # R = reactor_core at (2,1), X = hull breach at (5,2)
    # Door at (4,2) is closed, sealing the room.
    # Once reactor is extracted -> floor, and door opened, vacuum floods.
    # But even with the door open, the key point is:
    # reactor blocks vacuum while present; after extraction vacuum propagates.

    # Layout: reactor sits between the open corridor and a breach
    #   ######
    #   #.R.X
    #   ######
    # Player at (1,1), reactor at (2,1), floor at (3,1), breach at (4,1)
    width, height = 6, 3
    gm = GameMap(width, height)
    for x in range(width):
        for y in range(height):
            gm.tiles[x, y] = tile_types.wall
    gm.tiles[1, 1] = tile_types.floor       # player
    gm.tiles[2, 1] = tile_types.reactor_core # blocks vacuum
    gm.tiles[3, 1] = tile_types.floor
    gm.tiles[4, 1] = tile_types.hull_breach
    gm.hull_breaches.append((4, 1))
    gm.has_space = True
    gm.add_light_source(2, 1, radius=4, color=(180, 80, 255), intensity=0.8)

    player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)

    # Before extraction: reactor blocks vacuum from reaching player tile
    gm.recalculate_hazards()
    vacuum = gm.hazard_overlays["vacuum"]
    assert vacuum[4, 1], "breach should be vacuum"
    assert vacuum[3, 1], "tile adjacent to breach should be vacuum"
    assert not vacuum[1, 1], "player tile shielded by reactor should NOT be vacuum"

    # Extract reactor (player at (1,1), reactor at (2,1) -> dx=1, dy=0)
    result = TakeReactorCoreAction(1, 0).perform(engine, player)
    assert result == 1

    # After extraction: hazards must be recalculated; vacuum now floods through
    gm.recalculate_hazards()  # only recalcs if _hazards_dirty
    vacuum = gm.hazard_overlays["vacuum"]
    assert vacuum[2, 1], "former reactor tile should now be vacuum"
    assert vacuum[1, 1], "player tile should now be vacuum (no longer shielded)"


def test_adjacent_interact_dirs_finds_reactor():
    engine = make_engine()
    _place_reactor(engine.game_map, 6, 5)
    from ui.tactical_state import TacticalState
    dirs = TacticalState._adjacent_interact_dirs(engine)
    assert any(kind == "reactor" for _, _, kind in dirs)
    assert any((dx, dy) == (1, 0) for dx, dy, _ in dirs)
