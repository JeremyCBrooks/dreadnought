"""Tests for interdiction lifecycle: start_interdiction + _enter_ship hook.

start_interdiction generates a full pirate ship, composes it with the
player ship, and replaces engine.ship.game_map with the composite.
1-4 pirate variants spawn inside the pirate ship.

_enter_ship integration: queued interdictions get started on first entry;
re-entries don't re-spawn; pirates are stripped on exit and re-attached
on re-entry; resolved interdictions cause the original ship map to be restored.
"""

from __future__ import annotations

import random
from unittest.mock import patch

from game.interdiction import Interdiction, restore_original_ship_map, start_interdiction
from game.ship import Ship
from tests.conftest import make_engine
from world.dungeon_gen import generate_player_ship


def _ship_with_interior(seed: int = 42) -> Ship:
    ship = Ship()
    gm, rooms, exit_pos = generate_player_ship(seed=seed)
    ship.game_map = gm
    ship.rooms = rooms
    ship.exit_pos = exit_pos
    return ship


def _start_with_compatible_seed() -> tuple[Ship, Interdiction, int]:
    """Try seeds until start_interdiction actually starts (compatible airlocks)."""
    for seed in range(50):
        ship = _ship_with_interior()
        interdiction = Interdiction()
        start_interdiction(interdiction, ship, rng=random.Random(seed))
        if interdiction.started:
            return ship, interdiction, seed
    raise RuntimeError("could not find a compatible-airlock seed")


# ---- start_interdiction (full composite generation) ----


def test_start_interdiction_marks_started():
    ship, interdiction, _ = _start_with_compatible_seed()
    assert interdiction.started is True


def test_start_interdiction_records_layout_fields():
    ship, interdiction, _ = _start_with_compatible_seed()
    assert interdiction.craft_room is not None
    assert interdiction.connector_tiles, "connector should have at least 1 tile"
    assert interdiction.attach_pos is not None
    assert interdiction.attach_direction is not None
    assert interdiction.player_offset is not None
    assert interdiction.pirate_offset is not None
    assert interdiction.player_airlock_interior is not None
    assert interdiction.pirate_airlock_interior is not None
    assert interdiction.pirate_ship_seed is not None


def test_start_interdiction_swaps_engine_ship_game_map():
    ship_before = _ship_with_interior()
    original_map = ship_before.game_map
    for seed in range(50):
        ship = _ship_with_interior()
        original_map = ship.game_map
        interdiction = Interdiction()
        start_interdiction(interdiction, ship, rng=random.Random(seed))
        if interdiction.started:
            assert ship.game_map is not original_map, "engine.ship.game_map must be swapped to composite"
            assert ship.game_map is interdiction.composite_map
            assert interdiction.original_ship_map is original_map
            return
    raise RuntimeError("no compatible airlock seed found")


def test_start_interdiction_translates_exit_pos_into_composite_coords():
    """exit_pos must remain valid in the new composite map."""
    for seed in range(50):
        ship = _ship_with_interior()
        original_exit = ship.exit_pos
        interdiction = Interdiction()
        start_interdiction(interdiction, ship, rng=random.Random(seed))
        if interdiction.started:
            translated = (
                original_exit[0] + interdiction.player_offset[0],
                original_exit[1] + interdiction.player_offset[1],
            )
            assert ship.exit_pos == translated
            return
    raise RuntimeError("no compatible airlock seed found")


def test_start_interdiction_spawns_between_one_and_four_pirates():
    """Across 30 different seeds (where compatible), every spawn falls in [1, 4]."""
    found = 0
    for seed in range(50):
        ship = _ship_with_interior()
        interdiction = Interdiction()
        start_interdiction(interdiction, ship, rng=random.Random(seed))
        if not interdiction.started:
            continue
        n = len(interdiction.pirate_entities)
        assert 1 <= n <= 4, f"seed {seed}: count {n} out of range"
        found += 1
        if found >= 5:
            break
    assert found > 0, "no successful starts to count pirates from"


def test_start_interdiction_spawns_only_pirate_variants():
    ship, interdiction, _ = _start_with_compatible_seed()
    for p in interdiction.pirate_entities:
        assert p.ai_config.get("can_steal") is True, f"non-pirate variant spawned: {p.name}"


def test_start_interdiction_pirates_inside_spawn_room():
    ship, interdiction, _ = _start_with_compatible_seed()
    room = interdiction.craft_room
    for p in interdiction.pirate_entities:
        assert room.x1 <= p.x <= room.x2, f"pirate x={p.x} not inside {room.x1, room.x2}"
        assert room.y1 <= p.y <= room.y2, f"pirate y={p.y} not inside {room.y1, room.y2}"


def test_start_interdiction_aborts_when_no_compatible_airlocks():
    """If no facing-airlock pair exists, mark resolved and bail without changing the ship map."""
    ship = Ship()
    from world import tile_types
    from world.game_map import GameMap

    gm = GameMap(20, 20, fill_tile=tile_types.space)
    ship.game_map = gm
    ship.rooms = []
    ship.exit_pos = None  # no airlocks at all on player ship
    interdiction = Interdiction()
    start_interdiction(interdiction, ship, rng=random.Random(0))
    assert interdiction.started is False
    assert interdiction.resolved is True
    assert ship.game_map is gm, "ship.game_map must not be swapped on abort"


# ---- _enter_ship integration ----


def _make_ship_engine_with_galaxy(interdiction: Interdiction | None = None):
    from types import SimpleNamespace

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


