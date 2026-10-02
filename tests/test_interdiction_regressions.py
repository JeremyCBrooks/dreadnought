"""Regression tests for interdiction bugs found in review.

Covers:
  * disconnect-style saves must not mutate the live session,
  * cargo materializes inside the (offset) cargo hold on the composite map,
  * the pirate reactor core stays lootable after the last pirate dies,
  * a failed composition leaves the player ship map untouched,
  * composite tile changes survive a save/load rebuild,
  * the composite map inherits render/vacuum state from the player map.
"""

from __future__ import annotations

import random
from unittest.mock import patch

from game.entity import Entity
from game.interdiction import (
    Interdiction,
    rebuild_composite,
    restore_original_ship_map,
    start_interdiction,
    tile_in_player_ship_region,
)
from game.ship import Ship
from web.save_load import dict_to_engine, engine_to_dict
from world import tile_types
from world.boarding_craft import compose_ships
from world.dungeon_gen import generate_player_ship
from world.galaxy import Galaxy
from world.game_map import GameMap

PLAYER_SHIP_SEED = 42


def _junk(name: str = "junk", x: int = 0, y: int = 0) -> Entity:
    return Entity(x=x, y=y, char="!", color=(255, 255, 255), name=name, item={"type": "junk"})


def _ship_with_interior(seed: int = PLAYER_SHIP_SEED) -> Ship:
    ship = Ship()
    ship.game_map, ship.rooms, ship.exit_pos = generate_player_ship(seed=seed)
    return ship


def _started_interdiction(*, require_offset: bool = False) -> tuple[Ship, Interdiction]:
    """Start an interdiction on a fresh ship, optionally one whose player ship is shifted."""
    for seed in range(200):
        ship = _ship_with_interior()
        interdiction = Interdiction()
        start_interdiction(interdiction, ship, rng=random.Random(seed))
        if not interdiction.started:
            continue
        if require_offset and interdiction.player_offset == (0, 0):
            continue
        return ship, interdiction
    raise RuntimeError("could not start a suitable interdiction with any seed")


def _engine_boarded_in_ship():
    """Full Engine with the player inside their ship during an active interdiction."""
    from engine.game_state import Engine
    from ui.tactical_state import TacticalState

    engine = Engine()
    engine.galaxy = Galaxy(seed=PLAYER_SHIP_SEED)
    engine.galaxy.current_system = engine.galaxy.home_system
    ship, interdiction = _started_interdiction()
    engine.ship = ship
    engine.galaxy.systems[engine.galaxy.home_system].interdiction = interdiction
    engine._saved_player = None
    engine.environment = None
    with patch("world.game_map.GameMap.update_fov", lambda *a, **k: None):
        engine.push_state(TacticalState(explore_ship=True))
    return engine, interdiction


def _engine_for_region_check(interdiction: Interdiction):
    from types import SimpleNamespace

    galaxy = SimpleNamespace(systems={"Test": SimpleNamespace(interdiction=interdiction)}, current_system="Test")
    return SimpleNamespace(galaxy=galaxy)


def _room_center(room) -> tuple[int, int]:
    return room.center


def _reload(data: dict):
    from engine.game_state import Engine

    new_engine = Engine()
    dict_to_engine(data, new_engine)
    return new_engine


# ---- Building blocks ----


def test_tile_by_id_returns_canonical_tile():
    floor_id = int(tile_types.floor["tile_id"])
    assert tile_types.tile_by_id(floor_id) == tile_types.floor


def test_tile_by_id_ignores_recoloured_variants():
    """Variants sharing a base tile_id must not replace the canonical tile."""
    wall_id = int(tile_types.wall["tile_id"])
    tile_types.new_tile(
        walkable=False,
        transparent=False,
        dark=(ord("%"), (1, 2, 3), (4, 5, 6)),
        light=(ord("%"), (7, 8, 9), (10, 11, 12)),
        base_tile_id=wall_id,
    )
    assert tile_types.tile_by_id(wall_id) == tile_types.wall


