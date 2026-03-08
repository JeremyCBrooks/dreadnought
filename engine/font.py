"""Font/tileset loading with graceful fallback to tcod default."""
from __future__ import annotations

import pathlib


FONT_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
FONT_FILE = FONT_DIR / "terminal10x16_gs_ro.png"


def load_tileset():
    """Load a custom tileset if present, otherwise fall back to tcod default."""
    import tcod.tileset

    if FONT_FILE.exists():
        return tcod.tileset.load_tilesheet(
            str(FONT_FILE), 16, 16, tcod.tileset.CHARMAP_CP437
        )
    return tcod.tileset.get_default()
