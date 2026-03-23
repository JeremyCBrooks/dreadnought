"""Font/tileset loading with graceful fallback to tcod default."""

from __future__ import annotations

import logging
import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tcod.tileset

logger = logging.getLogger(__name__)

FONT_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
FONT_FILE = FONT_DIR / "terminal10x16_gs_ro.png"


def load_tileset() -> tcod.tileset.Tileset | None:
    """Load a custom tileset if present, otherwise fall back to tcod default."""
    import tcod.tileset

    if not FONT_FILE.exists():
        logger.info("Font file not found at %s, using tcod default", FONT_FILE)
        return None
    try:
        return tcod.tileset.load_tilesheet(str(FONT_FILE), 16, 16, tcod.tileset.CHARMAP_CP437)
    except Exception:
        logger.exception("Failed to load tileset from %s", FONT_FILE)
        return None
