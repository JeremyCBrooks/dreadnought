"""Tests for graph-based strategic state navigation with Tab toggle."""
from types import SimpleNamespace

import numpy as np

from tests.conftest import FakeEvent, MockEngine, make_arena
from game.entity import Entity, Fighter
from game.ship import Ship
from ui.strategic_state import StrategicState


def _sym(name):
    import tcod.event
    return getattr(tcod.event.KeySym, name)


def _make_system(name, gx, gy, connections=None, locations=None, depth=0):
    locs = locations or []
    return SimpleNamespace(
        name=name, gx=gx, gy=gy,
        locations=locs,
        connections=connections or {},
        depth=depth,
        star_type="yellow_dwarf",
    )


def _make_location(name="Loc", loc_type="derelict"):
    return SimpleNamespace(
        name=name, loc_type=loc_type, visited=False, environment={"vacuum": 1},
    )


def _make_engine(galaxy):
    gm = make_arena()
    player = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.ship = Ship()
    return engine


def _make_graph_galaxy():
    """Build a small 3-system graph:

        A(0,0) -- B(1,0)
                   |
                  C(1,1)
    """
    a = _make_system("A", 0, 0, {"B": 30}, [_make_location("A1"), _make_location("A2")])
    b = _make_system("B", 1, 0, {"A": 30, "C": 40}, [_make_location("B1")])
    c = _make_system("C", 1, 1, {"B": 40}, [_make_location("C1")])
    frontier = set()
    galaxy = SimpleNamespace(
        systems={"A": a, "B": b, "C": c},
        current_system="A",
        home_system="A",
        arrive_at=lambda name: None,
        _unexplored_frontier=frontier,
        travel_cost=lambda dest: 2 if dest in frontier else 1,
    )
    return galaxy