def test_rect_room_translated_shifts_bounds_and_keeps_label():
    from world.dungeon_gen import RectRoom

    room = RectRoom(2, 3, 4, 5, label="cargo")
    moved = room.translated(10, 20)
    assert (moved.x1, moved.y1, moved.x2, moved.y2, moved.label) == (12, 23, 16, 28, "cargo")
    assert (room.x1, room.y1) == (2, 3), "original room must not be mutated"


# ---- Bug 1: disconnect-style save must not mutate the live session ----


def test_mid_ship_save_keeps_pirates_on_live_map():
    """A reconnect reuses the in-memory engine, so pirates must still be there to fight."""
    engine, interdiction = _engine_boarded_in_ship()
    alive = [p for p in interdiction.pirate_entities if p.fighter.hp > 0]
    assert alive and all(p in engine.game_map.entities for p in alive)

    engine_to_dict(engine)

    assert all(p in engine.game_map.entities for p in alive)
    assert interdiction.pirate_entities == alive


def test_mid_ship_save_keeps_floor_items_on_live_map():
    engine, _ = _engine_boarded_in_ship()
    loot = _junk("floor-loot", engine.player.x, engine.player.y)
    engine.game_map.entities.append(loot)
    cargo_before = list(engine.ship.cargo)

    engine_to_dict(engine)

    assert loot in engine.game_map.entities
    assert engine.ship.cargo == cargo_before


def test_mid_ship_save_still_persists_floor_items_as_cargo():
    """The save itself must still carry floor items, as a clean ship exit would."""
    engine, _ = _engine_boarded_in_ship()
    engine.game_map.entities.append(_junk("floor-loot", engine.player.x, engine.player.y))

    reloaded = _reload(engine_to_dict(engine))

    assert "floor-loot" in [e.name for e in reloaded.ship.cargo]


def test_mid_ship_save_does_not_persist_dead_pirates():
    engine, interdiction = _engine_boarded_in_ship()
    interdiction.pirate_entities[0].fighter.hp = 0
    alive_count = interdiction.alive_pirate_count()

    reloaded = _reload(engine_to_dict(engine))

    loaded = reloaded.galaxy.systems[reloaded.galaxy.home_system].interdiction
    assert len(loaded.pirate_entities) == alive_count


def test_mid_ship_save_is_repeatable():
    """Saving twice in a row (disconnect, reconnect, disconnect) yields the same save."""
    engine, _ = _engine_boarded_in_ship()
    engine.game_map.entities.append(_junk("floor-loot", engine.player.x, engine.player.y))

    assert engine_to_dict(engine) == engine_to_dict(engine)


# ---- Bug 2: cargo lands in the cargo hold on the offset composite ----


def test_cargo_materializes_at_cargo_hold_on_shifted_composite():
    native_rooms = _ship_with_interior().rooms
    native_hold = next((r for r in native_rooms if r.label == "cargo"), native_rooms[0])
    ship, interdiction = _started_interdiction(require_offset=True)
    pox, poy = interdiction.player_offset
    item = _junk()
    ship.cargo.append(item)

    ship.materialize_cargo(ship.game_map, ship.rooms)

    assert (item.x - pox, item.y - poy) == _room_center(native_hold)


def test_ship_rooms_return_to_native_coords_after_restore():
    native_centers = [_room_center(r) for r in _ship_with_interior().rooms]
    ship, interdiction = _started_interdiction(require_offset=True)

    interdiction.resolve()
    restore_original_ship_map(interdiction, ship)

    assert [_room_center(r) for r in ship.rooms] == native_centers


# ---- Bug 3: pirate reactor core stays lootable after resolution ----


def test_pirate_tile_is_not_player_region_while_resolved_composite_is_active():
    _, interdiction = _started_interdiction()
    engine = _engine_for_region_check(interdiction)
    pirate_tile = _room_center(interdiction.craft_room)

    interdiction.resolve()  # last pirate died; composite still active until ship exit

    assert tile_in_player_ship_region(*pirate_tile, engine) is False


