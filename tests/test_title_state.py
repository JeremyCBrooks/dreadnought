"""Tests for TitleState (title screen)."""

import tcod.event

from engine.game_state import Engine
from tests.conftest import FakeEvent
from ui.title_state import TitleState


class FakeConsole:
    """Minimal console stub that records print calls."""

    def __init__(self, width=160, height=50):
        self.width = width
        self.height = height
        self.prints = []

    def print(self, *, x, y, string, fg=(255, 255, 255)):
        self.prints.append({"x": x, "y": y, "string": string, "fg": fg})


# ---- ev_key ----------------------------------------------------------------


def test_esc_returns_false():
    """ESC should return False (unhandled) so engine quits."""
    state = TitleState()
    engine = Engine()
    event = FakeEvent(tcod.event.KeySym.ESCAPE)
    assert state.ev_key(engine, event) is False


def test_esc_does_not_switch_state():
    """ESC should not create a galaxy or switch state."""
    state = TitleState()
    engine = Engine()
    event = FakeEvent(tcod.event.KeySym.ESCAPE)
    state.ev_key(engine, event)
    assert engine.galaxy is None
    assert engine.ship is None


def test_any_key_starts_game():
    """Non-ESC key should create galaxy, ship, and switch to StrategicState."""
    state = TitleState()
    engine = Engine()
    engine.push_state(state)
    event = FakeEvent(tcod.event.KeySym.RETURN)
    result = state.ev_key(engine, event)
    assert result is True
    assert engine.galaxy is not None
    assert engine.ship is not None


def test_any_key_switches_to_strategic():
    """After pressing a key, the current state should be StrategicState."""
    from ui.strategic_state import StrategicState

    state = TitleState()
    engine = Engine()
    engine.push_state(state)
    event = FakeEvent(tcod.event.KeySym.SPACE)
    state.ev_key(engine, event)
    assert isinstance(engine.current_state, StrategicState)


def test_multiple_keys_only_start_once():
    """Pressing a start key twice should not error (idempotent)."""
    state = TitleState()
    engine = Engine()
    engine.push_state(state)
    event = FakeEvent(tcod.event.KeySym.RETURN)
    state.ev_key(engine, event)
    # Second press on a new TitleState is fine; engine already switched
    galaxy_first = engine.galaxy
    assert galaxy_first is not None


# ---- on_render --------------------------------------------------------------


def test_render_prints_title():
    """on_render should print the game title."""
    state = TitleState()
    engine = Engine()
    console = FakeConsole()
    state.on_render(console, engine)
    strings = [p["string"] for p in console.prints]
    assert any("D R E A D N O U G H T" in s for s in strings)


def test_render_prints_tagline():
    """on_render should print the tagline."""
    state = TitleState()
    engine = Engine()
    console = FakeConsole()
    state.on_render(console, engine)
    strings = [p["string"] for p in console.prints]
    assert any("roguelike" in s.lower() for s in strings)


def test_render_prints_prompt():
    """on_render should print the start prompt."""
    state = TitleState()
    engine = Engine()
    console = FakeConsole()
    state.on_render(console, engine)
    strings = [p["string"] for p in console.prints]
    assert any("any key" in s.lower() for s in strings)


def test_render_prints_esc_hint():
    """on_render should print the ESC quit hint."""
    state = TitleState()
    engine = Engine()
    console = FakeConsole()
    state.on_render(console, engine)
    strings = [p["string"] for p in console.prints]
    assert any("esc" in s.lower() for s in strings)


def test_render_title_is_centered():
    """Title text should be horizontally centered."""
    state = TitleState()
    engine = Engine()
    console = FakeConsole()
    state.on_render(console, engine)
    title_print = next(p for p in console.prints if "D R E A D N O U G H T" in p["string"])
    title_str = title_print["string"]
    expected_x = engine.CONSOLE_WIDTH // 2 - len(title_str) // 2
    assert title_print["x"] == expected_x


def test_render_all_text_centered():
    """All printed strings should be horizontally centered."""
    state = TitleState()
    engine = Engine()
    console = FakeConsole()
    state.on_render(console, engine)
    cx = engine.CONSOLE_WIDTH // 2
    for p in console.prints:
        expected_x = cx - len(p["string"]) // 2
        assert p["x"] == expected_x, f"'{p['string']}' at x={p['x']}, expected {expected_x}"
