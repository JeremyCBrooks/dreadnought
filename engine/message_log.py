"""Simple scrollable message log -- no tcod dependency at import time."""

from collections import deque

type Color = tuple[int, int, int]
type Message = tuple[str, Color]

WHITE: Color = (255, 255, 255)


class MessageLog:
    """Stores recent messages and can render them into a rectangular region."""

    def __init__(self, capacity: int = 100) -> None:
        self._messages: deque[Message] = deque(maxlen=capacity)
        self._scroll: int = 0

    def add_message(self, text: str, color: Color | None = None) -> None:
        if color is None:
            color = WHITE
        self._messages.append((text, color))
        self._scroll = 0

    @property
    def messages(self) -> tuple[Message, ...]:
        return tuple(self._messages)

    def scroll(self, amount: int) -> None:
        if not self._messages:
            self._scroll = 0
            return
        self._scroll = max(0, min(self._scroll + amount, max(0, len(self._messages) - 1)))

    def render(self, console, x: int, y: int, width: int, height: int) -> None:
        """Render newest messages into the given rectangle (duck-typed console)."""
        console.draw_rect(x, y, width, height, ch=32, bg=(0, 0, 0))
        visible = list(self._messages)
        if not visible:
            return
        max_scroll = max(0, len(visible) - height)
        self._scroll = min(self._scroll, max_scroll)
        start_index = max(0, len(visible) - height - self._scroll)
        end_index = len(visible) - self._scroll
        for row, (text, color) in enumerate(visible[start_index:end_index]):
            console.print(x=x, y=y + row, string=text[:width], fg=color)
