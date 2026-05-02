"""Tests for Ship cargo sync methods (Task 1 — Explore Ship feature)."""

from __future__ import annotations

import numpy as np

from game.entity import Entity
from game.ship import Ship
from tests.conftest import make_arena, make_engine, make_heal_item, make_weapon
from world import tile_types
from world.dungeon_gen import RectRoom

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_cargo_room(cx: int = 4, cy: int = 4) -> RectRoom:
    """Return a RectRoom labelled 'cargo' whose center is (cx, cy)."""
    # RectRoom(x, y, width, height) — center = (x1+x2)//2, (y1+y2)//2
    # x1=cx-1, x2=cx+1 → center_x = cx; same for y
    return RectRoom(cx - 1, cy - 1, 2, 2, label="cargo")


def make_decoration(x: int = 5, y: int = 5) -> Entity:
    """Non-blocking entity with item=None (a decoration / interactable)."""
    return Entity(x=x, y=y, char="T", name="Terminal", blocks_movement=False, item=None)


def make_blocker(x: int = 5, y: int = 5) -> Entity:
    """Blocking entity (enemy/player stand-in)."""
    return Entity(x=x, y=y, char="@", name="Guard", blocks_movement=True)


# ---------------------------------------------------------------------------
# 1. Initial state
# ---------------------------------------------------------------------------


def test_ship_initial_game_map_is_none():
    ship = Ship()
    assert ship.game_map is None
    assert ship.rooms is None


# ---------------------------------------------------------------------------
# 2-4. materialize_cargo — happy path
# ---------------------------------------------------------------------------


def test_materialize_cargo_places_items_in_cargo_hold():
    """Items from cargo should appear on the map near the cargo-room center."""
    gm = make_arena(20, 20)
    cargo_room = make_cargo_room(cx=10, cy=10)
    ship = Ship()
    item = make_heal_item()
    ship.cargo.append(item)

    ship.materialize_cargo(gm, [cargo_room])

    assert item in gm.entities
    # item must be within the walkable area of the map
    assert gm.is_walkable(item.x, item.y)


def test_materialize_cargo_clears_cargo():
    """After materialize_cargo, ship.cargo must be empty."""
    gm = make_arena(20, 20)
    cargo_room = make_cargo_room(cx=10, cy=10)
    ship = Ship()
    ship.cargo.append(make_heal_item())
    ship.cargo.append(make_weapon())

    ship.materialize_cargo(gm, [cargo_room])

    assert ship.cargo == []


def test_materialize_cargo_overflow():
    """Items beyond the 3x3 neighbourhood still land on some walkable tile via global scan."""
    # Use a small arena and place the cargo room in a corner so the 3x3 neighbourhood
    # has at most ~4 walkable tiles (border walls cut it down).  We put 10 items so
    # the full-map fallback path is definitely exercised.
    gm = make_arena(10, 10)
    # Room centred at (1,1) — only tiles (1,1),(2,1),(1,2),(2,2) are walkable in 3x3
    cargo_room = make_cargo_room(cx=1, cy=1)
    ship = Ship()
    for i in range(10):
        ship.cargo.append(make_heal_item(name=f"Medkit-{i}"))

    ship.materialize_cargo(gm, [cargo_room])

    # All items placed on the map (fallback found space elsewhere)
    item_entities = [e for e in gm.entities if e.item is not None]
    assert len(item_entities) == 10
    for e in item_entities:
        assert gm.is_walkable(e.x, e.y)
    # Cargo fully cleared
    assert ship.cargo == []


def test_materialize_cargo_partial_on_full_map():
    """When the map has fewer walkable tiles than cargo items, placed items land on map
    and unplaced items remain in cargo (not silently lost)."""
    import world.tile_types as tile_types
    from world.game_map import GameMap

    # Build a tiny map: only 3 walkable floor tiles (the rest are walls).
    gm = GameMap(5, 5)
    walkable_tiles = [(1, 1), (2, 1), (3, 1)]
    for x, y in walkable_tiles:
        gm.tiles[x, y] = tile_types.floor

    cargo_room = make_cargo_room(cx=2, cy=1)
    ship = Ship()
    for i in range(5):
        ship.cargo.append(make_heal_item(name=f"Medkit-{i}"))

    ship.materialize_cargo(gm, [cargo_room])

    # Exactly 3 items placed (one per walkable tile)
    placed = [e for e in gm.entities if e.item is not None]
    assert len(placed) == 3
    for e in placed:
        assert gm.is_walkable(e.x, e.y)

    # Remaining 2 items are still in cargo — not lost
    assert len(ship.cargo) == 2


