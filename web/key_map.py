"""Map browser KeyboardEvent.key strings to tcod.event.KeySym values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WebKeyEvent:
    """Drop-in replacement for tcod.event.KeyDown / KeyUp inside ev_key handlers."""

    sym: int
    mod: int = 0
    type: str = "keydown"


def mod_flags(*, shift: bool, ctrl: bool, alt: bool) -> int:
    """Return a tcod-compatible modifier bitmask."""
    import tcod.event

    flags = 0
    if shift:
        flags |= tcod.event.Modifier.LSHIFT
    if ctrl:
        flags |= tcod.event.Modifier.LCTRL
    if alt:
        flags |= tcod.event.Modifier.LALT
    return flags


def _build_map() -> dict[str, int]:
    import tcod.event

    K = tcod.event.KeySym
    m: dict[str, int] = {}

    # Arrows
    m["ArrowUp"] = K.UP
    m["ArrowDown"] = K.DOWN
    m["ArrowLeft"] = K.LEFT
    m["ArrowRight"] = K.RIGHT

    # Confirm / cancel
    m["Enter"] = K.RETURN
    m["Escape"] = K.ESCAPE

    # Whitespace / punctuation used in ui/keys.py
    m[" "] = K.SPACE
    m["."] = K.PERIOD
    m[","] = K.COMMA

    # Page scroll (message log)
    m["PageUp"] = K.PAGEUP
    m["PageDown"] = K.PAGEDOWN

    # Function keys
    for n in range(1, 13):
        m[f"F{n}"] = getattr(K, f"F{n}")

    # Digits
    for n in range(10):
        m[str(n)] = getattr(K, f"N{n}")

    # All lowercase and uppercase letters — tcod KeySym only exposes uppercase
    # attributes for letter keys, but the integer value is the SDL keycode for
    # the lowercase character, so both browser variants map to the same sym.
    for c in "abcdefghijklmnopqrstuvwxyz":
        sym = getattr(K, c.upper())
        m[c] = sym
        m[c.upper()] = sym

    # Numpad — browser sends "Numpad0" … "Numpad9" for numlock-on numeric keys
    numpad = {
        "Numpad0": K.KP_0,
        "Numpad1": K.KP_1,
        "Numpad2": K.KP_2,
        "Numpad3": K.KP_3,
        "Numpad4": K.KP_4,
        "Numpad5": K.KP_5,
        "Numpad6": K.KP_6,
        "Numpad7": K.KP_7,
        "Numpad8": K.KP_8,
        "Numpad9": K.KP_9,
        "NumpadEnter": K.KP_ENTER,
        "NumpadDecimal": K.KP_PERIOD,
    }
    m.update(numpad)

    # Tab / Delete / Backspace
    m["Tab"] = K.TAB
    m["Delete"] = K.DELETE
    m["Backspace"] = K.BACKSPACE
    m["Home"] = K.HOME
    m["End"] = K.END
    m["Insert"] = K.INSERT

    return m


BROWSER_TO_KEYSYM: dict[str, int] = _build_map()
