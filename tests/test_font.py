"""Tests for engine/font.py tileset loading."""

import pathlib
from unittest.mock import MagicMock, patch

from engine.font import FONT_DIR, FONT_FILE, load_tileset


def test_font_dir_points_to_data():
    """FONT_DIR should resolve to the project's data/ directory."""
    assert FONT_DIR.name == "data"
    assert FONT_DIR.is_absolute()


def test_font_file_is_inside_font_dir():
    """FONT_FILE should be a child of FONT_DIR."""
    assert FONT_FILE.parent == FONT_DIR
    assert FONT_FILE.name == "terminal10x16_gs_ro.png"


def test_load_tileset_returns_none_when_file_missing():
    """When the font file doesn't exist, load_tileset returns None."""
    with patch.object(pathlib.Path, "exists", return_value=False):
        result = load_tileset()
    assert result is None


def test_load_tileset_calls_load_tilesheet_when_file_exists():
    """When the font file exists, load_tileset loads it via tcod."""
    mock_tileset = MagicMock()
    with (
        patch.object(pathlib.Path, "exists", return_value=True),
        patch("tcod.tileset.load_tilesheet", return_value=mock_tileset),
    ):
        result = load_tileset()
    assert result is mock_tileset


def test_load_tileset_returns_none_on_load_error():
    """When load_tilesheet raises, load_tileset falls back to None."""
    with (
        patch.object(pathlib.Path, "exists", return_value=True),
        patch("tcod.tileset.load_tilesheet", side_effect=Exception("corrupt")),
    ):
        result = load_tileset()
    assert result is None
