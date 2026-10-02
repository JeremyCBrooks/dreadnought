"""Hull damage on the player ship is physical: one hull point lost is one breach."""

from __future__ import annotations

import random

from engine.game_state import Engine
from game.entity import Entity
from game.interdiction import BREAK_AWAY_HULL_DAMAGE, Interdiction, restore_original_ship_map, start_interdiction
from game.ship import Ship
from tests.conftest import FakeEvent, enter_ship, key_for, make_arena, new_game
from web.save_load import dict_to_engine, engine_to_dict
from world import tile_types
from world.game_map import GameMap

SHIP_SEED = 42
CARDINALS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _tid(tile) -> int:
    return int(tile["tile_id"])


def _ship(seed: int = SHIP_SEED) -> Ship:
    ship = Ship()
    ship.generate_interior(seed)
    return ship


def _holed_room() -> GameMap:
    """A walled room with space along its west side: (1, y) is hull, (0, y) is space."""
    game_map = make_arena(12, 10)
    for y in range(10):
        game_map.tiles[0, y] = tile_types.space
        game_map.tiles[1, y] = tile_types.wall
    game_map.has_space = True
    return game_map


def _started_interdiction(ship_factory) -> tuple[Ship, Interdiction]:
    for seed in range(200):
        ship = ship_factory()
        interdiction = Interdiction()
        start_interdiction(interdiction, ship, rng=random.Random(seed))
        if interdiction.started:
            return ship, interdiction
    raise RuntimeError("could not start an interdiction with any seed")


# ---- GameMap: opening and sealing a breach ----


def test_opening_a_breach_holes_the_tile_and_lists_it():
    game_map = _holed_room()

    game_map.open_hull_breach(1, 5)

    assert _tid(game_map.tiles[1, 5]) == _tid(tile_types.hull_breach)
    assert game_map.hull_breaches == [(1, 5)]


def test_an_open_breach_vents_the_room_behind_it():
    game_map = _holed_room()
    game_map.recalculate_hazards()

    game_map.open_hull_breach(1, 5)
    game_map.recalculate_hazards()

    assert game_map.hazard_overlays["vacuum"][5, 5]


def test_a_breach_opened_while_nobody_is_aboard_causes_no_decompression():
    """The air is long gone by the time the player boards: no blast at the hatch."""
    game_map = _holed_room()
    game_map.recalculate_hazards()  # the ship has been visited: pressure baseline is set

    game_map.open_hull_breach(1, 5)
    game_map.recalculate_hazards()

    assert game_map.pending_decompression is None


def test_sealing_a_breach_restores_the_hull_and_the_air():
    game_map = _holed_room()
    game_map.open_hull_breach(1, 5)
    game_map.recalculate_hazards()

    game_map.seal_hull_breach(1, 5, tile_types.wall)
    game_map.recalculate_hazards()

    assert _tid(game_map.tiles[1, 5]) == _tid(tile_types.wall)
    assert game_map.hull_breaches == []
    assert not game_map.hazard_overlays["vacuum"][5, 5]


# ---- Ship: damage opens breaches ----


def test_each_hull_point_lost_opens_one_breach():
    ship = _ship()

    ship.damage_hull(3, rng=random.Random(1))

    assert ship.hull == 7
    assert len(ship.game_map.hull_breaches) == 3
    assert len(set(ship.game_map.hull_breaches)) == 3


def test_breaches_open_in_the_outer_hull():
    ship = _ship()
    before = ship.game_map.tiles.copy()

    ship.damage_hull(5, rng=random.Random(1))

    for x, y in ship.game_map.hull_breaches:
        neighbours = [before[x + dx, y + dy] for dx, dy in CARDINALS]
        assert _tid(before[x, y]) == _tid(tile_types.wall)
        assert any(_tid(n) == _tid(tile_types.space) for n in neighbours)
        assert any(bool(n["walkable"]) for n in neighbours)