def _enter_ship(engine):
    from ui.tactical_state import TacticalState

    state = TacticalState(explore_ship=True)
    # Bypass real FOV (it would require working tcod console state).
    with patch("world.game_map.GameMap.update_fov", lambda *a, **k: None):
        state.on_enter(engine)
    return state


def test_enter_ship_starts_queued_interdiction():
    interdiction = Interdiction()
    engine = _make_ship_engine_with_galaxy(interdiction)
    _enter_ship(engine)
    # Either started successfully or was resolved silently (no compatible airlock).
    assert interdiction.started or interdiction.resolved


def test_enter_ship_attaches_pirates_to_composite_map():
    interdiction = Interdiction()
    engine = _make_ship_engine_with_galaxy(interdiction)
    _enter_ship(engine)
    if not interdiction.started:
        return  # silent abort path covered elsewhere
    for p in interdiction.pirate_entities:
        assert p in engine.game_map.entities, "pirate not in composite game_map"


def test_enter_ship_swaps_to_composite_map():
    interdiction = Interdiction()
    engine = _make_ship_engine_with_galaxy(interdiction)
    original_map = engine.ship.game_map
    _enter_ship(engine)
    if interdiction.started:
        assert engine.ship.game_map is interdiction.composite_map
        assert engine.ship.game_map is not original_map


def test_enter_ship_no_interdiction_works_normally():
    engine = _make_ship_engine_with_galaxy(interdiction=None)
    _enter_ship(engine)
    assert engine.player is not None


def test_resolved_interdiction_restores_ship_map_on_entry():
    """If a resolved interdiction has a stale composite from a prior session,
    re-entering the ship swaps the original map back."""
    interdiction = Interdiction()
    engine = _make_ship_engine_with_galaxy(interdiction)
    original_map = engine.ship.game_map
    _enter_ship(engine)
    if not interdiction.started:
        return
    # Resolve mid-encounter
    for p in interdiction.pirate_entities:
        p.fighter.hp = 0
    interdiction.resolve()
    # Simulate exit: detach pirates and call restore (mimics on_exit's tail).
    restore_original_ship_map(interdiction, engine.ship)
    assert engine.ship.game_map is original_map


def test_enter_ship_message_includes_directional_hint():
    """Player should learn which direction to head to find the boarders."""
    interdiction = Interdiction()
    engine = _make_ship_engine_with_galaxy(interdiction)
    _enter_ship(engine)
    msgs = " ".join(m[0] for m in engine.message_log._messages).lower()
    if interdiction.started:
        assert any(d in msgs for d in (" north", " south", " east", " west")), (
            f"alert should include a cardinal direction; got: {msgs}"
        )


def test_enter_ship_marks_corridor_explored():
    interdiction = Interdiction()
    engine = _make_ship_engine_with_galaxy(interdiction)
    _enter_ship(engine)
    if not interdiction.started:
        return
    for tx, ty in interdiction.connector_tiles:
        assert engine.game_map.explored[tx, ty], f"connector tile {(tx, ty)} should be explored"


def test_reentering_ship_does_not_respawn_pirates():
    interdiction = Interdiction()
    engine = _make_ship_engine_with_galaxy(interdiction)
    _enter_ship(engine)
    if not interdiction.started:
        return
    pirates_first = list(interdiction.pirate_entities)
    # Strip + re-enter
    for p in pirates_first:
        if p in engine.game_map.entities:
            engine.game_map.entities.remove(p)
    _enter_ship(engine)
    pirates_second = list(interdiction.pirate_entities)
    assert pirates_first == pirates_second, "must not re-spawn"


def test_detach_strips_alive_pirates_even_when_resolved():
    """Future-proofing: if interdiction is marked resolved while live pirates
    remain on the map, detach should still remove them so they don't re-attach."""
    interdiction = Interdiction()
    engine = _make_ship_engine_with_galaxy(interdiction)
    state = _enter_ship(engine)
    if not interdiction.started:
        return
    interdiction.resolved = True
    live = [p for p in interdiction.pirate_entities if p.fighter and p.fighter.hp > 0]
    state._detach_interdiction_pirates(engine)
    for p in live:
        assert p not in engine.game_map.entities


# ---- rebuild_composite (post-load) ----


def test_rebuild_composite_recreates_map_from_seed():
    """After save/load wipes composite_map, rebuild_composite restores it."""
    from game.interdiction import rebuild_composite

    ship = _ship_with_interior()
    interdiction = Interdiction()
    start_interdiction(interdiction, ship, rng=random.Random(7))
    if not interdiction.started:
        return  # incompatible airlocks; skip
    saved_seed = interdiction.pirate_ship_seed
    saved_player_int = interdiction.player_airlock_interior
    saved_pirate_int = interdiction.pirate_airlock_interior
    saved_player_offset = interdiction.player_offset
    saved_pirate_offset = interdiction.pirate_offset

    # Wipe transient composite and restore the original ship_map (simulates load).
    ship.game_map = interdiction.original_ship_map
    ship.exit_pos = interdiction.original_exit_pos
    interdiction.original_ship_map = None
    interdiction.original_exit_pos = None
    interdiction.composite_map = None

    # Rebuild
    ok = rebuild_composite(interdiction, ship)
    assert ok is True
    assert interdiction.composite_map is not None
    # Same seed → same airlock positions and offsets
    assert interdiction.pirate_ship_seed == saved_seed
    assert interdiction.player_airlock_interior == saved_player_int
    assert interdiction.pirate_airlock_interior == saved_pirate_int
    assert interdiction.player_offset == saved_player_offset
    assert interdiction.pirate_offset == saved_pirate_offset
