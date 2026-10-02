"""Helm console widgets: segmented gauges and keycap hints, built as coloured text spans."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from data.colors import (
    CONSOLE_DIM,
    CONSOLE_FRAME,
    CONSOLE_LABEL,
    HP_GREEN,
    HP_RED,
    HP_YELLOW,
    KEYCAP_KEY,
    KEYCAP_LABEL,
    Color,
)

Span = tuple[str, Color]

_CELL = "■"
_HINT_GAP = "   "
_GROUP_RULE = "│"


@dataclass(frozen=True)
class Gauge:
    """A labelled bar: *value* out of *max_value*, drawn *width* cells wide."""

    label: str
    value: int
    max_value: int
    color: Color
    readout: str | None = None
    width: int = 10

    @property
    def filled(self) -> int:
        """Lit cells: none when empty, all only when full, at least one in between."""
        if self.value <= 0 or self.max_value <= 0:
            return 0
        if self.value >= self.max_value:
            return self.width
        return max(1, self.width * self.value // self.max_value)

    @property
    def text(self) -> str:
        """The readout after the bar; counts are padded so the bar never shifts."""
        if self.readout is not None:
            return self.readout
        return f"{self.value}/{self.max_value}".rjust(len(f"{self.max_value}/{self.max_value}"))


@dataclass(frozen=True)
class KeyHint:
    """A key and what it does, e.g. KeyHint("C", "Cargo")."""

    key: str
    label: str


def ratio_color(ratio: float) -> Color:
    """Return green/yellow/red for a 0-1 fill ratio."""
    if ratio > 0.5:
        return HP_GREEN
    if ratio >= 0.3:
        return HP_YELLOW
    return HP_RED


def _compact(spans: Iterable[Span]) -> list[Span]:
    return [(text, color) for text, color in spans if text]


def gauge_spans(gauge: Gauge) -> list[Span]:
    """Spans for 'FUEL ■■■■■■■■■■  8/10': a row of cells, lit in the gauge colour up to its value."""
    filled = gauge.filled
    return _compact(
        [
            (f"{gauge.label} ", CONSOLE_LABEL),
            (_CELL * filled, gauge.color),
            (_CELL * (gauge.width - filled), CONSOLE_DIM),
            (f" {gauge.text}", gauge.color),
        ]
    )


def keycap_spans(groups: Iterable[Sequence[KeyHint]]) -> list[Span]:
    """Spans for 'C Cargo   S Ship   │   Tab Locations': bright keys, dim labels, ruled groups."""
    spans: list[Span] = []
    for group in groups:
        if not group:
            continue
        if spans:
            spans.append((f"{_HINT_GAP}{_GROUP_RULE}{_HINT_GAP}", CONSOLE_FRAME))
        for i, hint in enumerate(group):
            lead = _HINT_GAP if i else ""
            spans.append((f"{lead}{hint.key}", KEYCAP_KEY))
            spans.append((f" {hint.label}", KEYCAP_LABEL))
    return spans


def spans_width(spans: Iterable[Span]) -> int:
    """Total cells the spans occupy when printed end to end."""
    return sum(len(text) for text, _ in spans)


def print_spans(console: Any, x: int, y: int, spans: Iterable[Span]) -> int:
    """Print spans end to end starting at (x, y); return the x just past the last one."""
    for text, color in spans:
        console.print(x=x, y=y, string=text, fg=color)
        x += len(text)
    return x