def test_breaches_never_open_into_an_airlock_chamber():
    """A holed airlock chamber would vent the docking corridor of the next boarding."""
    airlock_floor = _tid(tile_types.airlock_floor)
    for seed in range(5):
        ship = _ship(seed)
        before = ship.game_map.tiles.copy()

        ship.damage_hull(10, rng=random.Random(seed))

        for x, y in ship.game_map.hull_breaches:
            inside = [before[x + dx, y + dy] for dx, dy in CARDINALS if bool(before[x + dx, y + dy]["walkable"])]
            assert any(_tid(n) != airlock_floor for n in inside)


def test_damage_beyond_the_remaining_hull_opens_only_as_many_breaches_as_hull_lost():
    ship = _ship()
    ship.hull = 1

    ship.damage_hull(4, rng=random.Random(1))

    assert ship.hull == 0
    assert len(ship.game_map.hull_breaches) == 1


def test_damage_near_a_point_opens_the_closest_hull():
    ship = _ship()
    probe = _ship()
    probe.damage_hull(10, rng=random.Random(1))
    target = probe.game_map.hull_breaches[0]

    ship.damage_hull(1, rng=random.Random(2), near=target)

    assert ship.game_map.hull_breaches == [target]


def test_the_same_roll_opens_the_same_breaches():
    first, second = _ship(), _ship()

    first.damage_hull(3, rng=random.Random(9))
    second.damage_hull(3, rng=random.Random(9))

    assert first.game_map.hull_breaches == second.game_map.hull_breaches


def test_a_ship_without_an_interior_still_loses_hull():
    ship = Ship()

    ship.damage_hull(2)

    assert ship.hull == 8


def test_sealing_a_breach_restores_one_hull_point():
    ship = _ship()
    ship.damage_hull(2, rng=random.Random(1))
    x, y = ship.game_map.hull_breaches[0]

    sealed = ship.seal_hull_breach(x, y)

    assert sealed is True
    assert ship.hull == 9
    assert (x, y) not in ship.game_map.hull_breaches
    assert _tid(ship.game_map.tiles[x, y]) == _tid(tile_types.wall)


def test_sealing_where_there_is_no_breach_does_nothing():
    ship = _ship()
    ship.damage_hull(1, rng=random.Random(1))

    sealed = ship.seal_hull_breach(0, 0)

    assert sealed is False
    assert ship.hull == 9
    assert len(ship.game_map.hull_breaches) == 1


# ---- Interdiction: breaches ride the composite map and come home again ----


def _holed_ship() -> Ship:
    ship = _ship()
    ship.damage_hull(2, rng=random.Random(1))
    return ship


def test_breaches_are_carried_onto_the_composite_map():
    native = _holed_ship().hull_breach_positions()
    ship, interdiction = _started_interdiction(_holed_ship)
    pox, poy = interdiction.player_offset

    assert sorted(ship.game_map.hull_breaches) == sorted((x + pox, y + poy) for x, y in native)
    for x, y in ship.game_map.hull_breaches:
        assert _tid(ship.game_map.tiles[x, y]) == _tid(tile_types.hull_breach)


def test_breach_positions_stay_in_ship_coordinates_during_an_interdiction():
    native = _holed_ship().hull_breach_positions()
    ship, _ = _started_interdiction(_holed_ship)

    assert sorted(ship.hull_breach_positions()) == sorted(native)


def test_a_breach_sealed_during_an_interdiction_stays_sealed_afterwards():
    ship, interdiction = _started_interdiction(_holed_ship)
    sealed_at, left_open = ship.hull_breach_positions()
    cx, cy = ship.game_map.hull_breaches[ship.hull_breach_positions().index(sealed_at)]

    ship.seal_hull_breach(cx, cy)
    interdiction.resolve()
    restore_original_ship_map(interdiction, ship)

    assert ship.hull == 9
    assert ship.game_map.hull_breaches == [left_open]
    assert _tid(ship.game_map.tiles[sealed_at]) == _tid(tile_types.wall)
    assert _tid(ship.game_map.tiles[left_open]) == _tid(tile_types.hull_breach)
    assert ship.hull_breach_positions() == [left_open]


# ---- Save / load ----


def _reload(engine: Engine) -> Engine:
    loaded = Engine()
    dict_to_engine(engine_to_dict(engine), loaded)
    return loaded