def test_every_tile_is_player_region_once_original_map_is_restored():
    ship, interdiction = _started_interdiction()
    engine = _engine_for_region_check(interdiction)
    pirate_tile = _room_center(interdiction.craft_room)

    interdiction.resolve()
    restore_original_ship_map(interdiction, ship)

    assert tile_in_player_ship_region(*pirate_tile, engine) is True


# ---- Bug 4: a failed composition must not mutate the player map ----


def _unroutable_ship_pair():
    """Hand-built ships whose facing airlocks cannot be joined: the player's
    airlock opens straight onto a hull tile, so no corridor can leave it.
    The pirate airlock sits lower than the player's, forcing a player offset.
    """
    player_map = GameMap(12, 10, fill_tile=tile_types.space)
    player_map.tiles[1:5, 1:5] = tile_types.floor
    player_map.tiles[5, 2] = tile_types.airlock_ext_closed
    player_map.tiles[6, 2] = tile_types.wall  # blocks the corridor's first step
    player_airlock = {"interior_door": (4, 2), "exterior_door": (5, 2), "direction": (1, 0), "switch": None}
    player_map.airlocks = [player_airlock]
    player_map.entities.append(Entity(x=2, y=2, char="L", color=(255, 255, 255), name="Locker"))
    player_map.add_light_source(3, 3, radius=4, color=(200, 190, 170))

    pirate_map = GameMap(10, 12, fill_tile=tile_types.space)
    pirate_map.tiles[3:7, 5:10] = tile_types.floor
    pirate_map.tiles[2, 7] = tile_types.airlock_ext_closed
    pirate_airlock = {"interior_door": (3, 7), "exterior_door": (2, 7), "direction": (-1, 0), "switch": None}
    pirate_map.airlocks = [pirate_airlock]
    pirate_map.entities.append(Entity(x=4, y=6, char="L", color=(255, 255, 255), name="Pirate Locker"))
    pirate_map.add_light_source(5, 8, radius=4, color=(200, 190, 170))
    return player_map, player_airlock, pirate_map, pirate_airlock


def test_failed_compose_leaves_player_entities_untouched():
    player_map, player_airlock, pirate_map, pirate_airlock = _unroutable_ship_pair()
    locker = player_map.entities[0]

    layout = compose_ships(player_map, pirate_map, [], player_airlock, pirate_airlock)

    assert layout is None
    assert player_map.entities == [locker]
    assert (locker.x, locker.y) == (2, 2)


def test_failed_compose_leaves_player_lights_untouched():
    player_map, player_airlock, pirate_map, pirate_airlock = _unroutable_ship_pair()
    light = player_map.light_sources[0]

    layout = compose_ships(player_map, pirate_map, [], player_airlock, pirate_airlock)

    assert layout is None
    assert player_map.light_sources == [light]
    assert (light.x, light.y) == (3, 3)


# ---- Bug 5: composite tile changes survive a save/load rebuild ----


def _simulate_load(ship: Ship, interdiction: Interdiction) -> Interdiction:
    """Round-trip the interdiction through its save dict and regenerate the ship, as a DB load does."""
    from web.save_load import _interdiction_from_dict, _interdiction_to_dict

    loaded = _interdiction_from_dict(_interdiction_to_dict(interdiction))
    ship.game_map, ship.rooms, ship.exit_pos = generate_player_ship(seed=PLAYER_SHIP_SEED)
    return loaded


def _pirate_reactor_tile(interdiction: Interdiction) -> tuple[int, int]:
    engine = _engine_for_region_check(interdiction)
    core_tid = int(tile_types.reactor_core["tile_id"])
    cm = interdiction.composite_map
    xs, ys = (cm.tiles["tile_id"] == core_tid).nonzero()
    for x, y in zip(xs.tolist(), ys.tolist(), strict=True):
        if not tile_in_player_ship_region(x, y, engine):
            return x, y
    raise RuntimeError("pirate ship has no reactor core")


