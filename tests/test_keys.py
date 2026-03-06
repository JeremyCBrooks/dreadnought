"""Tests for ui.keys — centralised key mappings."""
import tcod.event

from ui.keys import (
    move_keys,
    confirm_keys,
    cancel_keys,
    action_keys,
    is_move_key,
    is_action,
)

K = tcod.event.KeySym


# -- move_keys ---------------------------------------------------------------

def test_move_keys_contains_arrows():
    mk = move_keys()
    assert mk[K.UP] == (0, -1)
    assert mk[K.DOWN] == (0, 1)
    assert mk[K.LEFT] == (-1, 0)
    assert mk[K.RIGHT] == (1, 0)


def test_move_keys_contains_vi_keys():
    mk = move_keys()
    assert mk[K.h] == (-1, 0)
    assert mk[K.j] == (0, 1)
    assert mk[K.k] == (0, -1)
    assert mk[K.l] == (1, 0)


def test_move_keys_contains_numpad():
    mk = move_keys()
    assert mk[K.KP_8] == (0, -1)
    assert mk[K.KP_2] == (0, 1)
    assert mk[K.KP_4] == (-1, 0)
    assert mk[K.KP_6] == (1, 0)


def test_move_keys_diagonals():
    mk = move_keys()
    assert mk[K.y] == (-1, -1)
    assert mk[K.u] == (1, -1)
    assert mk[K.b] == (-1, 1)
    assert mk[K.n] == (1, 1)


# -- is_move_key -------------------------------------------------------------

def test_is_move_key_true_for_arrow():
    assert is_move_key(K.UP) is True


def test_is_move_key_false_for_letter():
    assert is_move_key(K.a) is False


# -- confirm / cancel ---------------------------------------------------------

def test_confirm_keys_contains_return():
    assert K.RETURN in confirm_keys()
    assert K.KP_ENTER in confirm_keys()


def test_cancel_keys_contains_escape():
    assert K.ESCAPE in cancel_keys()


# -- action_keys / is_action --------------------------------------------------

def test_action_keys_has_expected_actions():
    ak = action_keys()
    expected = {"look", "fire", "inventory", "scan", "interact", "get", "wait", "quit", "cargo"}
    assert expected == set(ak.keys())


def test_is_action_look():
    assert is_action("look", K.x) is True


def test_is_action_fire():
    assert is_action("fire", K.f) is True


def test_is_action_wait():
    assert is_action("wait", K.PERIOD) is True
    assert is_action("wait", K.KP_5) is True


def test_is_action_get():
    assert is_action("get", K.g) is True
    assert is_action("get", K.COMMA) is True


def test_is_action_false_for_wrong_key():
    assert is_action("look", K.z) is False