def test_breaches_survive_a_save_and_load():
    engine, _ = new_game(seed=SHIP_SEED)
    engine.ship.damage_hull(3, rng=random.Random(1))
    breaches = engine.ship.hull_breach_positions()

    loaded = _reload(engine)

    assert loaded.ship.hull == 7
    assert loaded.ship.hull_breach_positions() == breaches
    for x, y in breaches:
        assert _tid(loaded.ship.game_map.tiles[x, y]) == _tid(tile_types.hull_breach)


def test_a_save_from_before_breaches_existed_gets_one_per_missing_hull_point():
    engine, _ = new_game(seed=SHIP_SEED)
    engine.ship.hull = 6
    data = engine_to_dict(engine)
    del data["ship"]["hull_breaches"]

    loaded = Engine()
    dict_to_engine(data, loaded)

    assert loaded.ship.hull == 6
    assert len(loaded.ship.hull_breach_positions()) == 4


def test_an_undamaged_ship_loads_without_breaches():
    engine, _ = new_game(seed=SHIP_SEED)

    loaded = _reload(engine)

    assert loaded.ship.hull_breach_positions() == []


# ---- On the star map: damage is real ----


def _strand(engine: Engine) -> None:
    """Out of fuel with an empty hold: the next navigation drifts and damages the hull."""
    engine.ship.fuel = 0
    engine.ship.cargo = []


def _navigate_anywhere(engine: Engine, strategic) -> None:
    import tcod.event

    strategic.ev_key(engine, FakeEvent(tcod.event.KeySym.TAB))
    direction = next(iter(strategic._connection_by_direction()))
    strategic.ev_key(engine, FakeEvent(key_for(direction)))


def test_drift_damage_opens_a_breach():
    engine, strategic = new_game(seed=SHIP_SEED)
    _strand(engine)

    _navigate_anywhere(engine, strategic)

    assert engine.ship.hull == 9
    assert len(engine.ship.hull_breach_positions()) == 1


def test_the_attach_point_is_reported_in_ship_coordinates():
    ship, interdiction = _started_interdiction(_ship)
    pox, poy = interdiction.player_offset
    ax, ay = interdiction.native_attach_point()

    assert (ax + pox, ay + poy) == interdiction.player_airlock_interior
    assert Interdiction().native_attach_point() is None


def test_breaking_away_holes_the_hull_where_the_pirates_were_clamped():
    engine, strategic = new_game(seed=SHIP_SEED)
    engine.ship, interdiction = _started_interdiction(lambda: _ship(engine.galaxy.seed))
    here = engine.galaxy.systems[engine.galaxy.current_system]
    here.interdiction = interdiction
    engine.ship.fuel = engine.ship.max_fuel
    expected = _ship(engine.galaxy.seed)
    expected.damage_hull(BREAK_AWAY_HULL_DAMAGE, near=interdiction.native_attach_point())

    strategic.break_away(engine, next(iter(here.connections)))

    assert engine.ship.hull == 10 - BREAK_AWAY_HULL_DAMAGE
    assert sorted(engine.ship.hull_breach_positions()) == sorted(expected.hull_breach_positions())


# ---- Boarding a holed ship ----


def _crate() -> Entity:
    return Entity(name="Crate", blocks_movement=False, item={"type": "heal", "value": 1})


def test_boarding_a_holed_ship_does_not_blow_the_cargo_out():
    engine, _ = new_game(seed=SHIP_SEED)
    enter_ship(engine)  # a first visit sets the pressure baseline
    engine.pop_state()
    engine.ship.damage_hull(engine.ship.hull - 1, rng=random.Random(1))
    crates = [_crate() for _ in range(5)]
    engine.ship.cargo = list(crates)

    state = enter_ship(engine)
    for _ in range(3):
        state._after_player_turn(engine)

    assert "EXPLOSIVE DECOMPRESSION!" not in [text for text, _ in engine.message_log.messages]
    assert all(crate in engine.game_map.entities for crate in crates)
    assert not any(crate.drifting for crate in crates)
    assert engine.player.drifting is False
