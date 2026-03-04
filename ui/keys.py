"""Shared input key maps used across all UI states."""
from __future__ import annotations

from typing import Dict, Optional, Set, Tuple

_MOVE_KEYS: Optional[Dict] = None
_CONFIRM_KEYS: Optional[Set] = None
_CANCEL_KEYS: Optional[Set] = None


def move_keys() -> Dict:
    """Lazy-build the movement key map. Maps KeySym -> (dx, dy)."""
    global _MOVE_KEYS
    if _MOVE_KEYS is not None:
        return _MOVE_KEYS
    import tcod.event
    K = tcod.event.KeySym
    _MOVE_KEYS = {
        K.UP: (0, -1), K.DOWN: (0, 1), K.LEFT: (-1, 0), K.RIGHT: (1, 0),
        K.KP_1: (-1, 1), K.KP_2: (0, 1), K.KP_3: (1, 1),
        K.KP_4: (-1, 0), K.KP_6: (1, 0),
        K.KP_7: (-1, -1), K.KP_8: (0, -1), K.KP_9: (1, -1),
        K.h: (-1, 0), K.j: (0, 1), K.k: (0, -1), K.l: (1, 0),
        K.y: (-1, -1), K.u: (1, -1), K.b: (-1, 1), K.n: (1, 1),
    }
    return _MOVE_KEYS


def confirm_keys() -> Set:
    """Keys that mean 'confirm / accept'."""
    global _CONFIRM_KEYS
    if _CONFIRM_KEYS is not None:
        return _CONFIRM_KEYS
    import tcod.event
    K = tcod.event.KeySym
    _CONFIRM_KEYS = {K.RETURN, K.KP_ENTER}
    return _CONFIRM_KEYS


def cancel_keys() -> Set:
    """Keys that mean 'cancel / go back'."""
    global _CANCEL_KEYS
    if _CANCEL_KEYS is not None:
        return _CANCEL_KEYS
    import tcod.event
    K = tcod.event.KeySym
    _CANCEL_KEYS = {K.ESCAPE}
    return _CANCEL_KEYS


def is_move_key(sym: int) -> bool:
    """Return True if *sym* is a directional / movement key."""
    return sym in move_keys()


_ACTION_KEYS: Optional[Dict[str, Tuple]] = None


def action_keys() -> Dict[str, Tuple]:
    """Action name -> (key_set, display_label, verb)."""
    global _ACTION_KEYS
    if _ACTION_KEYS is not None:
        return _ACTION_KEYS
    import tcod.event
    K = tcod.event.KeySym
    _ACTION_KEYS = {
        "look":      ({K.x},              "x", "look"),
        "fire":      ({K.f},              "f", "fire"),
        "inventory": ({K.i},              "i", "inventory"),
        "scan":      ({K.s},              "s", "scan"),
        "interact":  ({K.e},              "e", "interact"),
        "get":       ({K.g, K.COMMA},     "g", "get"),
        "wait":      ({K.PERIOD, K.KP_5}, ".", "wait"),
        "quit":      ({K.Q},              "Q", "quit"),
    }
    return _ACTION_KEYS


def is_action(name: str, sym: int) -> bool:
    """Return True if sym matches the named action."""
    return sym in action_keys()[name][0]
