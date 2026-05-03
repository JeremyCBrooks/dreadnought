"""Shared input key maps used across all UI states."""

from functools import cache


@cache
def move_keys() -> dict[int, tuple[int, int]]:
    """Lazy-build the movement key map. Maps KeySym -> (dx, dy)."""
    import tcod.event

    K = tcod.event.KeySym
    return {
        K.UP: (0, -1),
        K.DOWN: (0, 1),
        K.LEFT: (-1, 0),
        K.RIGHT: (1, 0),
        K.KP_1: (-1, 1),
        K.KP_2: (0, 1),
        K.KP_3: (1, 1),
        K.KP_4: (-1, 0),
        K.KP_6: (1, 0),
        K.KP_7: (-1, -1),
        K.KP_8: (0, -1),
        K.KP_9: (1, -1),
        K.H: (-1, 0),
        K.J: (0, 1),
        K.K: (0, -1),
        K.L: (1, 0),
        K.Y: (-1, -1),
        K.U: (1, -1),
        K.B: (-1, 1),
        K.N: (1, 1),
    }


@cache
def confirm_keys() -> set[int]:
    """Keys that mean 'confirm / accept'."""
    import tcod.event

    K = tcod.event.KeySym
    return {K.RETURN, K.KP_ENTER}


@cache
def cancel_keys() -> set[int]:
    """Keys that mean 'cancel / go back'."""
    import tcod.event

    K = tcod.event.KeySym
    return {K.ESCAPE}


def is_move_key(sym: int) -> bool:
    """Return True if *sym* is a directional / movement key."""
    return sym in move_keys()


@cache
def action_keys() -> dict[str, tuple[set[int], str, str]]:
    """Action name -> (key_set, display_label, verb)."""
    import tcod.event

    K = tcod.event.KeySym
    return {
        "look": ({K.X}, "x", "look"),
        "fire": ({K.F}, "f", "fire"),
        "inventory": ({K.I}, "i", "inventory"),
        "scan": ({K.S}, "s", "scan"),
        "interact": ({K.E}, "e", "interact"),
        "get": ({K.G, K.COMMA}, "g", "get"),
        "wait": ({K.PERIOD, K.KP_5}, ".", "wait"),
        "quit": ({K.Q}, "Q", "quit"),
        "cargo": ({K.C}, "c", "cargo"),
    }


def is_action(name: str, sym: int) -> bool:
    """Return True if sym matches the named action."""
    return sym in action_keys()[name][0]
