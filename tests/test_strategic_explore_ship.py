"""Tests for the [S] Explore Ship keybinding in StrategicState."""

from types import SimpleNamespace

from game.entity import Entity, Fighter
from game.ship import Ship
from tests.conftest import FakeEvent, MockEngine, make_arena, render_collecting, row_text
from ui.strategic_state import StrategicState, helm_layout


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
        arrive_at=lambda name, **_: None,
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
    def _keys_row(self, focus):
        galaxy = _make_galaxy()
        state = StrategicState(galaxy)
        state.focus = focus
        printed = render_collecting(state, _make_engine(galaxy))
        return row_text(printed, helm_layout(160, 50).keys_y)

    def test_hud_locations_focus_contains_explore_ship(self):
        """Key hints in LOCATIONS focus should offer 'S Ship'."""
        assert "S Ship" in self._keys_row("locations")

    def test_hud_navigation_focus_contains_explore_ship(self):
        """Key hints in NAVIGATION focus should offer 'S Ship'."""
        assert "S Ship" in self._keys_row("navigation")
