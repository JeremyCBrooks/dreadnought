"""Tests for game over state and player reset."""
from engine.game_state import Engine
from ui.game_over_state import GameOverState, FADE_IN_DURATION


class FakeEvent:
    def __init__(self, sym=None):
        self.sym = sym


def _skip_fade(state: GameOverState) -> None:
    """Set fade start to epoch so fade is considered complete."""
    state._fade_start = 0.0


def test_game_over_ignores_non_enter_keys():
    """Non-Enter keys should not restart the game."""
    import tcod.event

    engine = Engine()
    engine._saved_player = {"hp": 0, "max_hp": 10, "defense": 0, "power": 1, "base_power": 1, "inventory": []}
    engine.area_cache = {("test", 1): {"game_map": None}}

    state = GameOverState(victory=False)
    engine._state_stack.append(state)
    _skip_fade(state)

    state.ev_keydown(engine, FakeEvent(sym=tcod.event.KeySym.SPACE))

    assert engine._saved_player is not None
    assert engine.area_cache != {}


def test_game_over_clears_saved_player():
    """After death, pressing Enter returns to title and resets state."""
    import tcod.event

    engine = Engine()
    engine._saved_player = {"hp": 0, "max_hp": 10, "defense": 0, "power": 1, "base_power": 1, "inventory": []}
    engine.area_cache = {("test", 1): {"game_map": None}}

    state = GameOverState(victory=False)
    engine._state_stack.append(state)
    _skip_fade(state)

    state.ev_keydown(engine, FakeEvent(sym=tcod.event.KeySym.RETURN))

    assert engine._saved_player is None
    assert engine.area_cache == {}


def test_victory_clears_saved_player():
    """Victory screen should also reset for a fresh start on Enter."""
    import tcod.event

    engine = Engine()
    engine._saved_player = {"hp": 5, "max_hp": 10, "defense": 0, "power": 1, "base_power": 1, "inventory": []}
    engine.area_cache = {("test", 1): {"game_map": None}}

    state = GameOverState(victory=True)
    engine._state_stack.append(state)
    _skip_fade(state)

    state.ev_keydown(engine, FakeEvent(sym=tcod.event.KeySym.RETURN))

    assert engine._saved_player is None
    assert engine.area_cache == {}


def test_game_over_stores_cause():
    """GameOverState should store the cause of death."""
    state = GameOverState(victory=False, cause="Lost to the void.")
    assert state.cause == "Lost to the void."


def test_game_over_default_cause_is_empty():
    """GameOverState with no cause should default to empty string."""
    state = GameOverState(victory=False)
    assert state.cause == ""
