"""Searched furnishings on the player's ship stay searched across save/load.

The ship interior is regenerated from the galaxy seed on every load, so the
save records which of the generated furnishings are gone and the load takes
them back off the fresh map.
"""

from __future__ import annotations

import random

from game.entity import Entity
from game.helpers import missing_entity_indices, remove_entities_at_indices
from game.interdiction import Interdiction, start_interdiction
from game.ship import Ship
from web.save_load import dict_to_engine, engine_to_dict
from world import tile_types
from world.dungeon_gen import generate_player_ship
from world.galaxy import Galaxy
from world.game_map import GameMap

SEED = 42


def _engine():
    from engine.game_state import Engine

    engine = Engine()
    engine.galaxy = Galaxy(seed=SEED)
    engine.ship = Ship()
    engine.ship.generate_interior(engine.galaxy.seed)
    engine.saved_player = None
    engine.environment = None
    return engine


def _reload(engine):
    from engine.game_state import Engine

    new_engine = Engine()
    dict_to_engine(engine_to_dict(engine), new_engine)
    return new_engine


def _search(ship: Ship, index: int) -> None:
    """Remove a furnishing from the ship map, as InteractAction does after a search."""
    ship.game_map.entities.remove(ship.furnishings[index])


def _furnishings_on_map(ship: Ship) -> list[bool]:
    on_map = {id(e) for e in ship.game_map.entities}
    return [id(e) in on_map for e in ship.furnishings]


def _thing(name: str) -> Entity:
    return Entity(x=1, y=1, char="L", color=(255, 255, 255), name=name)


# ---- entity-index helpers ----


def test_missing_entity_indices_reports_removed_entities():
    game_map = GameMap(5, 5, fill_tile=tile_types.floor)
    pristine = [_thing("a"), _thing("b"), _thing("c")]
    game_map.entities.extend([pristine[0], pristine[2]])
    assert missing_entity_indices(pristine, game_map) == [1]


def test_missing_entity_indices_uses_identity_not_equality():
    """A different entity that merely looks the same must not count as present."""
    game_map = GameMap(5, 5, fill_tile=tile_types.floor)
    pristine = [_thing("a")]
    game_map.entities.append(_thing("a"))
    assert missing_entity_indices(pristine, game_map) == [0]


def test_remove_entities_at_indices_removes_only_those_entities():
    game_map = GameMap(5, 5, fill_tile=tile_types.floor)
    pristine = [_thing("a"), _thing("b"), _thing("c")]
    bystander = _thing("bystander")
    game_map.entities.extend([*pristine, bystander])
    entity_list = game_map.entities

    remove_entities_at_indices(pristine, [0, 2], game_map)

    assert game_map.entities == [pristine[1], bystander]
    assert game_map.entities is entity_list, "list must be mutated in place (it can be shared)"


def test_remove_entities_at_indices_ignores_out_of_range_indices():
    game_map = GameMap(5, 5, fill_tile=tile_types.floor)
    pristine = [_thing("a")]
    game_map.entities.extend(pristine)

    remove_entities_at_indices(pristine, [7], game_map)

    assert game_map.entities == pristine


# ---- Ship.generate_interior ----


def test_generate_interior_installs_the_seeded_ship_layout():
    ship = Ship()
    ship.generate_interior(SEED)
    expected_map, expected_rooms, expected_exit = generate_player_ship(seed=SEED)
    assert ship.exit_pos == expected_exit
    assert [r.center for r in ship.rooms] == [r.center for r in expected_rooms]
    assert (ship.game_map.tiles["tile_id"] == expected_map.tiles["tile_id"]).all()


def test_generate_interior_records_furnishings():
    ship = Ship()
    ship.generate_interior(SEED)
    assert len(ship.furnishings) >= 2, "player ship should have furnishings"
    assert all(_furnishings_on_map(ship))


def test_ship_without_generated_interior_reports_nothing_consumed():
    ship = Ship()
    ship.game_map = GameMap(5, 5, fill_tile=tile_types.floor)
    assert ship.consumed_furnishing_indices() == []


# ---- save/load ----


def test_searched_furnishing_stays_gone_after_reload():
    engine = _engine()
    _search(engine.ship, 0)
    expected = _furnishings_on_map(engine.ship)

    reloaded = _reload(engine)

    assert _furnishings_on_map(reloaded.ship) == expected
    assert expected[0] is False and all(expected[1:])


def test_unsearched_furnishings_all_return_after_reload():
    reloaded = _reload(_engine())
    assert all(_furnishings_on_map(reloaded.ship))


def test_furnishings_searched_across_separate_sessions_all_stay_gone():
    engine = _engine()
    _search(engine.ship, 0)
    reloaded = _reload(engine)
    _search(reloaded.ship, 1)

    reloaded_again = _reload(reloaded)

    on_map = _furnishings_on_map(reloaded_again.ship)
    assert on_map[:2] == [False, False] and all(on_map[2:])


def test_furnishing_searched_during_boarding_stays_gone_after_reload():
    """While boarded the active map is the composite, which shares the ship's entity list."""
    engine = _engine()
    home = engine.galaxy.systems[engine.galaxy.home_system]
    for seed in range(200):
        interdiction = Interdiction()
        start_interdiction(interdiction, engine.ship, rng=random.Random(seed))
        if interdiction.started:
            break
    else:
        raise RuntimeError("could not start an interdiction with any seed")
    home.interdiction = interdiction
    _search(engine.ship, 0)

    reloaded = _reload(engine)

    on_map = _furnishings_on_map(reloaded.ship)
    assert on_map[0] is False and all(on_map[1:])


def test_save_from_before_furnishing_tracking_still_loads():
    """Old saves have no consumed list; they load with every furnishing present."""
    from engine.game_state import Engine

    data = engine_to_dict(_engine())
    del data["ship"]["consumed_furnishings"]
    new_engine = Engine()
    dict_to_engine(data, new_engine)

    assert all(_furnishings_on_map(new_engine.ship))
