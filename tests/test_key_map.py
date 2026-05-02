"""Tests for web/key_map.py."""

import pytest


def test_arrow_keys_mapped():
    from web.key_map import BROWSER_TO_KEYSYM
    import tcod.event

    K = tcod.event.KeySym
    assert BROWSER_TO_KEYSYM["ArrowUp"] == K.UP
    assert BROWSER_TO_KEYSYM["ArrowDown"] == K.DOWN
    assert BROWSER_TO_KEYSYM["ArrowLeft"] == K.LEFT
    assert BROWSER_TO_KEYSYM["ArrowRight"] == K.RIGHT


def test_confirm_cancel_keys_mapped():
    from web.key_map import BROWSER_TO_KEYSYM
    import tcod.event

    K = tcod.event.KeySym
    assert BROWSER_TO_KEYSYM["Enter"] == K.RETURN
    assert BROWSER_TO_KEYSYM["Escape"] == K.ESCAPE


def test_space_and_period_mapped():
    from web.key_map import BROWSER_TO_KEYSYM
    import tcod.event

    K = tcod.event.KeySym
    assert BROWSER_TO_KEYSYM[" "] == K.SPACE
    assert BROWSER_TO_KEYSYM["."] == K.PERIOD
    assert BROWSER_TO_KEYSYM[","] == K.COMMA


def test_action_keys_mapped():
    from web.key_map import BROWSER_TO_KEYSYM
    import tcod.event

    K = tcod.event.KeySym
    # All keys from ui/keys.py action_keys()
    assert BROWSER_TO_KEYSYM["x"] == K.x
    assert BROWSER_TO_KEYSYM["f"] == K.f
    assert BROWSER_TO_KEYSYM["i"] == K.i
    assert BROWSER_TO_KEYSYM["s"] == K.s
    assert BROWSER_TO_KEYSYM["e"] == K.e
    assert BROWSER_TO_KEYSYM["g"] == K.g
    assert BROWSER_TO_KEYSYM["c"] == K.c
    assert BROWSER_TO_KEYSYM["Q"] == K.Q


def test_vi_movement_keys_mapped():
    from web.key_map import BROWSER_TO_KEYSYM
    import tcod.event

    K = tcod.event.KeySym
    assert BROWSER_TO_KEYSYM["h"] == K.h
    assert BROWSER_TO_KEYSYM["j"] == K.j
    assert BROWSER_TO_KEYSYM["k"] == K.k
    assert BROWSER_TO_KEYSYM["l"] == K.l
    assert BROWSER_TO_KEYSYM["y"] == K.y
    assert BROWSER_TO_KEYSYM["u"] == K.u
    assert BROWSER_TO_KEYSYM["b"] == K.b
    assert BROWSER_TO_KEYSYM["n"] == K.n


def test_page_scroll_keys_mapped():
    from web.key_map import BROWSER_TO_KEYSYM
    import tcod.event

    K = tcod.event.KeySym
    assert BROWSER_TO_KEYSYM["PageUp"] == K.PAGEUP
    assert BROWSER_TO_KEYSYM["PageDown"] == K.PAGEDOWN


def test_numpad_keys_mapped():
    from web.key_map import BROWSER_TO_KEYSYM
    import tcod.event

    K = tcod.event.KeySym
    assert BROWSER_TO_KEYSYM["Numpad1"] == K.KP_1
    assert BROWSER_TO_KEYSYM["Numpad5"] == K.KP_5
    assert BROWSER_TO_KEYSYM["Numpad9"] == K.KP_9


def test_unknown_key_returns_none():
    from web.key_map import BROWSER_TO_KEYSYM

    assert BROWSER_TO_KEYSYM.get("F13") is None
    assert BROWSER_TO_KEYSYM.get("") is None


def test_web_key_event_has_sym_and_mod():
    from web.key_map import WebKeyEvent

    evt = WebKeyEvent(sym=100, mod=0)
    assert evt.sym == 100
    assert evt.mod == 0


def test_web_key_event_type_field():
    from web.key_map import WebKeyEvent

    down = WebKeyEvent(sym=1, mod=0, type="keydown")
    up = WebKeyEvent(sym=1, mod=0, type="keyup")
    assert down.type == "keydown"
    assert up.type == "keyup"


def test_mod_flags_shift():
    from web.key_map import mod_flags

    assert mod_flags(shift=True, ctrl=False, alt=False) & 0x1


def test_mod_flags_ctrl():
    from web.key_map import mod_flags

    assert mod_flags(shift=False, ctrl=True, alt=False) & 0x40


def test_mod_flags_none():
    from web.key_map import mod_flags

    assert mod_flags(shift=False, ctrl=False, alt=False) == 0
