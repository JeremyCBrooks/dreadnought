"""Tests for fuel balance: cheaper frontier travel + adrift mechanic."""

import random
from types import SimpleNamespace

from game.entity import Entity, Fighter
from game.ship import Ship
from tests.conftest import FakeEvent, MockEngine, make_arena
from ui.strategic_state import StrategicState
from world.galaxy import Galaxy


def _sym(name):
    import tcod.event

    return getattr(tcod.event.KeySym, name)


def _make_two_system_galaxy(dest_frontier=True, dest_locations=None):
    """Build a galaxy with two connected systems (OtherSystem to the right)."""
    locs = [SimpleNamespace(name="Loc_0", loc_type="derelict", visited=False, environment={"vacuum": 1})]
    system = SimpleNamespace(
        name="TestSystem",
        gx=0,
        gy=0,
        locations=locs,
        connections={"OtherSystem": 30},
        depth=0,
        star_type="yellow_dwarf",
    )
    other_locs = dest_locations if dest_locations is not None else []
    other = SimpleNamespace(
        name="OtherSystem",
        gx=1,
        gy=0,
        locations=other_locs,
        connections={"TestSystem": 30},
        depth=1,
        star_type="red_dwarf",
    )
    frontier = {"OtherSystem"} if dest_frontier else set()
    galaxy = SimpleNamespace(
        systems={"TestSystem": system, "OtherSystem": other},
        current_system="TestSystem",
        home_system="TestSystem",
        arrive_at=lambda name: None,
        _unexplored_frontier=frontier,
        travel_cost=lambda dest: 2 if dest in frontier else 1,
    )
    return galaxy


def _make_strategic_engine(galaxy):
    gm = make_arena()
    player = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.ship = Ship()
    return engine


# --- Frontier cost tests ---


def test_frontier_cost_is_2():
    """travel_cost() returns 2 for a frontier (unexplored) system."""
    g = Galaxy(seed=1)
    home = g.systems[g.home_system]
    neighbor_name = next(iter(home.connections))
    assert neighbor_name in g._unexplored_frontier
    assert g.travel_cost(neighbor_name) == 2


def test_explored_cost_is_1():
    """travel_cost() returns 1 for an explored system."""
    g = Galaxy(seed=1)
    home = g.systems[g.home_system]
    neighbor_name = next(iter(home.connections))
    g.arrive_at(neighbor_name)
    assert neighbor_name not in g._unexplored_frontier
    assert g.travel_cost(neighbor_name) == 1


# --- Adrift mechanic tests ---


def test_adrift_when_zero_fuel():
    """0 fuel + travel attempt -> player drifts to a neighbor (not blocked)."""
    galaxy = _make_two_system_galaxy(dest_frontier=True)
    state = StrategicState(galaxy)
    engine = _make_strategic_engine(galaxy)
    engine.ship.fuel = 0
    state.ev_key(engine, FakeEvent(_sym("TAB")))  # navigation focus
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))
    # Should have drifted to some neighbor (only one exists)
    assert galaxy.current_system == "OtherSystem"
    assert engine.ship.fuel == 0  # no fuel deducted


def test_adrift_jettisons_cargo():
    """0 fuel + cargo has items -> one item removed from ship.cargo."""
    galaxy = _make_two_system_galaxy(dest_frontier=True)
    state = StrategicState(galaxy)
    engine = _make_strategic_engine(galaxy)
    engine.ship.fuel = 0
    item1 = Entity(name="Fuel Cell", char="f", color=(255, 255, 0))
    item2 = Entity(name="Data Core", char="d", color=(100, 100, 255))
    engine.ship.cargo = [item1, item2]
    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))
    assert len(engine.ship.cargo) == 1  # one item jettisoned
    # All cargo-loss messages include the jettisoned item's name regardless of which
    # random message was chosen, so this assertion is deterministic.
    jettisoned = next(e for e in [item1, item2] if e not in engine.ship.cargo)
    assert any(jettisoned.name in m[0] for m in engine.message_log.messages)


def test_adrift_no_jettison_empty_cargo():
    """0 fuel + empty cargo -> drift still works, no crash."""
    galaxy = _make_two_system_galaxy(dest_frontier=True)
    state = StrategicState(galaxy)
    engine = _make_strategic_engine(galaxy)
    engine.ship.fuel = 0
    engine.ship.cargo = []
    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))
    assert galaxy.current_system == "OtherSystem"
    assert engine.ship.hull == 9  # hull damaged when drifting with no cargo


def test_adrift_prefers_unvisited_derelicts():
    """Drift with one derelict neighbor and one non-derelict -> derelict chosen more."""
    derelict_loc = SimpleNamespace(name="Wreck", loc_type="derelict", visited=False)
    plain_loc = SimpleNamespace(name="Rock", loc_type="asteroid", visited=False)
    system = SimpleNamespace(
        name="TestSystem",
        gx=0,
        gy=0,
        locations=[],
        connections={"DerelictSys": 30, "PlainSys": 30},
        depth=0,
        star_type="yellow_dwarf",
    )
    derelict_sys = SimpleNamespace(
        name="DerelictSys",
        gx=1,
        gy=0,
        locations=[derelict_loc],
        connections={"TestSystem": 30},
        depth=1,
        star_type="red_dwarf",
    )
    plain_sys = SimpleNamespace(
        name="PlainSys",
        gx=0,
        gy=1,
        locations=[plain_loc],
        connections={"TestSystem": 30},
        depth=1,
        star_type="red_dwarf",
    )
    frontier = {"DerelictSys", "PlainSys"}
    galaxy = SimpleNamespace(
        systems={"TestSystem": system, "DerelictSys": derelict_sys, "PlainSys": plain_sys},
        current_system="TestSystem",
        home_system="TestSystem",
        arrive_at=lambda name: None,
        _unexplored_frontier=frontier,
        travel_cost=lambda dest: 2 if dest in frontier else 1,
    )

    counts = {"DerelictSys": 0, "PlainSys": 0}
    for i in range(200):
        galaxy.current_system = "TestSystem"
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 0
        random.seed(i)
        state.ev_key(engine, FakeEvent(_sym("TAB")))
        state.ev_key(engine, FakeEvent(_sym("RIGHT")))
        counts[galaxy.current_system] += 1

    # Derelict should be chosen significantly more (weight 5 vs 1)
    assert counts["DerelictSys"] > counts["PlainSys"] * 2


def test_adrift_blocked_when_has_some_fuel():
    """fuel=1, cost=2 -> 'Not enough fuel.' (no drift, drift only at 0)."""
    galaxy = _make_two_system_galaxy(dest_frontier=True)
    state = StrategicState(galaxy)
    engine = _make_strategic_engine(galaxy)
    engine.ship.fuel = 1  # has some fuel but not enough for frontier (cost 2)
    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))
    assert galaxy.current_system == "TestSystem"  # didn't move
    assert engine.ship.fuel == 1  # not deducted
    assert any("fuel" in m[0].lower() for m in engine.message_log.messages)


def test_adrift_messages():
    """Verify desperate-tone messages appear in log."""
    galaxy = _make_two_system_galaxy(dest_frontier=True)
    state = StrategicState(galaxy)
    engine = _make_strategic_engine(galaxy)
    engine.ship.fuel = 0
    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))
    texts = [m[0] for m in engine.message_log.messages]
    assert any("Engines dead" in t for t in texts)
    assert any("Drifting into" in t for t in texts)
