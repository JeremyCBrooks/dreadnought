"""Tests for the Engine state stack."""
from engine.game_state import Engine, State


class DummyState(State):
    def __init__(self) -> None:
        self.entered = 0
        self.exited = 0

    def on_enter(self, engine):
        self.entered += 1

    def on_exit(self, engine):
        self.exited += 1


def test_push_pop_switch():
    engine = Engine()
    s1, s2 = DummyState(), DummyState()

    assert engine.current_state is None

    engine.push_state(s1)
    assert engine.current_state is s1
    assert s1.entered == 1

    # Push suspends s1 (no on_exit), activates s2
    engine.push_state(s2)
    assert engine.current_state is s2
    assert s1.exited == 0  # suspended, NOT exited
    assert s2.entered == 1

    # Pop removes s2 (on_exit called), s1 resumes (no on_enter)
    engine.pop_state()
    assert engine.current_state is s1
    assert s2.exited == 1
    assert s1.entered == 1  # not re-entered, just resumed

    # Switch replaces s1 (on_exit called) with s2
    engine.switch_state(s2)
    assert engine.current_state is s2
    assert s1.exited == 1


def test_pop_empty_stack():
    engine = Engine()
    engine.pop_state()  # should not raise


def test_message_log_exists():
    engine = Engine()
    engine.message_log.add_message("hello")
    msgs = list(engine.message_log.messages)
    assert msgs[0][0] == "hello"
