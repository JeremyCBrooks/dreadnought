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


def test_game_over_custom_title():
    """GameOverState should support a custom title."""
    state = GameOverState(victory=False, title="MISSION ABANDONED")
    assert state.title == "MISSION ABANDONED"


def test_game_over_default_title_death():
    """Default title for non-victory should be YOU DIED."""
    state = GameOverState(victory=False)
    assert state.title == "YOU DIED"


def test_game_over_default_title_victory():
    """Default title for victory should be YOU ESCAPED!."""
    state = GameOverState(victory=True)
    assert state.title == "YOU ESCAPED!"


def test_active_effects_cleared_on_game_over():
    from engine.game_state import State
    from game.suit import Suit

    engine = Engine()
    engine.active_effects = [{"type": "radiation", "dot": 1, "remaining": 5}]
    engine._saved_player = {"hp": 0}
    engine.suit = Suit("Test", {}, 0)
    engine.environment = {"vacuum": 1}

    class DummyState(State):
        pass

    engine.push_state(DummyState())

    go = GameOverState()
    engine.switch_state(go)
    go._fade_start = 0.0  # skip fade for test

    # Simulate pressing ENTER
    import tcod.event
    evt = FakeEvent(sym=tcod.event.KeySym.RETURN)
    go.ev_keydown(engine, evt)

    assert engine.active_effects == []
    assert engine._saved_player is None
    assert engine.suit is None
    assert engine.environment is None


def test_state_stack_cleared_on_game_over_restart():
    from engine.game_state import State

    engine = Engine()

    class DummyStrategic(State):
        pass

    class DummyTactical(State):
        pass

    # Simulate: Strategic pushed, Tactical pushed, then switch to GameOver
    engine.push_state(DummyStrategic())
    engine.push_state(DummyTactical())

    engine.switch_state(GameOverState())
    engine._state_stack[-1]._fade_start = 0.0  # skip fade for test

    # Stack: [DummyStrategic, GameOverState]
    assert len(engine._state_stack) == 2

    import tcod.event
    evt = FakeEvent(sym=tcod.event.KeySym.RETURN)

    # Press ENTER to restart — should clear entire stack
    engine._state_stack[-1].ev_keydown(engine, evt)

    # Stack should only have TitleState (no stale DummyStrategic)
    assert len(engine._state_stack) == 1
    from ui.title_state import TitleState
    assert isinstance(engine._state_stack[0], TitleState)