def test_extracted_pirate_reactor_core_stays_extracted_after_reload():
    ship, interdiction = _started_interdiction()
    core = _pirate_reactor_tile(interdiction)
    interdiction.composite_map.tiles[core] = tile_types.floor  # what TakeReactorCoreAction does

    loaded = _simulate_load(ship, interdiction)
    assert rebuild_composite(loaded, ship) is True

    assert int(loaded.composite_map.tiles["tile_id"][core]) == int(tile_types.floor["tile_id"])


def test_extracted_pirate_reactor_core_light_stays_removed_after_reload():
    ship, interdiction = _started_interdiction()
    core = _pirate_reactor_tile(interdiction)
    cm = interdiction.composite_map
    assert any((ls.x, ls.y) == core for ls in cm.light_sources), "reactor core should glow before extraction"
    cm.tiles[core] = tile_types.floor
    cm.light_sources = [ls for ls in cm.light_sources if (ls.x, ls.y) != core]

    loaded = _simulate_load(ship, interdiction)
    assert rebuild_composite(loaded, ship) is True

    assert not any((ls.x, ls.y) == core for ls in loaded.composite_map.light_sources)


def test_tile_changes_survive_two_consecutive_reloads():
    """A second save before the player re-enters the ship must not drop the changes."""
    ship, interdiction = _started_interdiction()
    core = _pirate_reactor_tile(interdiction)
    interdiction.composite_map.tiles[core] = tile_types.floor

    loaded_once = _simulate_load(ship, interdiction)
    loaded_twice = _simulate_load(ship, loaded_once)
    assert rebuild_composite(loaded_twice, ship) is True

    assert int(loaded_twice.composite_map.tiles["tile_id"][core]) == int(tile_types.floor["tile_id"])


def test_untouched_composite_rebuilds_identically_after_reload():
    """No tile changes recorded → the rebuilt composite matches the original tile-for-tile."""
    ship, interdiction = _started_interdiction()
    original_ids = interdiction.composite_map.tiles["tile_id"].copy()

    loaded = _simulate_load(ship, interdiction)
    assert rebuild_composite(loaded, ship) is True

    assert (loaded.composite_map.tiles["tile_id"] == original_ids).all()


# ---- Pirates lost to space count as dead ----


def _vent_into_space(engine, pirate) -> None:
    """Put *pirate* on the map edge, drifting outward, as explosive decompression would."""
    pirate.x, pirate.y = engine.game_map.width - 1, 0
    pirate.drifting = True
    pirate.drift_direction = (1, 0)


def test_interdiction_resolves_when_every_pirate_is_vented_into_space():
    """Otherwise travel stays blocked forever with 'intruders remain' and nobody to fight."""
    engine, interdiction = _engine_boarded_in_ship()
    state = engine._state_stack[-1]
    for pirate in interdiction.pirate_entities:
        _vent_into_space(engine, pirate)

    state._after_player_turn(engine)

    assert interdiction.alive_pirate_count() == 0
    assert interdiction.resolved is True


def test_vented_pirate_is_not_reattached_on_next_ship_entry():
    engine, interdiction = _engine_boarded_in_ship()
    state = engine._state_stack[-1]
    vented = list(interdiction.pirate_entities)
    for pirate in vented:
        _vent_into_space(engine, pirate)
    state._after_player_turn(engine)

    engine.pop_state()
    with patch("world.game_map.GameMap.update_fov", lambda *a, **k: None):
        from ui.tactical_state import TacticalState

        engine.push_state(TacticalState(explore_ship=True))

    assert all(p not in engine.game_map.entities for p in vented)


# ---- Searched pirate-ship furnishings stay searched after a reload ----


def _search_furnishing(interdiction: Interdiction, index: int) -> None:
    """Remove a pirate-ship furnishing from the map, as InteractAction does after a search."""
    interdiction.composite_map.entities.remove(interdiction.pirate_entities_overlay[index])


def _furnishings_on_map(interdiction: Interdiction) -> list[bool]:
    on_map = {id(e) for e in interdiction.composite_map.entities}
    return [id(e) in on_map for e in interdiction.pirate_entities_overlay]


