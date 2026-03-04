"""Font/tileset loading with graceful fallback to tcod default."""
from __future__ import annotations

import pathlib


FONT_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "fonts"
FONT_FILE = FONT_DIR / "dejavu10x10_gs_tc.png"


def load_tileset():
    """Load a custom tileset if present, otherwise return None (tcod uses its default)."""
    import tcod.tileset

    if FONT_FILE.exists():
        return tcod.tileset.load_tilesheet(
            str(FONT_FILE), 32, 8, tcod.tileset.CHARMAP_TCOD
        )
    return None
