"""Tests for the strategic (galaxy navigation) state."""
from types import SimpleNamespace

import numpy as np
import pytest

from tests.conftest import FakeEvent, MockEngine, make_arena
from game.entity import Entity, Fighter
from game.ship import Ship
from ui.strategic_state import StrategicState


def _sym(name):
    import tcod.event
    return getattr(tcod.event.KeySym, name)


def _make_galaxy(num_locations=3, connections=None):
    """Build a minimal galaxy with one system."""
    locs = []
    for i in range(num_locations):
        loc = SimpleNamespace(
            name=f"Location_{i}",
            loc_type="derelict",
            visited=False,
            environment={"vacuum": 1},
        )
        locs.append(loc)
    conns = connections or {}
    system = SimpleNamespace(
        name="TestSystem",
        locations=locs,
        connections=conns,
        depth=0,
        star_type="yellow_dwarf",
    )
    galaxy = SimpleNamespace(
        systems={"TestSystem": system},
        current_system="TestSystem",
    )
    return galaxy


def _make_strategic_engine(galaxy):
    gm = make_arena()
    player = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.ship = Ship()
    return engine


class TestStrategicNavigation:
    def test_initial_selection_is_zero(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        assert state.selected == 0

    def test_move_down_increments_selection(self):
        galaxy = _make_galaxy(num_locations=3)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        assert state.selected == 1

    def test_move_up_decrements_selection(self):
        galaxy = _make_galaxy(num_locations=3)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        state.ev_keydown(engine, FakeEvent(_sym("UP")))
        assert state.selected == 1

    def test_move_up_clamps_at_zero(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("UP")))
        assert state.selected == 0

    def test_move_down_clamps_at_max(self):
        galaxy = _make_galaxy(num_locations=2)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        assert state.selected == 1

    def test_left_right_changes_system(self):
        galaxy = _make_galaxy(connections={"OtherSystem": 10})
        other = SimpleNamespace(
            name="OtherSystem",
            locations=[],
            connections={"TestSystem": 10},
            depth=1,
            star_type="red_dwarf",
        )
        galaxy.systems["OtherSystem"] = other
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("LEFT")))
        assert galaxy.current_system == "OtherSystem"

    def test_left_no_connections_stays(self):
        galaxy = _make_galaxy(connections={})
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("LEFT")))
        assert galaxy.current_system == "TestSystem"

    def test_confirm_pushes_briefing(self):
        galaxy = _make_galaxy(num_locations=1)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine._state_stack = [state]
        engine.push_state = lambda s: engine._state_stack.append(s)
        state.ev_keydown(engine, FakeEvent(_sym("RETURN")))
        assert len(engine._state_stack) == 2
        assert galaxy.systems["TestSystem"].locations[0].visited

    def test_confirm_empty_locations_noop(self):
        galaxy = _make_galaxy(num_locations=0)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        result = state.ev_keydown(engine, FakeEvent(_sym("RETURN")))
        assert result is True

    def test_on_enter_message(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.on_enter(engine)
        assert any("aboard" in m[0] for m in engine.message_log.messages)

    def test_cargo_key_pushes_cargo_state(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship = Ship()
        pushed = []
        engine.push_state = lambda s: pushed.append(s)
        state.ev_keydown(engine, FakeEvent(_sym("c")))
        assert len(pushed) == 1
        from ui.cargo_state import CargoState
        assert isinstance(pushed[0], CargoState)


class TestStrategicRender:
    def _make_console(self, w=160, h=50):
        console = SimpleNamespace(
            width=w, height=h,
            rgb=np.zeros((w, h), dtype=[("ch", np.int32),
                         ("fg", "3u1"), ("bg", "3u1")]),
        )
        console.print = lambda *, x, y, string, fg=(255, 255, 255): None
        console.draw_rect = lambda *a, **kw: None
        return console

    def test_on_render_smoke(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.CONSOLE_WIDTH = 160
        engine.CONSOLE_HEIGHT = 50
        console = self._make_console()
        # Should not raise
        state.on_render(console, engine)
