"""Tests for interdiction travel-blocking + drift detach (Phase 3).

* While a system has an unresolved interdiction, navigation is blocked
  (warning in log, no fuel consumed, no system change).
* Once resolved, navigation works normally.
* Drift (fuel-0 forced travel) escapes interdiction by marking it resolved
  on the source system before traveling.
"""

from __future__ import annotations

from types import SimpleNamespace

from game.entity import Entity, Fighter
from game.interdiction import Interdiction
from game.ship import Ship
from tests.conftest import FakeEvent, MockEngine, make_arena
from ui.strategic_state import StrategicState


def _sym(name):
    import tcod.event

    return getattr(tcod.event.KeySym, name)


def _two_system_galaxy() -> SimpleNamespace:
    """Two systems with a single connection in each direction."""
    here = SimpleNamespace(
        name="Here",
        gx=0,
        gy=0,
        locations=[],
        connections={"There": 30},
        depth=0,
        star_type="yellow_dwarf",
        interdiction=None,
    )
    there = SimpleNamespace(
        name="There",
        gx=1,
        gy=0,
        locations=[],
        connections={"Here": 30},
        depth=1,
        star_type="red_dwarf",
        interdiction=None,
    )
    return SimpleNamespace(
        systems={"Here": here, "There": there},
        current_system="Here",
        home_system="Here",
        arrive_at=lambda name, **_: None,
        _unexplored_frontier=set(),
        travel_cost=lambda dest: 1,
        dreadnought_system=None,
        seed=42,
    )


def _engine(galaxy) -> MockEngine:
    gm = make_arena()
    player = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.ship = Ship(fuel=5, max_fuel=10)
    engine.galaxy = galaxy
    return engine


# ---- Navigation gate ----


def test_navigation_blocked_while_interdiction_active():
    galaxy = _two_system_galaxy()
    galaxy.systems["Here"].interdiction = Interdiction(started=True)
    state = StrategicState(galaxy)
    engine = _engine(galaxy)
    fuel_before = engine.ship.fuel

    state.ev_key(engine, FakeEvent(_sym("TAB")))  # navigation focus
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))

    assert galaxy.current_system == "Here", "must not move while interdicted"
    assert engine.ship.fuel == fuel_before, "must not consume fuel when blocked"
    # A warning should be logged.
    assert any("board" in m[0].lower() or "escape" in m[0].lower() for m in engine.message_log._messages), (
        f"expected interdiction warning in log, got {engine.message_log._messages}"
    )


def test_navigation_unblocked_after_interdiction_resolved():
    galaxy = _two_system_galaxy()
    galaxy.systems["Here"].interdiction = Interdiction(started=True, resolved=True)
    state = StrategicState(galaxy)
    engine = _engine(galaxy)

    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))

    assert galaxy.current_system == "There", "resolved interdiction must not block"


def test_navigation_works_with_no_interdiction():
    galaxy = _two_system_galaxy()  # interdiction stays None
    state = StrategicState(galaxy)
    engine = _engine(galaxy)

    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))

    assert galaxy.current_system == "There"


# ---- Drift detach ----


def test_drift_marks_active_interdiction_resolved_on_source_system():
    galaxy = _two_system_galaxy()
    interdiction = Interdiction(started=True)
    galaxy.systems["Here"].interdiction = interdiction
    state = StrategicState(galaxy)
    engine = _engine(galaxy)
    engine.ship.fuel = 0  # force drift on next nav attempt

    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))

    # Drift carried us away.
    assert galaxy.current_system == "There"
    # Source-system interdiction is now resolved (the boarding craft tore free).
    assert interdiction.resolved is True


def test_drift_does_not_create_interdiction_on_source_when_none_existed():
    """Sanity: drift without an active interdiction must not invent one."""
    galaxy = _two_system_galaxy()
    state = StrategicState(galaxy)
    engine = _engine(galaxy)
    engine.ship.fuel = 0

    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))

    assert galaxy.systems["Here"].interdiction is None
