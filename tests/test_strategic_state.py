"""Tests for the strategic (galaxy navigation) state."""

from types import SimpleNamespace

from data.star_types import STAR_TYPES
from game.entity import Entity, Fighter
from game.ship import Ship
from tests.conftest import FakeEvent, MockEngine, make_arena, render_collecting, row_text
from ui.strategic_state import StrategicState, helm_layout

_LAYOUT = helm_layout(160, 50)
_STAR_NAME = STAR_TYPES["yellow_dwarf"].name


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
        arrive_at=lambda name, **_: None,
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
            arrive_at=lambda name, **_: None,
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
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 7
        engine.ship.max_fuel = 10
        printed = render_collecting(StrategicState(galaxy), engine)
        assert "FUEL ■■■■■■■■■■  7/10" in row_text(printed, _LAYOUT.gauge_y)
        lit = sum(s.count("■") for _, _, s, fg in printed if fg == (0, 255, 0))
        assert lit == 7 + engine.ship.hull


def _fg_of(printed, text):
    """Colour of the span whose text (ignoring padding) is *text*."""
    matches = [fg for _, _, s, fg in printed if s.strip() == text]
    assert matches, f"{text!r} not rendered"
    return matches[0]


class TestStrategicRender:
    def _render_collecting(self, engine, galaxy=None, focus="locations"):
        """Render and return list of (x, y, string, fg) tuples."""
        if galaxy is None:
            galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        state.focus = focus
        return render_collecting(state, engine)

    def test_on_render_smoke(self):
        galaxy = _make_galaxy()
        self._render_collecting(_make_strategic_engine(galaxy), galaxy)

    def test_fuel_color_uses_ratio_not_absolute(self):
        """Fuel at 6/200 (3%) should be red, not green."""
        galaxy = _make_galaxy()
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 6
        engine.ship.max_fuel = 200
        printed = self._render_collecting(engine, galaxy)
        assert _fg_of(printed, "6/200") == (255, 0, 0)

    def test_fuel_color_green_when_above_half(self):
        """Fuel at 150/200 (75%) should be green."""
        galaxy = _make_galaxy()
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 150
        engine.ship.max_fuel = 200
        printed = self._render_collecting(engine, galaxy)
        assert _fg_of(printed, "150/200") == (0, 255, 0)

    def test_fuel_color_yellow_when_between_30_and_50(self):
        """Fuel at 8/20 (40%) should be yellow."""
        galaxy = _make_galaxy()
        engine = _make_strategic_engine(galaxy)
        engine.ship.fuel = 8
        engine.ship.max_fuel = 20
        printed = self._render_collecting(engine, galaxy)
        assert _fg_of(printed, "8/20") == (255, 255, 0)

    def test_hud_renders_without_ship(self):
        """HUD should not crash, and shows no gauges, when engine.ship is None."""
        galaxy = _make_galaxy()
        engine = _make_strategic_engine(galaxy)
        engine.ship = None
        printed = self._render_collecting(engine, galaxy)
        assert "FUEL" not in row_text(printed, _LAYOUT.gauge_y)

    def test_nav_hud_locked_when_dreadnought_spawned(self):
        """NAV should show LOCKED when nav units are maxed and dreadnought exists."""
        galaxy = _make_galaxy()
        galaxy.dreadnought_system = "Dreadnought"
        engine = _make_strategic_engine(galaxy)
        engine.ship.nav_units = engine.ship.max_nav_units
        printed = self._render_collecting(engine, galaxy)
        assert "NAV ■■■■■■ LOCKED" in row_text(printed, _LAYOUT.gauge_y)

    def test_nav_hud_count_when_not_maxed(self):
        """NAV should show count when nav units are not maxed."""
        galaxy = _make_galaxy()
        engine = _make_strategic_engine(galaxy)
        engine.ship.nav_units = 3
        printed = self._render_collecting(engine, galaxy)
        assert "NAV ■■■■■■ 3/6" in row_text(printed, _LAYOUT.gauge_y)

    def test_gauges_sit_side_by_side_on_the_dash(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        row = row_text(printed, _LAYOUT.gauge_y)
        assert 0 <= row.index("FUEL") < row.index("HULL") < row.index("NAV")

    def test_nothing_is_printed_over_the_starfield(self):
        """The window is for stars: no gauge, key hint or label may land inside it."""
        galaxy = _make_galaxy(connections={"OtherSystem": 10})
        galaxy.systems["OtherSystem"] = SimpleNamespace(
            name="OtherSystem", gx=1, gy=0, locations=[], connections={}, depth=1, star_type="red_dwarf"
        )
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        over_stars = [(x, y, s) for x, y, s, _ in printed if y < _LAYOUT.viewport_h and x + len(s) > _LAYOUT.viewport_x]
        assert not over_stars, f"printed over the starfield: {over_stars}"

    def test_starfield_fills_the_window_above_the_sill(self):
        from unittest.mock import patch

        galaxy = _make_galaxy()
        with patch("ui.viewport_renderer.render_viewport") as render_viewport:
            self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        _, vp_x, vp_y, vp_w, vp_h = render_viewport.call_args.args[:5]
        assert (vp_x, vp_y, vp_w, vp_h) == (64, 0, 96, _LAYOUT.sill_y)

    def test_sill_runs_under_console_and_window(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        sill = row_text(printed, _LAYOUT.sill_y)
        assert sill[: _LAYOUT.strut_x] == "─" * _LAYOUT.strut_x
        assert sill[_LAYOUT.strut_x] == "┴"
        assert sill.endswith("──")

    def test_instruments_are_set_into_the_sill_under_the_window(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        sill = row_text(printed, _LAYOUT.sill_y)
        assert _LAYOUT.gauge_y == _LAYOUT.sill_y
        assert sill.index("FUEL") > _LAYOUT.strut_x
        assert "┴── FUEL " in sill
        assert "/10 ── HULL " in sill

    def test_blank_row_separates_key_hints_from_message_log(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        assert _LAYOUT.keys_y == _LAYOUT.sill_y + 1
        assert _LAYOUT.log_y == _LAYOUT.keys_y + 2
        assert not row_text(printed, _LAYOUT.keys_y + 1).strip()

    def test_strut_divides_console_from_window(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        for y in range(_LAYOUT.sill_y):
            assert row_text(printed, y)[_LAYOUT.strut_x] == "│", f"strut missing on row {y}"

    def test_key_hints_for_locations_focus(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        keys = row_text(printed, _LAYOUT.keys_y)
        for hint in ("C Cargo", "S Ship", "M Galaxy", "Tab Star Map", "↑↓ Select", "Enter Dock"):
            assert hint in keys
        assert "Navigate" not in keys

    def test_key_hints_for_navigation_focus(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy, focus="navigation")
        keys = row_text(printed, _LAYOUT.keys_y)
        for hint in ("C Cargo", "S Ship", "M Galaxy", "Tab Locations", "Arrows Navigate"):
            assert hint in keys
        assert "Dock" not in keys

    def test_key_hints_have_no_brackets(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        keys = row_text(printed, _LAYOUT.keys_y)
        assert "[" not in keys and "]" not in keys

    def test_quit_hint_stands_alone_at_the_right_edge(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        keys = row_text(printed, _LAYOUT.keys_y)
        assert keys.rstrip().endswith("Esc Quit")
        assert len(keys.rstrip()) == 160 - 2
        assert keys[: keys.index("Esc Quit")].endswith(" " * 10)

    def test_focus_marker_sits_beside_the_active_section(self):
        galaxy = _make_galaxy()
        for focus, active, idle in (("locations", "LOCATIONS", "STAR MAP"), ("navigation", "STAR MAP", "LOCATIONS")):
            printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy, focus=focus)
            rows = {s: y for _, y, s, _ in printed if s in (active, idle)}
            assert row_text(printed, rows[active]).startswith("▌"), f"{active} should be marked"
            assert not row_text(printed, rows[idle]).startswith("▌"), f"{idle} should not be marked"

    def test_section_headers_drop_their_colons(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        assert not [s for _, _, s, _ in printed if s.endswith(":")]

    def test_header_rule_is_a_thin_line(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        assert not [s for _, _, s, _ in printed if "=" in s]
        assert row_text(printed, 2)[2:62] == "─" * 60

    def test_header_names_system_and_star_type(self):
        galaxy = _make_galaxy()
        printed = self._render_collecting(_make_strategic_engine(galaxy), galaxy)
        assert row_text(printed, 1)[: _LAYOUT.strut_x].strip() == f"TestSystem · {_STAR_NAME} · home"


class TestLocationList:
    def _galaxy(self):
        galaxy = _make_galaxy(num_locations=0)
        galaxy.systems["TestSystem"].locations.extend(
            [
                SimpleNamespace(name="South Bulwark", loc_type="colony", visited=False),
                SimpleNamespace(name="Debris", loc_type="asteroid", visited=True),
            ]
        )
        return galaxy

    def _render(self, focus="locations"):
        galaxy = self._galaxy()
        state = StrategicState(galaxy)
        state.focus = focus
        printed = render_collecting(state, _make_strategic_engine(galaxy))
        ys = sorted(y for _, y, s, _ in printed if s.strip() in ("South Bulwark", "Debris"))
        return printed, [row_text(printed, y)[: _LAYOUT.strut_x] for y in ys]

    def test_rows_read_name_type_status(self):
        _, (first, second) = self._render()
        assert first.split() == ["►", "South", "Bulwark", "colony", "unvisited"]
        assert second.split() == ["Debris", "asteroid", "visited"]

    def test_columns_line_up(self):
        _, (first, second) = self._render()
        assert first.index("South Bulwark") == second.index("Debris")
        assert first.index("colony") == second.index("asteroid")
        assert first.index("unvisited") == second.index("visited")

    def test_unvisited_status_is_brighter_than_visited(self):
        printed, _ = self._render()
        assert sum(_fg_of(printed, "unvisited")) > sum(_fg_of(printed, "visited"))

    def test_selected_name_is_brightest(self):
        printed, _ = self._render()
        assert _fg_of(printed, "South Bulwark") == (255, 255, 255)
        assert sum(_fg_of(printed, "Debris")) < 3 * 255

    def test_list_dims_when_star_map_has_focus(self):
        printed, _ = self._render(focus="navigation")
        assert _fg_of(printed, "South Bulwark") != (255, 255, 255)

    def test_long_names_are_truncated_inside_the_console(self):
        galaxy = self._galaxy()
        galaxy.systems["TestSystem"].locations[0].name = "X" * 90
        printed = render_collecting(StrategicState(galaxy), _make_strategic_engine(galaxy))
        row_y = next(y for _, y, s, _ in printed if "XXX" in s)
        row = row_text(printed, row_y)[: _LAYOUT.strut_x]
        assert "XXX... " in row
        assert row.split()[-2:] == ["colony", "unvisited"]


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
