"""A boarding craft whose crew the player kills stays in the system as a wreck.

The wreck is the ship that was fought on, as the player left it: same layout,
looted core still gone, searched lockers still empty. It is nobody's home any
more, so nothing ever spawns aboard.
"""

from __future__ import annotations

import numpy as np

from data.names import LOCATION_TYPES, WRECK_LOC_TYPE
from game.entity import Entity
from game.interdiction import current_interdiction, tile_in_player_ship_region
from game.wreck import WreckRecord, build_wreck_map
from tests.conftest import FakeEvent, enter_ship, key_for, new_game
from ui.strategic_state import _direction
from ui.tactical_state import TacticalState
from web.save_load import _galaxy_from_dict, _galaxy_to_dict
from world import tile_types
from world.boarding_ship import generate_pirate_ship
from world.galaxy import Galaxy

# Seed 1's ship has an airlock pirates can reach; seed 37's never does.
BOARDABLE_SEED = 1
UNBOARDABLE_SEED = 37

_CORE_ID = int(tile_types.reactor_core["tile_id"])


def _boarded_game(seed: int = BOARDABLE_SEED):
    """A game that has just jumped, cargo aboard, into its first neighbouring system."""
    engine, strategic = new_game(seed)
    engine.ship.max_fuel = engine.ship.fuel = 50
    engine.ship.add_cargo(Entity(name="Scrap", item={"type": "scrap", "value": 1}))
    _jump(engine, strategic)
    return engine, strategic


def _jump(engine, strategic) -> None:
    galaxy = engine.galaxy
    here = galaxy.systems[galaxy.current_system]
    dest = next(iter(here.connections))
    strategic.focus = "navigation"
    strategic.ev_key(engine, FakeEvent(key_for(_direction(here, galaxy.systems[dest]))))


def _kill_pirates(engine) -> None:
    for pirate in current_interdiction(engine).pirate_entities:
        pirate.fighter.hp = 0


def _wrecks(engine, system_name: str | None = None) -> list:
    system = engine.galaxy.systems[system_name or engine.galaxy.current_system]
    return [loc for loc in system.locations if loc.loc_type == WRECK_LOC_TYPE]


def _find_tile(engine, tile_id: int, players_own: bool) -> tuple[int, int]:
    """A composite tile of *tile_id* on the player's own ship, or on the pirate ship."""
    xs, ys = (engine.game_map.tiles["tile_id"] == tile_id).nonzero()
    tiles = zip(xs.tolist(), ys.tolist(), strict=True)
    return next((x, y) for x, y in tiles if tile_in_player_ship_region(x, y, engine) == players_own)


def _pirate_side(engine, tile_id: int) -> tuple[int, int]:
    return _find_tile(engine, tile_id, players_own=False)


def _extract_core(engine, x: int, y: int) -> None:
    """What TakeReactorCoreAction does to the map."""
    game_map = engine.game_map
    game_map.tiles[x, y] = tile_types.floor
    game_map.light_sources[:] = [ls for ls in game_map.light_sources if (ls.x, ls.y) != (x, y)]


def _cleared_wreck(seed: int = BOARDABLE_SEED, aboard=None):
    """Clear the boarding, optionally do *aboard(engine)* while still docked, and return to the bridge."""
    engine, strategic = _boarded_game(seed)
    enter_ship(engine)
    _kill_pirates(engine)
    interdiction = current_interdiction(engine)
    noted = aboard(engine) if aboard else None
    engine.pop_state()
    (wreck,) = _wrecks(engine)
    return engine, strategic, wreck, interdiction, noted


def _visit(engine, wreck) -> TacticalState:
    state = TacticalState(location=wreck, depth=0)
    engine.push_state(state)
    return state


def _furnishings(game_map, player) -> list:
    return [e for e in game_map.entities if e is not player]


class TestWreckIsLeftBehind:
    def test_clearing_and_returning_to_the_bridge_leaves_one_wreck(self):
        engine, _, wreck, _, _ = _cleared_wreck()
        assert _wrecks(engine) == [wreck]

    def test_wreck_is_already_visited(self):
        _, _, wreck, _, _ = _cleared_wreck()
        assert wreck.visited is True

    def test_wreck_belongs_to_the_system_it_was_fought_in(self):
        engine, _, wreck, _, _ = _cleared_wreck()
        assert wreck.system_name == engine.galaxy.current_system

    def test_wreck_is_named_as_a_raider(self):
        _, _, wreck, _, _ = _cleared_wreck()
        assert wreck.name.startswith("Raider ")

    def test_bridge_is_told_the_ship_drifted_free(self):
        engine, _, wreck, _, _ = _cleared_wreck()
        log = " ".join(text for text, *_ in engine.message_log.messages)
        assert f"{wreck.name} drifts free" in log

    def test_no_wreck_while_the_ship_is_still_docked(self):
        engine, _ = _boarded_game()
        enter_ship(engine)
        _kill_pirates(engine)
        assert _wrecks(engine) == []

    def test_returning_to_the_ship_does_not_leave_a_second_wreck(self):
        engine, _, wreck, _, _ = _cleared_wreck()
        enter_ship(engine)
        engine.pop_state()
        assert _wrecks(engine) == [wreck]

    def test_wreck_name_is_unique_in_the_galaxy(self):
        engine, _ = _boarded_game()
        seed = current_interdiction(engine).pirate_ship_seed
        taken = f"Raider {100 + seed % 900}"
        engine.galaxy.claim_name(taken)
        enter_ship(engine)
        _kill_pirates(engine)
        engine.pop_state()
        (wreck,) = _wrecks(engine)
        assert wreck.name != taken
        assert wreck.name.startswith("Raider ")


