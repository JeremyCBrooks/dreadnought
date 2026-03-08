"""Tests for the strategic (galaxy navigation) state."""
from types import SimpleNamespace

import numpy as np

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
        gx=0, gy=0,
        locations=locs,
        connections=conns,
        depth=0,
        star_type="yellow_dwarf",
    )
    frontier = set()
    galaxy = SimpleNamespace(
        systems={"TestSystem": system},
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

    def test_direction_changes_system(self):
        galaxy = _make_galaxy(connections={"OtherSystem": 10})
        other = SimpleNamespace(
            name="OtherSystem",
            gx=1, gy=0,
            locations=[],
            connections={"TestSystem": 10},
            depth=1,
            star_type="red_dwarf",
        )
        galaxy.systems["OtherSystem"] = other
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        # Switch to navigation focus first
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert galaxy.current_system == "OtherSystem"

    def test_no_connections_stays(self):
        galaxy = _make_galaxy(connections={})
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
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


    def test_escape_pushes_confirm_quit(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        pushed = []
        engine.push_state = lambda s: pushed.append(s)
        state.ev_keydown(engine, FakeEvent(_sym("ESCAPE")))
        assert len(pushed) == 1
        from ui.confirm_quit_state import ConfirmQuitState
        assert isinstance(pushed[0], ConfirmQuitState)

    def test_pageup_scrolls_message_log(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        # Add enough messages to scroll
        for i in range(20):
            engine.message_log.add_message(f"msg {i}")
        assert engine.message_log._scroll == 0
        state.ev_keydown(engine, FakeEvent(_sym("PAGEUP")))
        assert engine.message_log._scroll == 1
        state.ev_keydown(engine, FakeEvent(_sym("PAGEDOWN")))
        assert engine.message_log._scroll == 0

    def test_shift_q_pushes_confirm_quit(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        pushed = []
        engine.push_state = lambda s: pushed.append(s)
        state.ev_keydown(engine, FakeEvent(_sym("Q")))
        assert len(pushed) == 1
        from ui.confirm_quit_state import ConfirmQuitState
        assert isinstance(pushed[0], ConfirmQuitState)


class TestStrategicFuel:
    def _make_two_system_galaxy(self, dest_frontier=True):
        """Build a galaxy with two connected systems."""
        locs = [SimpleNamespace(name="Loc_0", loc_type="derelict",
                                visited=False, environment={"vacuum": 1})]
        system = SimpleNamespace(
            name="TestSystem", gx=0, gy=0, locations=locs,
            connections={"OtherSystem": 30}, depth=0, star_type="yellow_dwarf",
        )
        other = SimpleNamespace(
            name="OtherSystem", gx=1, gy=0, locations=[],
            connections={"TestSystem": 30}, depth=1, star_type="red_dwarf",
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

    def test_travel_deducts_fuel(self):
        galaxy = self._make_two_system_galaxy(dest_frontier=False)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 5
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert engine.ship.fuel == 4  # explored costs 1

    def test_travel_frontier_costs_2(self):
        galaxy = self._make_two_system_galaxy(dest_frontier=True)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 10
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert engine.ship.fuel == 8  # frontier costs 2
        assert galaxy.current_system == "OtherSystem"

    def test_travel_explored_costs_1(self):
        galaxy = self._make_two_system_galaxy(dest_frontier=False)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 10
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert engine.ship.fuel == 9  # explored costs 1
        assert galaxy.current_system == "OtherSystem"

    def test_travel_blocked_insufficient_fuel(self):
        galaxy = self._make_two_system_galaxy(dest_frontier=True)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 1  # need 2 for frontier
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert galaxy.current_system == "TestSystem"  # didn't move
        assert engine.ship.fuel == 1  # not deducted
        assert any("fuel" in m[0].lower() for m in engine.message_log.messages)

    def test_fuel_gauge_rendered(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 7
        engine.ship.max_fuel = 10
        engine.CONSOLE_WIDTH = 160
        engine.CONSOLE_HEIGHT = 50
        printed = []
        console = SimpleNamespace(
            width=160, height=50,
            rgb=np.zeros((160, 50), dtype=[("ch", np.int32),
                         ("fg", "3u1"), ("bg", "3u1")]),
        )
        original_print = lambda *, x, y, string, fg=(255, 255, 255): printed.append(string)
        console.print = original_print
        console.draw_rect = lambda *a, **kw: None
        state.on_render(console, engine)
        assert any("FUEL: 7/10" in s for s in printed)


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
        state.on_render(console, engine)
