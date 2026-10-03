"""Tests for interdiction resolution + ship-map restoration.

When the last pirate dies, _after_player_turn detects it and calls
``Interdiction.resolve()``. The actual ship-map restoration is deferred
to the player's next ship-exit (handled in TacticalState.on_exit) so the
player isn't stranded on a tile that's about to vanish.
"""

from __future__ import annotations

import random
from types import SimpleNamespace
from unittest.mock import patch

from game.entity import Entity
from game.interdiction import (
    Interdiction,
    restore_original_ship_map,
    start_interdiction,
)
from game.ship import Ship
from tests.conftest import make_engine
from world.dungeon_gen import generate_player_ship


def _ship_with_interior() -> Ship:
    ship = Ship()
    gm, rooms, exit_pos = generate_player_ship(seed=42)
    ship.game_map = gm
    ship.rooms = rooms
    ship.exit_pos = exit_pos
    return ship


def _make_engine_in_ship(interdiction):
    engine = make_engine()
    ship = _ship_with_interior()
    engine.ship = ship
    engine.CONSOLE_WIDTH = 160
    engine.CONSOLE_HEIGHT = 50

    system = SimpleNamespace(name="TestSys", interdiction=interdiction)
    engine.galaxy = SimpleNamespace(
        systems={"TestSys": system},
        current_system="TestSys",
        seed=42,
        home_system="TestSys",
    )
    return engine


def _enter(engine):
    from ui.tactical_state import TacticalState

    state = TacticalState(explore_ship=True)
    with patch("world.game_map.GameMap.update_fov", lambda *a, **k: None):
        state.on_enter(engine)
    return state


# ---- Interdiction.resolve ----


def test_resolve_marks_resolved_true_and_does_not_swap_map():
    """resolve() only marks the flag; map swap happens later in on_exit."""
    ship = _ship_with_interior()
    interdiction = Interdiction()
    start_interdiction(interdiction, ship, rng=random.Random(7))
    if not interdiction.started:
        return
    composite_was = interdiction.composite_map
    interdiction.resolve()
    assert interdiction.resolved is True
    # Map is still the composite - restoration hasn't happened yet.
    assert ship.game_map is composite_was


def test_restore_original_ship_map_swaps_back():
    ship = _ship_with_interior()
    original_map = ship.game_map
    original_exit = ship.exit_pos
    interdiction = Interdiction()
    start_interdiction(interdiction, ship, rng=random.Random(7))
    if not interdiction.started:
        return
    interdiction.resolve()
    restore_original_ship_map(interdiction, ship)
    assert ship.game_map is original_map
    assert ship.exit_pos == original_exit
    assert interdiction.composite_map is None
    assert interdiction.original_ship_map is None


def test_restore_idempotent():
    """Calling restore_original_ship_map twice is safe."""
    ship = _ship_with_interior()
    interdiction = Interdiction()
    start_interdiction(interdiction, ship, rng=random.Random(7))
    if not interdiction.started:
        return
    restore_original_ship_map(interdiction, ship)
    restore_original_ship_map(interdiction, ship)  # should be a no-op
    assert interdiction.original_ship_map is None


def test_restore_no_op_when_no_original_ship_map():
    ship = _ship_with_interior()
    map_before = ship.game_map
    interdiction = Interdiction()  # never started
    restore_original_ship_map(interdiction, ship)
    assert ship.game_map is map_before


# ---- end-of-turn resolution detection in TacticalState ----


def test_resolution_fires_when_all_pirates_dead():
    interdiction = Interdiction()
    engine = _make_engine_in_ship(interdiction)
    state = _enter(engine)
    if not interdiction.started:
        return
    for p in interdiction.pirate_entities:
        p.fighter.hp = 0
    state._after_player_turn(engine)
    assert interdiction.resolved is True