class TestNoWreck:
    def test_retreating_with_pirates_still_alive(self):
        engine, _ = _boarded_game()
        enter_ship(engine)
        engine.pop_state()
        assert _wrecks(engine) == []

    def test_breaking_away(self):
        engine, strategic = _boarded_game()
        boarded_in = engine.galaxy.current_system
        onward = next(iter(engine.galaxy.systems[boarded_in].connections))
        strategic.break_away(engine, onward)
        assert engine.galaxy.current_system == onward
        assert _wrecks(engine, boarded_in) == []

    def test_drifting_off(self):
        engine, strategic = _boarded_game()
        boarded_in = engine.galaxy.current_system
        strategic._drift(engine)
        assert _wrecks(engine, boarded_in) == []

    def test_a_craft_that_never_docked(self):
        engine, _ = _boarded_game(UNBOARDABLE_SEED)
        enter_ship(engine)
        engine.pop_state()
        assert _wrecks(engine) == []

    def test_random_systems_never_roll_a_wreck(self):
        assert WRECK_LOC_TYPE not in LOCATION_TYPES
        galaxy = Galaxy(seed=3)
        for name in list(galaxy.systems):
            galaxy.arrive_at(name)
        assert not [loc for system in galaxy.systems.values() for loc in system.locations if loc.wreck is not None]


class TestWreckIsTheShipYouFoughtOn:
    def test_layout_matches_the_pirate_ship(self):
        engine, _, wreck, interdiction, _ = _cleared_wreck()
        _visit(engine, wreck)
        pristine, _, _ = generate_pirate_ship(interdiction.pirate_ship_seed)
        assert np.array_equal(engine.game_map.tiles["tile_id"], pristine.tiles["tile_id"])

    def test_player_arrives_at_the_docking_hatch(self):
        engine, _, wreck, interdiction, _ = _cleared_wreck()
        state = _visit(engine, wreck)
        _, _, exit_pos = generate_pirate_ship(interdiction.pirate_ship_seed)
        assert state.exit_pos == exit_pos
        assert (engine.player.x, engine.player.y) == exit_pos

    def test_an_extracted_core_stays_extracted(self):
        def loot_core(engine):
            x, y = _pirate_side(engine, _CORE_ID)
            _extract_core(engine, x, y)
            ox, oy = current_interdiction(engine).pirate_offset
            return x - ox, y - oy

        engine, _, wreck, _, core_at = _cleared_wreck(aboard=loot_core)
        _visit(engine, wreck)
        assert not (engine.game_map.tiles["tile_id"] == _CORE_ID).any()
        assert int(engine.game_map.tiles["tile_id"][core_at]) == int(tile_types.floor["tile_id"])
        assert not [ls for ls in engine.game_map.light_sources if (ls.x, ls.y) == core_at]

    def test_an_untouched_core_is_still_there(self):
        engine, _, wreck, _, _ = _cleared_wreck()
        _visit(engine, wreck)
        assert (engine.game_map.tiles["tile_id"] == _CORE_ID).sum() == 1

    def test_a_searched_furnishing_stays_gone(self):
        def search_one(engine):
            interdiction = current_interdiction(engine)
            searched = interdiction.pirate_entities_overlay[0]
            engine.game_map.entities.remove(searched)
            ox, oy = interdiction.pirate_offset
            return searched.name, (searched.x - ox, searched.y - oy), len(interdiction.pirate_entities_overlay)

        engine, _, wreck, _, (name, at, total) = _cleared_wreck(aboard=search_one)
        _visit(engine, wreck)
        left = _furnishings(engine.game_map, engine.player)
        assert len(left) == total - 1
        assert not [e for e in left if e.name == name and (e.x, e.y) == at]

    def test_changes_to_the_players_own_ship_do_not_leak_onto_the_wreck(self):
        def open_own_door(engine):
            door = _find_tile(engine, int(tile_types.door_closed["tile_id"]), players_own=True)
            engine.game_map.tiles[door] = tile_types.door_open

        engine, _, wreck, interdiction, _ = _cleared_wreck(aboard=open_own_door)
        assert wreck.wreck.tile_changes == []
        _visit(engine, wreck)
        pristine, _, _ = generate_pirate_ship(interdiction.pirate_ship_seed)
        assert np.array_equal(engine.game_map.tiles["tile_id"], pristine.tiles["tile_id"])


