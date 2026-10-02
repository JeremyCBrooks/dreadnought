"""Pirates dock when the ship arrives, not when the player later walks aft.

The bridge may only claim a boarding that is really happening: a craft that
could not find a docking point is a non-event and leaves no trace at all.
"""

from __future__ import annotations

from game.entity import Entity
from game.interdiction import Interdiction, current_interdiction, prepare_ship_entry
from tests.conftest import FakeEvent, enter_ship, key_for, new_game, render_collecting, row_text
from ui.break_away_state import BreakAwayState
from ui.strategic_state import _direction, helm_layout

# Seed 1's ship has an airlock pirates can reach; seed 37's lone side airlock
# can never be reached by a boarding corridor.
BOARDABLE_SEED = 1
UNBOARDABLE_SEED = 37


def _game_with_cargo(seed: int):
    """A fresh game with something aboard worth stealing."""
    engine, strategic = new_game(seed)
    engine.ship.add_cargo(Entity(name="Scrap", item={"type": "scrap", "value": 1}))
    return engine, strategic


def _jump(engine, strategic) -> None:
    """Travel to the first neighbour of the current system."""
    galaxy = engine.galaxy
    here = galaxy.systems[galaxy.current_system]
    dest = next(iter(here.connections))
    strategic.focus = "navigation"
    strategic.ev_key(engine, FakeEvent(key_for(_direction(here, galaxy.systems[dest]))))
    assert galaxy.current_system == dest


def _arrive_with_cargo(seed: int):
    engine, strategic = _game_with_cargo(seed)
    _jump(engine, strategic)
    return engine, strategic


def _messages(engine) -> str:
    return " ".join(text for text, *_ in engine.message_log.messages)


def _sill(engine, strategic) -> str:
    return row_text(render_collecting(strategic, engine), helm_layout(160, 50).sill_y)


class TestPiratesDock:
    def test_craft_is_docked_before_the_player_leaves_the_bridge(self):
        engine, _ = _arrive_with_cargo(BOARDABLE_SEED)
        interdiction = current_interdiction(engine)
        assert interdiction is not None
        assert interdiction.started and not interdiction.resolved
        assert interdiction.pirate_entities
        assert engine.ship.game_map is interdiction.composite_map

    def test_bridge_announces_which_airlock_was_clamped(self):
        engine, _ = _arrive_with_cargo(BOARDABLE_SEED)
        log = _messages(engine)
        assert "clamped onto the" in log
        assert any(heading in log for heading in ("north", "south", "east", "west"))

    def test_bridge_shows_the_boarding_alert(self):
        engine, strategic = _arrive_with_cargo(BOARDABLE_SEED)
        assert "BEING BOARDED" in _sill(engine, strategic)

    def test_boarding_the_ship_finds_the_pirates_already_there(self):
        engine, _ = _arrive_with_cargo(BOARDABLE_SEED)
        pirates = list(current_interdiction(engine).pirate_entities)
        enter_ship(engine)
        assert current_interdiction(engine).pirate_entities == pirates, "pirates must not be respawned"
        assert all(pirate in engine.game_map.entities for pirate in pirates)

    def test_boarding_the_ship_does_not_repeat_the_announcement(self):
        engine, _ = _arrive_with_cargo(BOARDABLE_SEED)
        enter_ship(engine)
        assert _messages(engine).count("clamped onto the") == 1


class TestFailedDockingIsANonEvent:
    def test_no_interdiction_is_recorded(self):
        engine, _ = _arrive_with_cargo(UNBOARDABLE_SEED)
        assert current_interdiction(engine) is None

    def test_ship_map_is_left_alone(self):
        engine, strategic = _game_with_cargo(UNBOARDABLE_SEED)
        original_map = engine.ship.game_map
        _jump(engine, strategic)
        assert engine.ship.game_map is original_map

    def test_bridge_shows_no_boarding_alert(self):
        engine, strategic = _arrive_with_cargo(UNBOARDABLE_SEED)
        assert "BOARDED" not in _sill(engine, strategic)

    def test_nothing_is_said_about_pirates(self):
        engine, _ = _arrive_with_cargo(UNBOARDABLE_SEED)
        enter_ship(engine)
        log = _messages(engine).lower()
        assert "pirate" not in log
        assert "broke off" not in log

    def test_travel_onward_needs_no_break_away(self):
        engine, strategic = _arrive_with_cargo(UNBOARDABLE_SEED)
        arrived_at = engine.galaxy.current_system
        _jump(engine, strategic)
        assert not engine.has_state(BreakAwayState)
        assert engine.galaxy.current_system != arrived_at


class TestQueuedInterdictionFromAnOlderSave:
    """Saves written before docking moved to arrival can still hold an unstarted interdiction."""

    def _engine(self, seed: int):
        engine, _ = new_game(seed)
        galaxy = engine.galaxy
        galaxy.current_system = next(iter(galaxy.systems[galaxy.home_system].connections))
        galaxy.systems[galaxy.current_system].interdiction = Interdiction()
        return engine

    def test_docks_when_the_player_boards(self):
        engine = self._engine(BOARDABLE_SEED)
        prepare_ship_entry(engine)
        assert current_interdiction(engine).started
        assert "clamped onto the" in _messages(engine)

    def test_failed_docking_is_forgotten_without_a_word(self):
        engine = self._engine(UNBOARDABLE_SEED)
        before = _messages(engine)
        prepare_ship_entry(engine)
        assert current_interdiction(engine) is None
        assert _messages(engine) == before
