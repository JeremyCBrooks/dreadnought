"""Interdiction lifecycle driven through the game layer, with no UI state involved."""

from engine.game_state import Engine
from game.interdiction import Interdiction, current_interdiction, detach_pirates, prepare_ship_entry, resolve_if_cleared
from tests.conftest import new_game


def _boarded():
    engine, _ = new_game(11)
    interdiction = Interdiction()
    engine.galaxy.systems[engine.galaxy.current_system].interdiction = interdiction
    prepare_ship_entry(engine)
    engine.game_map = engine.ship.game_map
    return engine, interdiction


def test_lifecycle_calls_are_safe_with_no_galaxy():
    """After a game over the galaxy is gone but states still unwind through these."""
    engine = Engine()

    assert current_interdiction(engine) is None
    assert resolve_if_cleared(engine) is False
    prepare_ship_entry(engine)
    detach_pirates(engine)


def test_prepare_ship_entry_starts_a_queued_interdiction_and_attaches_pirates():
    engine, interdiction = _boarded()

    assert interdiction.started is True
    assert engine.ship.game_map is interdiction.composite_map
    assert all(p in engine.ship.game_map.entities for p in interdiction.pirate_entities)
    assert any("clamped onto" in text for text, _ in engine.message_log.messages)


def test_resolve_if_cleared_waits_for_the_last_pirate():
    engine, interdiction = _boarded()

    assert resolve_if_cleared(engine) is False
    for pirate in interdiction.pirate_entities:
        pirate.fighter.hp = 0

    assert resolve_if_cleared(engine) is True
    assert interdiction.resolved is True
    assert resolve_if_cleared(engine) is False


def test_detach_pirates_takes_them_off_the_map_and_drops_the_dead():
    engine, interdiction = _boarded()
    dead = interdiction.pirate_entities[0]
    dead.fighter.hp = 0
    living = interdiction.pirate_entities[1:]

    detach_pirates(engine)

    assert interdiction.pirate_entities == living
    assert all(p not in engine.game_map.entities for p in [dead, *living])
