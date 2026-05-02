"""Tests for web/console_serializer.py."""

import numpy as np
import pytest


def make_console(w: int = 4, h: int = 3):
    """Create a minimal tcod-compatible Console stub using a numpy array."""
    import tcod.console

    return tcod.console.Console(w, h, order="F")


def test_first_call_returns_full_frame_type():
    from web.console_serializer import serialize_delta

    console = make_console()
    tiles, _ = serialize_delta(console, None)
    # First call: all cells returned
    assert len(tiles) == 4 * 3


def test_first_call_returns_all_cells():
    from web.console_serializer import serialize_delta

    console = make_console(2, 2)
    console.rgb["ch"][0, 0] = ord("A")
    tiles, _ = serialize_delta(console, None)
    coords = {(t[0], t[1]) for t in tiles}
    assert coords == {(0, 0), (0, 1), (1, 0), (1, 1)}


def test_each_tile_has_nine_fields():
    from web.console_serializer import serialize_delta

    console = make_console(2, 2)
    tiles, _ = serialize_delta(console, None)
    for tile in tiles:
        assert len(tile) == 9, "tile must be [x, y, ch, fr, fg, fb, br, bg, bb]"


def test_unchanged_frame_returns_empty_delta():
    from web.console_serializer import serialize_delta

    console = make_console(2, 2)
    _, prev = serialize_delta(console, None)
    tiles, _ = serialize_delta(console, prev)
    assert tiles == []


def test_changed_cell_appears_in_delta():
    from web.console_serializer import serialize_delta

    console = make_console(3, 3)
    _, prev = serialize_delta(console, None)

    console.rgb["ch"][1, 2] = ord("X")
    console.rgb["fg"][1, 2] = (255, 128, 0)

    tiles, _ = serialize_delta(console, prev)
    assert len(tiles) == 1
    t = tiles[0]
    assert t[0] == 1 and t[1] == 2          # x, y
    assert t[2] == ord("X")                  # ch
    assert t[3] == 255 and t[4] == 128       # fg r, g


def test_only_changed_cells_in_delta():
    from web.console_serializer import serialize_delta

    console = make_console(4, 4)
    _, prev = serialize_delta(console, None)

    console.rgb["ch"][0, 0] = ord("A")
    console.rgb["ch"][3, 3] = ord("Z")

    tiles, _ = serialize_delta(console, prev)
    assert len(tiles) == 2
    coords = {(t[0], t[1]) for t in tiles}
    assert coords == {(0, 0), (3, 3)}


def test_serialize_returns_updated_prev():
    from web.console_serializer import serialize_delta

    console = make_console(2, 2)
    _, prev1 = serialize_delta(console, None)

    console.rgb["ch"][0, 0] = ord("Q")
    _, prev2 = serialize_delta(console, prev1)

    # Third call: nothing changed → empty delta
    tiles, _ = serialize_delta(console, prev2)
    assert tiles == []


def test_tile_values_are_python_ints():
    """JSON serialization requires plain ints, not numpy scalar types."""
    from web.console_serializer import serialize_delta

    console = make_console(2, 2)
    console.rgb["ch"][0, 0] = ord("@")
    console.rgb["fg"][0, 0] = (200, 100, 50)
    console.rgb["bg"][0, 0] = (10, 20, 30)

    tiles, _ = serialize_delta(console, None)
    t = next(tile for tile in tiles if tile[0] == 0 and tile[1] == 0)
    for val in t:
        assert isinstance(val, int), f"expected int, got {type(val)}: {val}"
