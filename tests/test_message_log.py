"""Tests for the MessageLog behaviour."""

from engine.message_log import MessageLog


class DummyConsole:
    def __init__(self) -> None:
        self.draw_calls: list = []
        self.print_calls: list = []

    def draw_rect(self, x, y, width, height, ch, bg):
        self.draw_calls.append((x, y, width, height, ch, bg))

    def print(self, x, y, string, fg):
        self.print_calls.append((x, y, string, fg))


def test_add_and_capacity():
    log = MessageLog(capacity=3)
    log.add_message("one")
    log.add_message("two")
    log.add_message("three")
    assert [m[0] for m in log.messages] == ["one", "two", "three"]

    log.add_message("four")
    assert [m[0] for m in log.messages] == ["two", "three", "four"]


def test_scroll_bounds():
    log = MessageLog(capacity=5)
    for i in range(5):
        log.add_message(f"m{i}")
    log.scroll(100)
    log.scroll(-200)


def test_render_latest():
    log = MessageLog(capacity=10)
    for i in range(5):
        log.add_message(f"msg {i}", (255, 255, 0))

    con = DummyConsole()
    log.render(con, x=0, y=0, width=20, height=3)

    assert con.draw_calls
    texts = [c[2] for c in con.print_calls]
    assert "msg 2" in texts[-3]
    assert "msg 3" in texts[-2]
    assert "msg 4" in texts[-1]


def test_default_color_is_white():
    log = MessageLog()
    log.add_message("hello")
    assert log.messages[0] == ("hello", (255, 255, 255))


def test_render_empty_log():
    """Rendering with no messages should clear the rect and print nothing."""
    log = MessageLog()
    con = DummyConsole()
    log.render(con, x=0, y=0, width=20, height=3)
    assert len(con.draw_calls) == 1
    assert len(con.print_calls) == 0


def test_scroll_empty_log():
    log = MessageLog()
    log.scroll(5)
    assert log._scroll == 0


def test_scroll_affects_render():
    """Scrolling up should show older messages."""
    log = MessageLog(capacity=10)
    for i in range(6):
        log.add_message(f"m{i}")

    # No scroll: should show m3, m4, m5 (last 3)
    con = DummyConsole()
    log.render(con, x=0, y=0, width=20, height=3)
    texts = [c[2] for c in con.print_calls]
    assert texts == ["m3", "m4", "m5"]

    # Scroll up by 2: should show m1, m2, m3
    log.scroll(2)
    con = DummyConsole()
    log.render(con, x=0, y=0, width=20, height=3)
    texts = [c[2] for c in con.print_calls]
    assert texts == ["m1", "m2", "m3"]


def test_scroll_fully_up_shows_full_page():
    """Scrolling to the top should still show a full page of messages."""
    log = MessageLog(capacity=10)
    for i in range(6):
        log.add_message(f"m{i}")

    log.scroll(100)  # scroll way past the top
    con = DummyConsole()
    log.render(con, x=0, y=0, width=20, height=3)
    texts = [c[2] for c in con.print_calls]
    # Should show the 3 oldest: m0, m1, m2
    assert texts == ["m0", "m1", "m2"]


def test_add_message_resets_scroll():
    log = MessageLog(capacity=10)
    for i in range(5):
        log.add_message(f"m{i}")
    log.scroll(3)
    assert log._scroll != 0
    log.add_message("new")
    assert log._scroll == 0


def test_render_normalizes_scroll():
    """After render, _scroll should not exceed the max useful scroll for the viewport.

    Without normalization, over-scrolling would require extra scroll-downs
    to "unstick" from the top.
    """
    log = MessageLog(capacity=10)
    for i in range(6):
        log.add_message(f"m{i}")

    # max useful scroll = 6 - 3 = 3, but scroll() allows up to len-1 = 5
    log.scroll(100)

    con = DummyConsole()
    log.render(con, x=0, y=0, width=20, height=3)

    # After render, _scroll should be clamped to max_scroll (3), not 5
    assert log._scroll == 3

    # Now scrolling down by 1 should immediately change the view
    log.scroll(-1)
    con = DummyConsole()
    log.render(con, x=0, y=0, width=20, height=3)
    texts = [c[2] for c in con.print_calls]
    assert texts == ["m1", "m2", "m3"]


def test_fewer_messages_than_height():
    """When messages fit entirely in the viewport, scrolling should have no effect."""
    log = MessageLog(capacity=10)
    log.add_message("only one")

    log.scroll(5)
    con = DummyConsole()
    log.render(con, x=0, y=0, width=20, height=3)
    texts = [c[2] for c in con.print_calls]
    assert texts == ["only one"]
    assert log._scroll == 0