def test_searched_pirate_furnishing_stays_gone_after_reload():
    ship, interdiction = _started_interdiction()
    assert len(interdiction.pirate_entities_overlay) >= 2, "pirate ship should have furnishings"
    _search_furnishing(interdiction, 0)
    expected = _furnishings_on_map(interdiction)

    loaded = _simulate_load(ship, interdiction)
    assert rebuild_composite(loaded, ship) is True

    assert _furnishings_on_map(loaded) == expected
    assert expected[0] is False and all(expected[1:])


def test_searched_furnishings_survive_two_consecutive_reloads():
    ship, interdiction = _started_interdiction()
    _search_furnishing(interdiction, 0)
    expected = _furnishings_on_map(interdiction)

    loaded_twice = _simulate_load(ship, _simulate_load(ship, interdiction))
    assert rebuild_composite(loaded_twice, ship) is True

    assert _furnishings_on_map(loaded_twice) == expected


def test_furnishings_searched_across_separate_sessions_all_stay_gone():
    ship, interdiction = _started_interdiction()
    _search_furnishing(interdiction, 0)
    loaded = _simulate_load(ship, interdiction)
    assert rebuild_composite(loaded, ship) is True
    _search_furnishing(loaded, 1)

    reloaded = _simulate_load(ship, loaded)
    assert rebuild_composite(reloaded, ship) is True

    on_map = _furnishings_on_map(reloaded)
    assert on_map[:2] == [False, False] and all(on_map[2:])


def test_unsearched_pirate_furnishings_all_return_after_reload():
    ship, interdiction = _started_interdiction()

    loaded = _simulate_load(ship, interdiction)
    assert rebuild_composite(loaded, ship) is True

    assert all(_furnishings_on_map(loaded))


# ---- Bug 6: composite inherits render/vacuum state from the player map ----


def _compose_with_player_map_state(**attrs):
    """Compose after setting *attrs* on the pristine player map; returns (player_map, interdiction)."""
    for seed in range(200):
        ship = _ship_with_interior()
        player_map = ship.game_map
        for name, value in attrs.items():
            setattr(player_map, name, value)
        interdiction = Interdiction()
        start_interdiction(interdiction, ship, rng=random.Random(seed))
        if interdiction.started:
            return player_map, interdiction
    raise RuntimeError("could not start an interdiction with any seed")


def test_composite_is_flagged_as_having_space():
    """Without has_space the starfield stops animating and space isn't vacuum."""
    _, interdiction = _compose_with_player_map_state()
    assert interdiction.composite_map.has_space is True


def test_composite_space_tiles_are_vacuum():
    _, interdiction = _compose_with_player_map_state()
    cm = interdiction.composite_map
    cm.recalculate_hazards()
    space_mask = cm.tiles["tile_id"] == int(tile_types.space["tile_id"])
    assert space_mask.any()
    assert cm.hazard_overlays["vacuum"][space_mask].all()


def test_composite_keeps_player_space_seed():
    _, interdiction = _compose_with_player_map_state(space_seed=987654)
    assert interdiction.composite_map.space_seed == 987654


def test_composite_keeps_debug_visible_all():
    _, interdiction = _compose_with_player_map_state(debug_visible_all=True)
    assert interdiction.composite_map.debug_visible_all is True


def test_composite_does_not_enable_debug_visible_all_by_itself():
    _, interdiction = _compose_with_player_map_state(debug_visible_all=False)
    assert interdiction.composite_map.debug_visible_all is False


def test_composite_keeps_player_explored_tiles():
    ship = _ship_with_interior()
    player_map = ship.game_map
    player_map.explored[:] = True
    for seed in range(200):
        interdiction = Interdiction()
        start_interdiction(interdiction, ship, rng=random.Random(seed))
        if interdiction.started:
            break
    else:
        raise RuntimeError("could not start an interdiction with any seed")
    pox, poy = interdiction.player_offset
    explored = interdiction.composite_map.explored
    assert explored[pox : pox + player_map.width, poy : poy + player_map.height].all()


def test_composite_does_not_reveal_unexplored_pirate_ship():
    _, interdiction = _compose_with_player_map_state()
    assert not interdiction.composite_map.explored.any()
