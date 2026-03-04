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
