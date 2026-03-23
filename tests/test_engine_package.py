"""Tests for engine package public API re-exports."""

from engine import Engine, MessageLog, State


def test_engine_reexported():
    """Engine should be importable directly from the engine package."""
    from engine.game_state import Engine as Direct

    assert Engine is Direct


def test_state_reexported():
    """State should be importable directly from the engine package."""
    from engine.game_state import State as Direct

    assert State is Direct


def test_message_log_reexported():
    """MessageLog should be importable directly from the engine package."""
    from engine.message_log import MessageLog as Direct

    assert MessageLog is Direct


def test_all_contains_public_names():
    """__all__ should list the public API."""
    import engine

    assert set(engine.__all__) == {"Engine", "State", "MessageLog"}
