"""Tests for the strategic (galaxy navigation) state."""

from types import SimpleNamespace

import numpy as np

from game.entity import Entity, Fighter
from game.ship import Ship
from tests.conftest import FakeEvent, MockEngine, make_arena
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
        gx=0,
        gy=0,
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
        dreadnought_system=None,
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
        state.ev_key(engine, FakeEvent(_sym("DOWN")))
        assert state.selected == 1

    def test_move_up_decrements_selection(self):
        galaxy = _make_galaxy(num_locations=3)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_key(engine, FakeEvent(_sym("DOWN")))
        state.ev_key(engine, FakeEvent(_sym("DOWN")))
        state.ev_key(engine, FakeEvent(_sym("UP")))
        assert state.selected == 1

    def test_move_up_clamps_at_zero(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_key(engine, FakeEvent(_sym("UP")))
        assert state.selected == 0

    def test_move_down_clamps_at_max(self):
        galaxy = _make_galaxy(num_locations=2)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_key(engine, FakeEvent(_sym("DOWN")))
        state.ev_key(engine, FakeEvent(_sym("DOWN")))
        state.ev_key(engine, FakeEvent(_sym("DOWN")))
        assert state.selected == 1

    def test_direction_changes_system(self):
        galaxy = _make_galaxy(connections={"OtherSystem": 10})
        other = SimpleNamespace(
            name="OtherSystem",
            gx=1,
            gy=0,
            locations=[],
            connections={"TestSystem": 10},
            depth=1,
            star_type="red_dwarf",
        )
        galaxy.systems["OtherSystem"] = other
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        # Switch to navigation focus first
        state.ev_key(engine, FakeEvent(_sym("TAB")))
        state.ev_key(engine, FakeEvent(_sym("RIGHT")))
        assert galaxy.current_system == "OtherSystem"

    def test_no_connections_stays(self):
        galaxy = _make_galaxy(connections={})
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        state.ev_key(engine, FakeEvent(_sym("TAB")))
        state.ev_key(engine, FakeEvent(_sym("LEFT")))
        assert galaxy.current_system == "TestSystem"

    def test_confirm_pushes_briefing(self):
        galaxy = _make_galaxy(num_locations=1)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine._state_stack = [state]
        engine.push_state = lambda s: engine._state_stack.append(s)
        state.ev_key(engine, FakeEvent(_sym("RETURN")))
        assert len(engine._state_stack) == 2
        assert galaxy.systems["TestSystem"].locations[0].visited

    def test_confirm_empty_locations_noop(self):
        galaxy = _make_galaxy(num_locations=0)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        result = state.ev_key(engine, FakeEvent(_sym("RETURN")))
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
        state.ev_key(engine, FakeEvent(_sym("c")))
        assert len(pushed) == 1
        from ui.cargo_state import CargoState

        assert isinstance(pushed[0], CargoState)

    def test_escape_pushes_confirm_quit(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        pushed = []
        engine.push_state = lambda s: pushed.append(s)
        state.ev_key(engine, FakeEvent(_sym("ESCAPE")))
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
        state.ev_key(engine, FakeEvent(_sym("PAGEUP")))
        assert engine.message_log._scroll == 1
        state.ev_key(engine, FakeEvent(_sym("PAGEDOWN")))
        assert engine.message_log._scroll == 0

    def test_shift_q_pushes_confirm_quit(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        pushed = []
        engine.push_state = lambda s: pushed.append(s)
        state.ev_key(engine, FakeEvent(_sym("Q")))
        assert len(pushed) == 1
        from ui.confirm_quit_state import ConfirmQuitState

        assert isinstance(pushed[0], ConfirmQuitState)


class TestStrategicFuel:
    def _make_two_system_galaxy(self, dest_frontier=True):
        """Build a galaxy with two connected systems."""
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
        other = SimpleNamespace(
            name="OtherSystem",
            gx=1,
            gy=0,
            locations=[],
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
            dreadnought_system=None,
        )
        return galaxy

    def test_travel_deducts_fuel(self):
        galaxy = self._make_two_system_galaxy(dest_frontier=False)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 5
        state.ev_key(engine, FakeEvent(_sym("TAB")))
        state.ev_key(engine, FakeEvent(_sym("RIGHT")))
        assert engine.ship.fuel == 4  # explored costs 1

    def test_travel_frontier_costs_2(self):
        galaxy = self._make_two_system_galaxy(dest_frontier=True)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 10
        state.ev_key(engine, FakeEvent(_sym("TAB")))
        state.ev_key(engine, FakeEvent(_sym("RIGHT")))
        assert engine.ship.fuel == 8  # frontier costs 2
        assert galaxy.current_system == "OtherSystem"

    def test_travel_explored_costs_1(self):
        galaxy = self._make_two_system_galaxy(dest_frontier=False)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 10
        state.ev_key(engine, FakeEvent(_sym("TAB")))
        state.ev_key(engine, FakeEvent(_sym("RIGHT")))
        assert engine.ship.fuel == 9  # explored costs 1
        assert galaxy.current_system == "OtherSystem"

    def test_travel_blocked_insufficient_fuel(self):
        galaxy = self._make_two_system_galaxy(dest_frontier=True)
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 1  # need 2 for frontier
        state.ev_key(engine, FakeEvent(_sym("TAB")))
        state.ev_key(engine, FakeEvent(_sym("RIGHT")))
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
            width=160,
            height=50,
            rgb=np.zeros((160, 50), dtype=[("ch", np.int32), ("fg", "3u1"), ("bg", "3u1")]),
        )

        def original_print(*, x, y, string, fg=(255, 255, 255)):
            printed.append(string)

        console.print = original_print
        console.draw_rect = lambda *a, **kw: None
        state.on_render(console, engine)
        assert any("FUEL: 7/10" in s for s in printed)


class TestStrategicRender:
    def _make_console(self, w=160, h=50):
        console = SimpleNamespace(
            width=w,
            height=h,
            rgb=np.zeros((w, h), dtype=[("ch", np.int32), ("fg", "3u1"), ("bg", "3u1")]),
        )
        console.print = lambda *, x, y, string, fg=(255, 255, 255): None
        console.draw_rect = lambda *a, **kw: None
        return console

    def _render_collecting(self, engine, galaxy=None):
        """Render and return list of (x, y, string, fg) tuples."""
        if galaxy is None:
            galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine.CONSOLE_WIDTH = 160
        engine.CONSOLE_HEIGHT = 50
        printed = []
        console = self._make_console()
        console.print = lambda *, x, y, string, fg=(255, 255, 255): printed.append((x, y, string, fg))
        state.on_render(console, engine)
        return printed

    def test_on_render_smoke(self):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_strategic_engine(galaxy)
        engine.CONSOLE_WIDTH = 160
        engine.CONSOLE_HEIGHT = 50
        console = self._make_console()
        state.on_render(console, engine)

    def test_fuel_color_uses_ratio_not_absolute(self):
        """Fuel at 6/200 (3%) should be red, not green."""
        galaxy = _make_galaxy()
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 6
        engine.ship.max_fuel = 200
        printed = self._render_collecting(engine, galaxy)
        fuel_entries = [(x, y, s, fg) for x, y, s, fg in printed if "FUEL:" in s]
        assert fuel_entries, "FUEL not rendered"
        _, _, _, fg = fuel_entries[0]
        assert fg == (255, 0, 0), f"Fuel 6/200 should be red, got {fg}"

    def test_fuel_color_green_when_above_half(self):
        """Fuel at 150/200 (75%) should be green."""
        galaxy = _make_galaxy()
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 150
        engine.ship.max_fuel = 200
        printed = self._render_collecting(engine, galaxy)
        fuel_entries = [(x, y, s, fg) for x, y, s, fg in printed if "FUEL:" in s]
        assert fuel_entries, "FUEL not rendered"
        _, _, _, fg = fuel_entries[0]
        assert fg == (0, 255, 0), f"Fuel 150/200 should be green, got {fg}"

    def test_fuel_color_yellow_when_between_30_and_50(self):
        """Fuel at 8/20 (40%) should be yellow."""
        galaxy = _make_galaxy()
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 8
        engine.ship.max_fuel = 20
        printed = self._render_collecting(engine, galaxy)
        fuel_entries = [(x, y, s, fg) for x, y, s, fg in printed if "FUEL:" in s]
        assert fuel_entries, "FUEL not rendered"
        _, _, _, fg = fuel_entries[0]
        assert fg == (255, 255, 0), f"Fuel 8/20 should be yellow, got {fg}"

    def test_hud_renders_without_ship(self):
        """HUD should not crash when engine.ship is None."""
        galaxy = _make_galaxy()
        engine = _make_strategic_engine(galaxy)
        engine.ship = None
        engine.CONSOLE_WIDTH = 160
        engine.CONSOLE_HEIGHT = 50
        console = self._make_console()
        state = StrategicState(galaxy)
        state.on_render(console, engine)  # should not raise

    def test_nav_hud_locked_when_dreadnought_spawned(self):
        """NAV should show LOCKED when nav units are maxed and dreadnought exists."""
        galaxy = _make_galaxy()
        galaxy.dreadnought_system = "Dreadnought"
        engine = _make_strategic_engine(galaxy)
        engine.ship.nav_units = engine.ship.max_nav_units
        printed = self._render_collecting(engine, galaxy)
        nav_entries = [s for _, _, s, _ in printed if "NAV" in s]
        assert any("LOCKED" in s for s in nav_entries)

    def test_nav_hud_count_when_not_maxed(self):
        """NAV should show count when nav units are not maxed."""
        galaxy = _make_galaxy()
        engine = _make_strategic_engine(galaxy)
        engine.ship.nav_units = 3
        printed = self._render_collecting(engine, galaxy)
        nav_entries = [s for _, _, s, _ in printed if "NAV" in s]
        assert any("3/6" in s for s in nav_entries)


def test_strategic_navigate_all_systems():
    """Direction keys should allow navigating the graph of systems."""
    import tcod.event

    from engine.game_state import Engine
    from world.galaxy import Galaxy

    class _FakeEvent:
        def __init__(self, sym):
            self.sym = sym

    galaxy = Galaxy(seed=42)
    state = StrategicState(galaxy)

    engine = Engine()
    engine.ship = Ship()

    # All systems should be reachable via BFS
    visited = {galaxy.home_system}
    queue = [galaxy.home_system]
    while queue:
        name = queue.pop(0)
        for neighbor in galaxy.systems[name].connections:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    assert visited == set(galaxy.systems.keys()), "All systems reachable"

    # Navigate from home to a connected system using the correct direction key
    home = galaxy.systems[galaxy.home_system]
    neighbor_name = next(iter(home.connections))
    neighbor = galaxy.systems[neighbor_name]
    dx = (neighbor.gx > home.gx) - (neighbor.gx < home.gx)
    dy = (neighbor.gy > home.gy) - (neighbor.gy < home.gy)
    _dir_to_key = {
        (0, -1): "UP",
        (0, 1): "DOWN",
        (-1, 0): "LEFT",
        (1, 0): "RIGHT",
        (-1, -1): "KP_7",
        (1, -1): "KP_9",
        (-1, 1): "KP_1",
        (1, 1): "KP_3",
    }
    key_name = _dir_to_key[(dx, dy)]
    # Tab to navigation focus, then navigate
    state.ev_key(engine, _FakeEvent(tcod.event.KeySym.TAB))
    state.ev_key(engine, _FakeEvent(getattr(tcod.event.KeySym, key_name)))
    assert galaxy.current_system == neighbor_name

    # Focus stays on navigation; navigate back home
    back_key = _dir_to_key[(-dx, -dy)]
    state.ev_key(engine, _FakeEvent(getattr(tcod.event.KeySym, back_key)))
    assert galaxy.current_system == home.name
