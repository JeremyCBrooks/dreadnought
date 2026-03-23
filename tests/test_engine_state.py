"""Tests for Engine state-stack methods."""

import tcod.event

from engine.game_state import Engine, State


class SpyState(State):
    """Tracks on_enter / on_exit calls for verification."""

    def __init__(self, label: str = ""):
        self.label = label
        self.entered = False
        self.exited = False

    def on_enter(self, engine):
        self.entered = True

    def on_exit(self, engine):
        self.exited = True


# -- reset_to_state -----------------------------------------------------------


def test_reset_to_state_clears_stack():
    eng = Engine()
    s1, s2 = SpyState("s1"), SpyState("s2")
    eng.push_state(s1)
    eng.push_state(s2)

    new = SpyState("new")
    eng.reset_to_state(new)

    assert eng.current_state is new
    assert new.entered is True


def test_reset_to_state_calls_on_exit_for_all():
    eng = Engine()
    s1, s2, s3 = SpyState("s1"), SpyState("s2"), SpyState("s3")
    eng.push_state(s1)
    eng.push_state(s2)
    eng.push_state(s3)

    eng.reset_to_state(SpyState("fresh"))

    assert s1.exited is True
    assert s2.exited is True
    assert s3.exited is True


def test_reset_to_state_from_empty():
    eng = Engine()
    new = SpyState("new")
    eng.reset_to_state(new)
    assert eng.current_state is new
    assert new.entered is True


def test_reset_to_state_stack_has_one_entry():
    eng = Engine()
    eng.push_state(SpyState())
    eng.push_state(SpyState())
    eng.push_state(SpyState())

    eng.reset_to_state(SpyState("sole"))
    # Pop should leave stack empty
    eng.pop_state()
    assert eng.current_state is None


# -- _handle_log_scroll -------------------------------------------------------


def test_handle_log_scroll_pageup_scrolls_up():
    eng = Engine()
    eng.message_log.add_message("line1")
    eng.message_log.add_message("line2")
    state = State()
    consumed = state._handle_log_scroll(eng, tcod.event.KeySym.PAGEUP)
    assert consumed is True
    assert eng.message_log._scroll == 1


def test_handle_log_scroll_pagedown_scrolls_down():
    eng = Engine()
    eng.message_log.add_message("line1")
    eng.message_log.add_message("line2")
    state = State()
    # Scroll up first so there's room to scroll back
    state._handle_log_scroll(eng, tcod.event.KeySym.PAGEUP)
    consumed = state._handle_log_scroll(eng, tcod.event.KeySym.PAGEDOWN)
    assert consumed is True
    assert eng.message_log._scroll == 0


def test_handle_log_scroll_other_key_not_consumed():
    eng = Engine()
    state = State()
    consumed = state._handle_log_scroll(eng, tcod.event.KeySym.a)
    assert consumed is False
