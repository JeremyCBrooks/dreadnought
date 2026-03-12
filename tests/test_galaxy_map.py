"""Tests for the galaxy map overlay state."""
from types import SimpleNamespace

from engine.game_state import Engine
from engine.message_log import MessageLog
from ui.galaxy_map_state import GalaxyMapState


def _sym(name):
    import tcod.event
    return getattr(tcod.event.KeySym, name)


class FakeEvent:
    def __init__(self, sym, mod=0):
        self.sym = sym
        self.mod = mod


def _make_system(name, gx, gy, connections, depth=0):
    return SimpleNamespace(
        name=name, gx=gx, gy=gy, connections=connections,
        depth=depth, star_type="yellow_dwarf", locations=[],
    )


def _make_engine():
    engine = Engine()
    engine.message_log = MessageLog()
    return engine


def _make_galaxy():
    """3-system graph: Home(0,0) -- B(2,0) -- C(4,1)"""
    home = _make_system("Home", 0, 0, {"B": 30}, depth=0)
    b = _make_system("B", 2, 0, {"Home": 30, "C": 40}, depth=1)
    c = _make_system("C", 4, 1, {"B": 40}, depth=2)
    return SimpleNamespace(
        systems={"Home": home, "B": b, "C": c},
        current_system="Home",
        home_system="Home",
    )


class TestGalaxyMapState:
    def test_escape_pops_state(self):
        galaxy = _make_galaxy()
        state = GalaxyMapState(galaxy)
        engine = _make_engine()
        engine.push_state(state)
        state.ev_keydown(engine, FakeEvent(_sym("ESCAPE")))
        assert engine.current_state is None

    def test_camera_starts_on_current_system(self):
        galaxy = _make_galaxy()
        state = GalaxyMapState(galaxy)
        assert state.camera_gx == 0
        assert state.camera_gy == 0

    def test_camera_scrolls_with_arrow_keys(self):
        galaxy = _make_galaxy()
        state = GalaxyMapState(galaxy)
        engine = _make_engine()
        engine.push_state(state)
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert state.camera_gx == 1
        state.ev_keydown(engine, FakeEvent(_sym("DOWN")))
        assert state.camera_gy == 1
        state.ev_keydown(engine, FakeEvent(_sym("LEFT")))
        assert state.camera_gx == 0
        state.ev_keydown(engine, FakeEvent(_sym("UP")))
        assert state.camera_gy == 0

    def test_center_key_recenters_on_current(self):
        galaxy = _make_galaxy()
        state = GalaxyMapState(galaxy)
        engine = _make_engine()
        engine.push_state(state)
        # Scroll away
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert state.camera_gx == 2
        # Press 'c' to recenter
        state.ev_keydown(engine, FakeEvent(_sym("c")))
        current = galaxy.systems[galaxy.current_system]
        assert state.camera_gx == current.gx
        assert state.camera_gy == current.gy

    def test_render_smoke(self):
        """on_render should not crash."""
        galaxy = _make_galaxy()
        state = GalaxyMapState(galaxy)
        engine = _make_engine()
        engine.push_state(state)
        import tcod.console
        console = tcod.console.Console(engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT, order="F")
        state.on_render(console, engine)

    def test_home_key_recenters_on_home(self):
        galaxy = _make_galaxy()
        galaxy.current_system = "C"
        state = GalaxyMapState(galaxy)
        engine = _make_engine()
        engine.push_state(state)
        # Camera starts on current (C at 4,1)
        assert state.camera_gx == 4
        # Press Shift+H to jump to home
        import tcod.event
        state.ev_keydown(engine, FakeEvent(_sym("h"), mod=tcod.event.Modifier.SHIFT))
        home = galaxy.systems[galaxy.home_system]
        assert state.camera_gx == home.gx
        assert state.camera_gy == home.gy
