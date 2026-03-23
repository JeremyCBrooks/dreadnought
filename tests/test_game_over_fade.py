"""Tests for the two-phase game over transition.

Phase 1: tactical state fades out (dims) for 1 second.
Phase 2: game over state fades in text for 1 second on black screen.
"""

import time

import numpy as np
import tcod.event

from engine.game_state import Engine
from ui.game_over_state import FADE_IN_DURATION, GameOverState
from ui.tactical_state import DEATH_FADE_DURATION


class FakeEvent:
    def __init__(self, sym=None):
        self.sym = sym


class FakeConsole:
    """Minimal console stub that records print calls and has fg/bg arrays."""

    def __init__(self, width=160, height=50):
        self.width = width
        self.height = height
        self.prints = []
        self.fg = np.full((width, height, 3), 200, dtype=np.uint8)
        self.bg = np.full((width, height, 3), 50, dtype=np.uint8)

    def print(self, *, x, y, string, fg=(255, 255, 255)):
        self.prints.append({"x": x, "y": y, "string": string, "fg": fg})


# ---- Phase 1: tactical death fade-out ----


def test_death_fade_sets_fields():
    """_handle_player_death should set death fade fields, not switch state."""
    from ui.tactical_state import TacticalState

    state = TacticalState()
    engine = Engine()
    engine._state_stack.append(state)

    before = time.time()
    state._handle_player_death(engine, "Killed.")
    after = time.time()

    assert state._death_cause == "Killed."
    assert before <= state._death_fade_start <= after
    # Should NOT have switched state yet
    assert engine.current_state is state


def test_tactical_blocks_input_while_dying():
    """During death fade, tactical should consume but ignore all input."""
    from ui.tactical_state import TacticalState

    state = TacticalState()
    engine = Engine()
    engine._state_stack.append(state)
    state._death_cause = "Test"
    state._death_fade_start = time.time()

    result = state.ev_key(engine, FakeEvent(sym=tcod.event.KeySym.RETURN))
    assert result is True
    assert engine.current_state is state


def test_tactical_needs_animation_while_dying():
    """Tactical should request animation frames during death fade."""
    from ui.tactical_state import TacticalState

    state = TacticalState()
    state._death_cause = "Test"
    state._death_fade_start = time.time()
    assert state.needs_animation is True


def test_tactical_switches_to_game_over_after_fade():
    """After death fade completes, tactical should switch to GameOverState."""
    import tcod.console

    from game.entity import Entity, Fighter
    from tests.conftest import make_arena
    from ui.tactical_state import TacticalState

    state = TacticalState()
    engine = Engine()
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(0, 10, 0, 1))
    gm.entities.append(player)
    gm.update_fov(player.x, player.y)
    engine.game_map = gm
    engine.player = player
    engine.environment = {}
    from game.suit import EVA_SUIT

    engine.suit = EVA_SUIT.copy()
    state._layout = type(
        "L",
        (),
        {
            "viewport_w": 60,
            "viewport_h": 42,
            "stats_x": 60,
            "stats_w": 20,
            "log_y": 42,
            "log_h": 8,
            "map_w": 60,
            "map_h": 42,
        },
    )()
    engine._state_stack.append(state)
    # Fade already elapsed
    state._death_cause = "Killed in action."
    state._death_fade_start = time.time() - DEATH_FADE_DURATION - 1.0

    console = tcod.console.Console(160, 50, order="F")
    state.on_render(console, engine)

    assert isinstance(engine.current_state, GameOverState)
    assert engine.current_state.cause == "Killed in action."


# ---- Phase 2: game over text fade-in ----


def test_game_over_fade_starts_on_enter():
    """on_enter should record the fade start time."""
    state = GameOverState(victory=False)
    engine = Engine()
    before = time.time()
    state.on_enter(engine)
    after = time.time()
    assert before <= state._fade_start <= after


def test_game_over_input_blocked_during_fade():
    """ev_key should ignore all input while text is fading in."""
    state = GameOverState(victory=False)
    engine = Engine()
    engine._state_stack.append(state)
    state.on_enter(engine)

    result = state.ev_key(engine, FakeEvent(sym=tcod.event.KeySym.RETURN))
    assert result is True
    assert engine.current_state is state


def test_game_over_input_accepted_after_fade():
    """After fade completes, Enter should trigger return to title."""
    state = GameOverState(victory=False)
    engine = Engine()
    engine._saved_player = {"hp": 0, "max_hp": 10, "defense": 0, "power": 1, "base_power": 1, "inventory": []}
    engine.area_cache = {("test", 1): {"game_map": None}}
    engine._state_stack.append(state)
    state._fade_start = time.time() - FADE_IN_DURATION - 1.0

    state.ev_key(engine, FakeEvent(sym=tcod.event.KeySym.RETURN))
    assert engine._saved_player is None


def test_game_over_text_fades_in():
    """Text colors should scale from dim to full brightness."""
    state = GameOverState(victory=False, cause="Test death")
    engine = Engine()
    engine._state_stack.append(state)
    state.on_enter(engine)

    # At start — text very dim
    state._fade_start = time.time()
    console = FakeConsole()
    state.on_render(console, engine)
    you_died = [p for p in console.prints if "YOU DIED" in p["string"]]
    assert len(you_died) == 1
    assert you_died[0]["fg"][0] < 30

    # After fade — full brightness
    state._fade_start = time.time() - FADE_IN_DURATION - 1.0
    console2 = FakeConsole()
    state.on_render(console2, engine)
    you_died2 = [p for p in console2.prints if "YOU DIED" in p["string"]]
    assert you_died2[0]["fg"] == (255, 0, 0)


def test_game_over_prompt_hidden_during_fade():
    """'Press Enter' should not show until text fade is complete."""
    state = GameOverState(victory=False)
    engine = Engine()
    engine._state_stack.append(state)
    state.on_enter(engine)

    state._fade_start = time.time()
    console = FakeConsole()
    state.on_render(console, engine)
    assert not [p for p in console.prints if "Press Enter" in p["string"]]

    state._fade_start = time.time() - FADE_IN_DURATION - 1.0
    console2 = FakeConsole()
    state.on_render(console2, engine)
    assert [p for p in console2.prints if "Press Enter" in p["string"]]


def test_game_over_needs_animation_during_fade():
    """Game over should request animation frames while fading in."""
    state = GameOverState(victory=False)
    engine = Engine()
    state.on_enter(engine)
    assert state.needs_animation is True

    state._fade_start = time.time() - FADE_IN_DURATION - 1.0
    assert state.needs_animation is False


def test_victory_fade_colors():
    """Victory screen should also fade in with correct final colors."""
    state = GameOverState(victory=True)
    engine = Engine()
    engine._state_stack.append(state)
    state._fade_start = time.time() - FADE_IN_DURATION - 1.0

    console = FakeConsole()
    state.on_render(console, engine)
    escaped = [p for p in console.prints if "YOU ESCAPED" in p["string"]]
    assert len(escaped) == 1
    assert escaped[0]["fg"] == (0, 255, 0)


def test_game_over_renders_on_black():
    """Game over should not render any state below — just black + text."""
    state = GameOverState(victory=False)
    engine = Engine()
    engine._state_stack.append(state)
    state._fade_start = time.time() - FADE_IN_DURATION - 1.0

    console = FakeConsole()
    # Console starts with fg=200, bg=50; game over should NOT restore those
    state.on_render(console, engine)
    # bg should remain whatever it was (black from engine clear())
    # The state does not touch fg/bg arrays, only prints text
