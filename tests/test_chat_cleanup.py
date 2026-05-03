"""Tests for the chat cleanup loop wiring."""


def test_chat_cleanup_loop_function_exists():
    """The loop function must be importable so lifespan can schedule it."""
    from web.server import _chat_cleanup_loop

    assert callable(_chat_cleanup_loop)