class TestWreckIsDead:
    def test_nothing_is_aboard_on_the_first_visit(self):
        engine, _, wreck, _, _ = _cleared_wreck()
        _visit(engine, wreck)
        assert not [e for e in engine.game_map.entities if e.ai]

    def test_nothing_spawns_on_later_visits(self):
        engine, _, wreck, _, _ = _cleared_wreck()
        for _ in range(3):
            _visit(engine, wreck)
            assert not [e for e in engine.game_map.entities if e.ai]
            engine.pop_state()


class TestWreckPersists:
    def test_the_same_map_is_revisited_within_a_session(self):
        engine, _, wreck, _, _ = _cleared_wreck()
        _visit(engine, wreck)
        first = engine.game_map
        engine.pop_state()
        _visit(engine, wreck)
        assert engine.game_map is first

    def test_looting_during_a_later_visit_is_recorded(self):
        engine, _, wreck, _, _ = _cleared_wreck()
        _visit(engine, wreck)
        xs, ys = (engine.game_map.tiles["tile_id"] == _CORE_ID).nonzero()
        core_at = (int(xs[0]), int(ys[0]))
        _extract_core(engine, *core_at)
        engine.pop_state()
        assert (*core_at, int(tile_types.floor["tile_id"])) in wreck.wreck.tile_changes

    def test_wreck_survives_save_and_load(self):
        def loot_core(engine):
            _extract_core(engine, *_pirate_side(engine, _CORE_ID))

        engine, _, wreck, _, _ = _cleared_wreck(aboard=loot_core)
        loaded = _galaxy_from_dict(_galaxy_to_dict(engine.galaxy))
        (reloaded,) = [loc for loc in loaded.systems[loaded.current_system].locations if loc.wreck is not None]
        assert (reloaded.name, reloaded.loc_type, reloaded.visited) == (wreck.name, WRECK_LOC_TYPE, True)
        assert reloaded.wreck == wreck.wreck
        game_map, _, _ = build_wreck_map(reloaded.wreck)
        assert not (game_map.tiles["tile_id"] == _CORE_ID).any()

    def test_ordinary_locations_carry_no_wreck_record_through_a_save(self):
        galaxy = Galaxy(seed=2)
        loaded = _galaxy_from_dict(_galaxy_to_dict(galaxy))
        assert all(loc.wreck is None for system in loaded.systems.values() for loc in system.locations)


class TestWreckRecord:
    def test_building_from_an_empty_record_gives_the_pristine_ship(self):
        game_map, rooms, exit_pos = build_wreck_map(WreckRecord(ship_seed=7))
        pristine, pristine_rooms, pristine_exit = generate_pirate_ship(7)
        assert np.array_equal(game_map.tiles["tile_id"], pristine.tiles["tile_id"])
        assert (len(rooms), exit_pos) == (len(pristine_rooms), pristine_exit)

    def test_changes_outside_the_hull_are_ignored(self):
        pristine, _, _ = generate_pirate_ship(7)
        space_id = int(tile_types.space["tile_id"])
        xs, ys = (pristine.tiles["tile_id"] == space_id).nonzero()
        stray = (int(xs[0]), int(ys[0]), int(tile_types.floor["tile_id"]))
        out_of_bounds = (10_000, 10_000, int(tile_types.floor["tile_id"]))
        game_map, _, _ = build_wreck_map(WreckRecord(ship_seed=7, tile_changes=[stray, out_of_bounds]))
        assert np.array_equal(game_map.tiles["tile_id"], pristine.tiles["tile_id"])

    def test_refresh_records_what_changed_since_the_ship_was_built(self):
        record = WreckRecord(ship_seed=7)
        game_map, _, _ = build_wreck_map(record)
        xs, ys = (game_map.tiles["tile_id"] == _CORE_ID).nonzero()
        core_at = (int(xs[0]), int(ys[0]))
        game_map.tiles[core_at] = tile_types.floor
        searched = game_map.entities[0]
        game_map.entities.remove(searched)
        record.refresh(game_map)
        assert record.tile_changes == [(*core_at, int(tile_types.floor["tile_id"]))]
        assert record.consumed_furnishings == [0]

    def test_a_refreshed_record_rebuilds_the_same_ship(self):
        record = WreckRecord(ship_seed=7)
        game_map, _, _ = build_wreck_map(record)
        xs, ys = (game_map.tiles["tile_id"] == _CORE_ID).nonzero()
        game_map.tiles[int(xs[0]), int(ys[0])] = tile_types.floor
        game_map.entities.remove(game_map.entities[0])
        record.refresh(game_map)
        rebuilt, _, _ = build_wreck_map(WreckRecord(record.ship_seed, record.tile_changes, record.consumed_furnishings))
        assert np.array_equal(rebuilt.tiles["tile_id"], game_map.tiles["tile_id"])
        assert len(rebuilt.entities) == len(game_map.entities)