# ---------------------------------------------------------------------------
# 5. materialize_cargo — empty cargo is a no-op
# ---------------------------------------------------------------------------


def test_materialize_cargo_empty_cargo_noop():
    gm = make_arena(10, 10)
    cargo_room = make_cargo_room(cx=5, cy=5)
    ship = Ship()

    ship.materialize_cargo(gm, [cargo_room])

    assert gm.entities == []
    assert ship.cargo == []


# ---------------------------------------------------------------------------
# 6. materialize_cargo — empty rooms list → return early
# ---------------------------------------------------------------------------


def test_materialize_cargo_no_rooms_noop():
    gm = make_arena(10, 10)
    ship = Ship()
    item = make_heal_item()
    ship.cargo.append(item)

    ship.materialize_cargo(gm, [])

    # Item NOT placed on map, cargo unchanged
    assert item not in gm.entities
    assert len(ship.cargo) == 1


# ---------------------------------------------------------------------------
# 7. materialize_cargo — falls back to rooms[0] when no "cargo" label
# ---------------------------------------------------------------------------


def test_materialize_cargo_falls_back_to_first_room():
    gm = make_arena(20, 20)
    generic_room = RectRoom(4, 4, 6, 6, label="bridge")
    ship = Ship()
    item = make_heal_item()
    ship.cargo.append(item)

    ship.materialize_cargo(gm, [generic_room])

    assert item in gm.entities
    assert gm.is_walkable(item.x, item.y)
    assert ship.cargo == []


# ---------------------------------------------------------------------------
# 8-9. collect_floor_items — happy path
# ---------------------------------------------------------------------------


def test_collect_floor_items_gathers_items():
    """Floor items should be appended to ship.cargo."""
    gm = make_arena(10, 10)
    item1 = make_heal_item()
    item1.x, item1.y = 3, 3
    item2 = make_weapon()
    item2.x, item2.y = 4, 4
    gm.entities.extend([item1, item2])

    ship = Ship()
    ship.collect_floor_items(gm)

    assert item1 in ship.cargo
    assert item2 in ship.cargo


def test_collect_floor_items_clears_from_map():
    """Collected items must be removed from game_map.entities."""
    gm = make_arena(10, 10)
    item = make_heal_item()
    item.x, item.y = 3, 3
    gm.entities.append(item)

    ship = Ship()
    ship.collect_floor_items(gm)

    assert item not in gm.entities


# ---------------------------------------------------------------------------
# 10. collect_floor_items — ignores decorations (item=None)
# ---------------------------------------------------------------------------


def test_collect_floor_items_ignores_non_items():
    """Decorations (item=None, non-blocking) must stay on the map."""
    gm = make_arena(10, 10)
    deco = make_decoration(x=3, y=3)
    gm.entities.append(deco)

    ship = Ship()
    ship.collect_floor_items(gm)

    assert deco in gm.entities
    assert ship.cargo == []


# ---------------------------------------------------------------------------
# 11. collect_floor_items — ignores blocking entities
# ---------------------------------------------------------------------------


def test_collect_floor_items_ignores_player():
    """Blocking entities (player, enemies) must not be swept into cargo."""
    gm = make_arena(10, 10)
    blocker = make_blocker(x=5, y=5)
    gm.entities.append(blocker)

    ship = Ship()
    ship.collect_floor_items(gm)

    assert blocker in gm.entities
    assert ship.cargo == []


# ---------------------------------------------------------------------------
# 12. collect_floor_items — empty map
# ---------------------------------------------------------------------------


def test_collect_floor_items_empty_map():
    gm = make_arena(10, 10)
    ship = Ship()

    ship.collect_floor_items(gm)

    assert ship.cargo == []


