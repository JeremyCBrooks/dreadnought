"""Production code must only reference portable tcod.event.KeySym attrs.

tcod.event.KeySym exposes BOTH lowercase (K.h) and uppercase (K.H) letter
attributes on most builds — they alias the same SDL keycode. But some builds
(notably the Linux wheel deployed to Fly.io) expose only the uppercase
variants; lowercase access raises AttributeError, crashing the WebSocket
session as soon as the first key event triggers ui.keys.move_keys().

Regression guard for the 2026-05-03 deploy crash.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PROD_DIRS = ("ui", "engine")
_OFFENDER_RE = re.compile(r"\b(?:K|KeySym)\.[a-z]\b")


def _scan(py: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("#", 1)[0]
        for m in _OFFENDER_RE.finditer(code):
            hits.append((lineno, m.group(0)))
    return hits


@pytest.mark.parametrize("prod_dir", _PROD_DIRS)
def test_no_lowercase_keysym_letter_attrs(prod_dir: str) -> None:
    offenders: list[str] = []
    for py in (_PROJECT_ROOT / prod_dir).rglob("*.py"):
        for lineno, snippet in _scan(py):
            offenders.append(f"  {py.relative_to(_PROJECT_ROOT)}:{lineno}: {snippet}")
    assert not offenders, (
        "tcod.event.KeySym lowercase letter attrs are not portable across tcod "
        "wheels (Fly's Linux wheel exposes only K.A..K.Z). Use uppercase: "
        "K.h and K.H alias the same SDL keycode.\n" + "\n".join(offenders)
    )