class TestTabToggle:
    def test_initial_focus_is_locations(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        assert state.focus == "locations"

    def test_tab_toggles_to_navigation(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        assert state.focus == "navigation"

    def test_tab_toggles_back_to_locations(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        assert state.focus == "locations"


class TestLocationFocus:
    def test_up_down_selects_locations(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        assert state.selected == 0
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        assert state.selected == 1
        state.ev_keydown(engine, FakeEvent(_sym("UP")))
        assert state.selected == 0

    def test_enter_docks(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        engine._state_stack = [state]
        engine.push_state = lambda s: engine._state_stack.append(s)
        state.ev_keydown(engine, FakeEvent(_sym("RETURN")))
        assert len(engine._state_stack) == 2
        assert galaxy.systems["A"].locations[0].visited

    def test_direction_keys_ignored_in_location_focus(self):
        """Horizontal keys should not navigate systems when focus=locations."""
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert galaxy.current_system == "A"

    def test_selection_clamps(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        assert state.selected == 1
        state.ev_keydown(engine, FakeEvent(_sym("UP")))
        state.ev_keydown(engine, FakeEvent(_sym("UP")))
        assert state.selected == 0


class TestNavigationFocus:
    def test_direction_key_moves_to_connected_system(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))  # switch to navigation
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert galaxy.current_system == "B"

    def test_direction_no_connection_stays(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.ev_keydown(engine, FakeEvent(_sym("LEFT")))
        assert galaxy.current_system == "A"

    def test_navigate_resets_selection(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        assert state.selected == 1
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert state.selected == 0

    def test_enter_does_not_dock_in_navigation_focus(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        engine._state_stack = [state]
        engine.push_state = lambda s: engine._state_stack.append(s)
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.ev_keydown(engine, FakeEvent(_sym("RETURN")))
        assert len(engine._state_stack) == 1  # no briefing pushed

    def test_navigate_stays_in_navigation_focus(self):
        """After traveling, focus stays on navigation."""
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert state.focus == "navigation"

    def test_diagonal_navigation(self):
        """Diagonal keys should navigate to diagonally-connected systems."""
        a = _make_system("A", 0, 0, {"D": 30}, [_make_location("A1")])
        d = _make_system("D", 1, 1, {"A": 30}, [_make_location("D1")])
        frontier = set()
        galaxy = SimpleNamespace(
            systems={"A": a, "D": d},
            current_system="A",
            home_system="A",
            arrive_at=lambda name: None,
            _unexplored_frontier=frontier,
            travel_cost=lambda dest: 2 if dest in frontier else 1,
        )
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        # D is at (1,1) relative to A at (0,0) = SE = KP_3 or 'n'
        state.ev_keydown(engine, FakeEvent(_sym("KP_3")))
        assert galaxy.current_system == "D"


class TestSharedKeys:
    def test_cargo_works_in_either_focus(self):
        for focus in ("locations", "navigation"):
            galaxy = _make_graph_galaxy()
            state = StrategicState(galaxy)
            engine = _make_engine(galaxy)
            engine.ship = Ship()
            pushed = []
            engine.push_state = lambda s: pushed.append(s)
            if focus == "navigation":
                state.ev_keydown(engine, FakeEvent(_sym("TAB")))
            state.ev_keydown(engine, FakeEvent(_sym("c")))
            assert len(pushed) == 1


class TestLabelPositioning:
    def test_labels_no_overlap_all_8_directions(self):
        """Labels for all 8 directions should not overlap each other."""
        # System with connections in all 8 directions
        conns = {}
        systems = {}
        dirs = [
            ("N-Star", 0, -1), ("NE-Star", 1, -1), ("E-Star", 1, 0),
            ("SE-Star", 1, 1), ("S-Star", 0, 1), ("SW-Star", -1, 1),
            ("W-Star", -1, 0), ("NW-Star", -1, -1),
        ]
        for name, dx, dy in dirs:
            conns[name] = 30
            systems[name] = _make_system(name, 3 + dx, 3 + dy, {"Center": 30})
        center = _make_system("Center", 3, 3, conns, [_make_location()])
        systems["Center"] = center
        frontier = set()
        galaxy = SimpleNamespace(
            systems=systems, current_system="Center", home_system="Center",
            _unexplored_frontier=frontier,
            travel_cost=lambda dest: 2 if dest in frontier else 1,
        )
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        engine.CONSOLE_WIDTH = 160
        engine.CONSOLE_HEIGHT = 50

        # Capture all printed labels
        printed = []
        def mock_print(*, x, y, string, fg=(255, 255, 255)):
            printed.append((x, y, string))

        console = SimpleNamespace(
            width=160, height=50,
            rgb=__import__("numpy").zeros((160, 50), dtype=[
                ("ch", __import__("numpy").int32), ("fg", "3u1"), ("bg", "3u1")]),
        )
        console.print = mock_print
        console.draw_rect = lambda *a, **kw: None
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))  # nav focus for bright labels
        state.on_render(console, engine)

        # Find label prints (contain system names with fuel cost)
        labels = [(x, y, s) for x, y, s in printed if "(" in s and "Star" in s]
        # Check no two labels share the same row AND overlap in x range
        for i, (x1, y1, s1) in enumerate(labels):
            for x2, y2, s2 in labels[i + 1:]:
                if y1 != y2:
                    continue
                # Same row — check x ranges don't overlap
                end1 = x1 + len(s1)
                end2 = x2 + len(s2)
                overlaps = not (end1 <= x2 or end2 <= x1)
                assert not overlaps, (
                    f"Labels overlap on row {y1}: "
                    f"'{s1}' at x={x1}-{end1} vs '{s2}' at x={x2}-{end2}"
                )

    def test_long_names_dont_overflow(self):
        """Labels with very long system names should be truncated, not overflow."""
        long_name = "Wolf-Rayet Proxima Centauri"
        a = _make_system("Center", 3, 3, {long_name: 99}, [_make_location()])
        b = _make_system(long_name, 4, 3, {"Center": 99})
        frontier = set()
        galaxy = SimpleNamespace(
            systems={"Center": a, long_name: b},
            current_system="Center", home_system="Center",
            _unexplored_frontier=frontier,
            travel_cost=lambda dest: 2 if dest in frontier else 1,
        )
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        engine.CONSOLE_WIDTH = 160
        engine.CONSOLE_HEIGHT = 50

        printed = []
        def mock_print(*, x, y, string, fg=(255, 255, 255)):
            printed.append((x, y, string))

        console = SimpleNamespace(
            width=160, height=50,
            rgb=__import__("numpy").zeros((160, 50), dtype=[
                ("ch", __import__("numpy").int32), ("fg", "3u1"), ("bg", "3u1")]),
        )
        console.print = mock_print
        console.draw_rect = lambda *a, **kw: None
        state.on_render(console, engine)

        # Compass labels (contain the long system name) should not overflow
        left_w = 64
        for x, y, s in printed:
            if long_name in s or long_name[:20] in s:
                assert x + len(s) <= left_w, (
                    f"Label overflows: '{s}' at x={x} extends to {x + len(s)} (max {left_w})"
                )


class TestStarmapRender:
    def _make_console(self, w=160, h=50):
        console = SimpleNamespace(
            width=w, height=h,
            rgb=np.zeros((w, h), dtype=[("ch", np.int32),
                         ("fg", "3u1"), ("bg", "3u1")]),
        )
        console.print = lambda *, x, y, string, fg=(255, 255, 255): None
        console.draw_rect = lambda *a, **kw: None
        return console

    def test_render_locations_focus_smoke(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        engine.CONSOLE_WIDTH = 160
        engine.CONSOLE_HEIGHT = 50
        console = self._make_console()
        state.on_render(console, engine)

    def test_render_navigation_focus_smoke(self):
        galaxy = _make_graph_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        engine.CONSOLE_WIDTH = 160
        engine.CONSOLE_HEIGHT = 50
        console = self._make_console()
        state.ev_keydown(engine, FakeEvent(_sym("TAB")))
        state.on_render(console, engine)