# ---------------------------------------------------------------------------
# Task 2: generate_player_ship() — 7 tests
# ---------------------------------------------------------------------------


def test_generate_player_ship_no_hull_breaches():
    from world.dungeon_gen import generate_player_ship

    gm, _, _ = generate_player_ship(seed=42)
    assert gm.hull_breaches == []


def test_generate_player_ship_no_enemies():
    from world.dungeon_gen import generate_player_ship

    gm, _, _ = generate_player_ship(seed=42)
    fighters = [e for e in gm.entities if e.fighter is not None]
    assert fighters == []


def test_generate_player_ship_no_items():
    from world.dungeon_gen import generate_player_ship

    gm, _, _ = generate_player_ship(seed=42)
    items = [e for e in gm.entities if e.item is not None]
    assert items == []


def test_generate_player_ship_has_cargo_room():
    from world.dungeon_gen import generate_player_ship

    _, rooms, _ = generate_player_ship(seed=42)
    labels = [r.label for r in rooms]
    assert "cargo" in labels


def test_generate_player_ship_has_exit_pos():
    from world.dungeon_gen import generate_player_ship

    _, _, exit_pos = generate_player_ship(seed=42)
    assert exit_pos is not None
    assert isinstance(exit_pos, tuple)
    assert len(exit_pos) == 2
    assert all(isinstance(v, int) for v in exit_pos)


def test_generate_player_ship_has_reactor_core_tile():
    from world.dungeon_gen import generate_player_ship

    gm, _, _ = generate_player_ship(seed=42)
    rc_tid = int(tile_types.reactor_core["tile_id"])
    assert np.any(gm.tiles["tile_id"] == rc_tid)


def test_generate_player_ship_deterministic():
    from world.dungeon_gen import generate_player_ship

    gm1, rooms1, ep1 = generate_player_ship(seed=99)
    gm2, rooms2, ep2 = generate_player_ship(seed=99)
    assert ep1 == ep2
    assert len(rooms1) == len(rooms2)
    assert gm1.hull_breaches == gm2.hull_breaches


# ---------------------------------------------------------------------------
# Task 3: TacticalState explore_ship mode — 10 tests
# ---------------------------------------------------------------------------


def make_ship_engine():
    """Engine with a ship that has a pre-built game_map for explore_ship tests."""
    from world.dungeon_gen import generate_player_ship

    engine = make_engine()
    ship = Ship()
    gm, rooms, exit_pos = generate_player_ship(seed=42)
    ship.game_map = gm
    ship.rooms = rooms
    ship.exit_pos = exit_pos
    engine.ship = ship
    # Engine needs CONSOLE_WIDTH/HEIGHT for _layout
    engine.CONSOLE_WIDTH = 160
    engine.CONSOLE_HEIGHT = 50
    return engine


def _enter_ship(engine):
    """Call TacticalState(explore_ship=True).on_enter(engine) with tcod mocked."""
    from unittest.mock import patch

    from ui.tactical_state import TacticalState

    state = TacticalState(explore_ship=True)
    with patch.object(engine.ship.game_map, "update_fov"):
        state.on_enter(engine)
    return state


def test_explore_ship_on_enter_sets_game_map():
    """After on_enter, engine.game_map is the ship's game_map."""
    engine = make_ship_engine()
    ship_gm = engine.ship.game_map
    _enter_ship(engine)
    assert engine.game_map is ship_gm


def test_explore_ship_on_enter_places_player_at_exit_pos():
    """Player entity is placed at ship.exit_pos after on_enter."""
    engine = make_ship_engine()
    exit_pos = engine.ship.exit_pos
    _enter_ship(engine)
    assert engine.player is not None
    assert (engine.player.x, engine.player.y) == exit_pos


def test_explore_ship_on_enter_materializes_cargo():
    """Cargo item is on the map floor after on_enter."""
    engine = make_ship_engine()
    item = make_heal_item(name="CargoPack")
    engine.ship.cargo.append(item)
    _enter_ship(engine)
    assert item in engine.game_map.entities


