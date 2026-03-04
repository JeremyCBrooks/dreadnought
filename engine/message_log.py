"""Simple scrollable message log -- no tcod dependency at import time."""
from __future__ import annotations

from collections import deque
from typing import Deque, Iterable, Tuple

Color = Tuple[int, int, int]
Message = Tuple[str, Color]

WHITE: Color = (255, 255, 255)


class MessageLog:
    """Stores recent messages and can render them into a rectangular region."""

    def __init__(self, capacity: int = 100) -> None:
        self._messages: Deque[Message] = deque(maxlen=capacity)
        self._scroll: int = 0

    def add_message(self, text: str, color: Color | None = None) -> None:
        if color is None:
            color = WHITE
        self._messages.append((text, color))
        self._scroll = 0

    @property
    def messages(self) -> Iterable[Message]:
        return tuple(self._messages)

    def scroll(self, amount: int) -> None:
        if not self._messages:
            self._scroll = 0
            return
        self._scroll = max(
            0, min(self._scroll + amount, max(0, len(self._messages) - 1))
        )

    def render(self, console, x: int, y: int, width: int, height: int) -> None:
        """Render newest messages into the given rectangle (duck-typed console)."""
        console.draw_rect(x, y, width, height, ch=32, bg=(0, 0, 0))
        visible = list(self._messages)
        if not visible:
            return
        start_index = max(0, len(visible) - height - self._scroll)
        end_index = max(0, len(visible) - self._scroll)
        lines = visible[start_index:end_index]
        row = 0
        for text, color in lines[-height:]:
            console.print(x=x, y=y + row, string=text[:width], fg=color)
            row += 1
