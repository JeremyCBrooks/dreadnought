"""Tests for the [S] Explore Ship keybinding in StrategicState."""

from types import SimpleNamespace

from game.entity import Entity, Fighter
from game.ship import Ship
from tests.conftest import FakeEvent, MockEngine, make_arena
from ui.strategic_state import StrategicState


def _sym(name):
    import tcod.event

    return getattr(tcod.event.KeySym, name)


def _make_galaxy():
    """Build a minimal galaxy with one system."""
    system = SimpleNamespace(
        name="TestSystem",
        gx=0,
        gy=0,
        locations=[],
        connections={},
        depth=0,
        star_type="yellow_dwarf",
    )
    galaxy = SimpleNamespace(
        systems={"TestSystem": system},
        current_system="TestSystem",
        home_system="TestSystem",
        arrive_at=lambda name: None,
        _unexplored_frontier=set(),
        travel_cost=lambda dest: 1,
        dreadnought_system=None,
    )
    return galaxy


def _make_engine(galaxy):
    gm = make_arena()
    player = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.ship = Ship()
    return engine


class TestExploreShipKeybinding:
    def test_s_key_pushes_explore_ship_state(self):
        """Pressing 's' should push TacticalState(explore_ship=True) onto the stack."""
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        pushed = []
        engine.push_state = lambda s: pushed.append(s)

        result = state.ev_key(engine, FakeEvent(_sym("s")))

        assert result is True
        assert len(pushed) == 1
        from ui.tactical_state import TacticalState

        assert isinstance(pushed[0], TacticalState)
        assert pushed[0].explore_ship is True

    def test_capital_s_key_pushes_explore_ship_state(self):
        """Pressing 'S' (capital) should also push TacticalState(explore_ship=True)."""
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        pushed = []
        engine.push_state = lambda s: pushed.append(s)

        result = state.ev_key(engine, FakeEvent(_sym("S")))

        assert result is True
        assert len(pushed) == 1
        from ui.tactical_state import TacticalState

        assert isinstance(pushed[0], TacticalState)
        assert pushed[0].explore_ship is True

    def test_s_key_explore_ship_not_mission(self):
        """TacticalState pushed by [S] must have explore_ship=True, not a location."""
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        pushed = []
        engine.push_state = lambda s: pushed.append(s)

        state.ev_key(engine, FakeEvent(_sym("s")))

        from ui.tactical_state import TacticalState

        ts = pushed[0]
        assert isinstance(ts, TacticalState)
        assert ts.explore_ship is True
        assert ts.location is None


class TestExploreShipHUD:
    def _render_collecting(self, state, engine):
        """Render strategic state and collect all printed strings."""
        import numpy as np

        engine.CONSOLE_WIDTH = 160
        engine.CONSOLE_HEIGHT = 50
        printed = []
        console = SimpleNamespace(
            width=160,
            height=50,
            rgb=np.zeros((160, 50), dtype=[("ch", np.int32), ("fg", "3u1"), ("bg", "3u1")]),
        )
        console.print = lambda *, x, y, string, fg=(255, 255, 255): printed.append(string)
        console.draw_rect = lambda *a, **kw: None
        state.on_render(console, engine)
        return printed

    def test_hud_locations_focus_contains_explore_ship(self):
        """Controls line in LOCATIONS focus should contain '[S] Explore Ship'."""
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        assert state.focus == "locations"
        engine = _make_engine(galaxy)

        printed = self._render_collecting(state, engine)

        ctrl_lines = [s for s in printed if "[S]" in s or "Explore Ship" in s]
        assert ctrl_lines, "HUD controls should contain '[S]' or 'Explore Ship'"
        assert any("[S]" in s and "Explore Ship" in s for s in ctrl_lines), (
            "HUD should contain '[S] Explore Ship' in locations focus"
        )

    def test_hud_navigation_focus_contains_explore_ship(self):
        """Controls line in NAVIGATION focus should contain '[S] Explore Ship'."""
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        engine = _make_engine(galaxy)
        # Switch to navigation focus
        state.focus = "navigation"

        printed = self._render_collecting(state, engine)

        ctrl_lines = [s for s in printed if "[S]" in s or "Explore Ship" in s]
        assert ctrl_lines, "HUD controls should contain '[S]' or 'Explore Ship'"
        assert any("[S]" in s and "Explore Ship" in s for s in ctrl_lines), (
            "HUD should contain '[S] Explore Ship' in navigation focus"
        )
