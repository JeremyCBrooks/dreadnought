"""Tests for reactor core pickup and fuel conversion."""
from tests.conftest import make_arena, make_engine, MockEngine
from world import tile_types
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


def test_adjacent_interact_dirs_finds_reactor():
    engine = make_engine()
    _place_reactor(engine.game_map, 6, 5)
    from ui.tactical_state import TacticalState
    dirs = TacticalState._adjacent_interact_dirs(engine)
    assert any(kind == "reactor" for _, _, kind in dirs)
    assert any((dx, dy) == (1, 0) for dx, dy, _ in dirs)