def test_resolution_does_not_fire_with_pirates_alive():
    interdiction = Interdiction()
    engine = _make_engine_in_ship(interdiction)
    state = _enter(engine)
    if not interdiction.started:
        return
    if len(interdiction.pirate_entities) > 1:
        for p in interdiction.pirate_entities[:-1]:
            p.fighter.hp = 0
    state._after_player_turn(engine)
    assert interdiction.resolved is False


def test_resolution_does_nothing_when_no_interdiction():
    """Sanity: ship-explore without interdiction still ticks normally."""
    engine = _make_engine_in_ship(interdiction=None)
    state = _enter(engine)
    state._after_player_turn(engine)


def test_restore_removes_pirate_overlay_entities_from_player_map():
    """Pirate ship's interactables/lights must NOT remain in the original
    player_map.entities list after the interdiction resolves."""
    ship = _ship_with_interior()
    interdiction = Interdiction()
    start_interdiction(interdiction, ship, rng=random.Random(7))
    if not interdiction.started:
        return
    pmap = interdiction.original_ship_map
    # Confirm pirate entities are in the shared list before resolve
    pirate_overlay = list(interdiction.pirate_entities_overlay)
    if pirate_overlay:
        assert all(p in pmap.entities for p in pirate_overlay)
    interdiction.resolve()
    restore_original_ship_map(interdiction, ship)
    # After restore, pirate overlay entities must be gone
    for p in pirate_overlay:
        assert p not in pmap.entities, f"pirate overlay entity {p.name} not removed"


def test_restore_untranslates_player_entities_back_to_native_coords():
    """Player ship's entities should have their original native positions after restore."""
    ship = _ship_with_interior()
    interdiction = Interdiction()
    # Snapshot native player entity positions BEFORE start
    pre_positions = [(e, e.x, e.y) for e in ship.game_map.entities]
    start_interdiction(interdiction, ship, rng=random.Random(7))
    if not interdiction.started:
        return
    interdiction.resolve()
    restore_original_ship_map(interdiction, ship)
    # Each surviving entity must be at its original native position.
    for e, orig_x, orig_y in pre_positions:
        if e in ship.game_map.entities:
            assert (e.x, e.y) == (orig_x, orig_y), f"entity {e.name} not untranslated"


def test_tile_in_player_ship_region_returns_false_for_pirate_tiles():
    from types import SimpleNamespace

    from game.interdiction import tile_in_player_ship_region

    ship = _ship_with_interior()
    interdiction = Interdiction()
    start_interdiction(interdiction, ship, rng=random.Random(7))
    if not interdiction.started:
        return
    galaxy = SimpleNamespace(
        systems={"Test": SimpleNamespace(interdiction=interdiction)},
        current_system="Test",
    )
    engine = SimpleNamespace(galaxy=galaxy)
    # A tile inside the original player ship region (use exit_pos which is
    # native on original_ship_map; in composite it's offset by player_offset)
    pox, poy = interdiction.player_offset
    pem = interdiction.original_exit_pos
    assert tile_in_player_ship_region(pem[0] + pox, pem[1] + poy, engine) is True
    # A tile in the pirate ship region (spawn room is in pirate region)
    cr = interdiction.craft_room
    cx = (cr.x1 + cr.x2) // 2
    cy = (cr.y1 + cr.y2) // 2
    assert tile_in_player_ship_region(cx, cy, engine) is False


def test_floor_items_survive_restoration():
    """Loot dropped during the encounter doesn't vanish when the original ship
    map is restored after exit."""
    ship = _ship_with_interior()
    original_map = ship.game_map
    interdiction = Interdiction()
    start_interdiction(interdiction, ship, rng=random.Random(7))
    if not interdiction.started:
        return
    # Drop a loot item somewhere walkable in the player ship area
    px, py = ship.exit_pos
    loot = Entity(x=px, y=py, char="!", color=(255, 255, 255), name="Loot", item={"type": "junk"})
    # Add loot to original ship map (will survive across the swap)
    original_map.entities.append(loot)
    interdiction.resolve()
    restore_original_ship_map(interdiction, ship)
    assert loot in original_map.entities