def test_explore_ship_on_enter_no_enemies():
    """No entities with fighter set after on_enter (no enemy spawning)."""
    engine = make_ship_engine()
    _enter_ship(engine)
    fighters = [e for e in engine.game_map.entities if e.fighter is not None and e is not engine.player]
    assert fighters == []


def test_explore_ship_on_enter_empty_environment():
    """engine.environment is {} (pressurized ship interior) after on_enter."""
    engine = make_ship_engine()
    _enter_ship(engine)
    assert engine.environment == {}


def test_explore_ship_on_exit_collects_floor_items():
    """Items on the floor are collected into ship.cargo on on_exit."""
    engine = make_ship_engine()
    state = _enter_ship(engine)
    # Place an item on the map floor
    item = make_heal_item(name="FloorLoot")
    item.x, item.y = 5, 5
    engine.game_map.entities.append(item)
    state.on_exit(engine)
    assert item in engine.ship.cargo


def test_explore_ship_on_exit_skips_fuel_conversion():
    """Reactor core in player inventory does NOT add fuel to ship on on_exit."""
    from game.entity import Entity

    engine = make_ship_engine()
    state = _enter_ship(engine)
    initial_fuel = engine.ship.fuel
    # Give player a reactor_core item
    core = Entity(
        char="\xea",
        color=(180, 80, 255),
        name="Reactor Core",
        blocks_movement=False,
        item={"type": "reactor_core", "value": 5},
    )
    engine.player.inventory.append(core)
    state.on_exit(engine)
    assert engine.ship.fuel == initial_fuel


def test_explore_ship_exit_tile_message():
    """Stepping on exit_pos logs 'You step out of your ship.' when explore_ship=True."""
    from unittest.mock import patch

    from tests.conftest import FakeEvent
    from ui.keys import action_keys

    engine = make_ship_engine()
    state = _enter_ship(engine)

    # Move player to exit_pos so the next action triggers the exit tile check
    exit_pos = engine.ship.exit_pos
    engine.player.x, engine.player.y = exit_pos

    with patch.object(engine.game_map, "update_fov"):
        # Push state onto the real stack so current_state resolves correctly
        engine._state_stack.append(state)

        # action_keys() maps name -> (set_of_syms, label, verb)
        wait_keys_set, _, _ = action_keys()["wait"]
        wait_key = next(iter(wait_keys_set))
        state.ev_key(engine, FakeEvent(wait_key))

    messages = [m[0] for m in engine.message_log.messages]
    assert any("step out of your ship" in m.lower() for m in messages)


def test_take_reactor_core_blocked_in_explore_ship():
    """TakeReactorCoreAction returns 0 and logs block message when explore_ship=True."""
    from game.actions import TakeReactorCoreAction
    from ui.tactical_state import TacticalState

    engine = make_ship_engine()
    _enter_ship(engine)

    # Push an explore_ship state so engine.current_state has explore_ship=True
    state_obj = TacticalState(explore_ship=True)
    engine._state_stack.append(state_obj)

    # Place reactor_core tile adjacent to player
    from world import tile_types as tt

    px, py = engine.player.x, engine.player.y
    tx, ty = px + 1, py
    if engine.game_map.in_bounds(tx, ty):
        engine.game_map.tiles[tx, ty] = tt.reactor_core

    action = TakeReactorCoreAction(dx=1, dy=0)
    result = action.perform(engine, engine.player)

    assert result == 0
    messages = [m[0] for m in engine.message_log.messages]
    assert any("cannot remove" in m.lower() for m in messages)


def test_explore_ship_on_enter_restores_player_stats():
    """Saved player stats (hp, inventory) are applied when engine._saved_player exists."""
    engine = make_ship_engine()
    wpn = make_weapon(name="Blaster")
    engine._saved_player = {
        "hp": 3,
        "max_hp": 12,
        "defense": 2,
        "power": 4,
        "base_power": 4,
        "inventory": [wpn],
        "loadout": None,
    }
    _enter_ship(engine)
    assert engine.player.fighter.hp == 3
    assert engine.player.fighter.max_hp == 12
    assert wpn in engine.player.inventory
