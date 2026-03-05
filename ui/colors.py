"""Shared UI color constants (RGB tuples) used across UI states."""
from typing import Tuple

Color = Tuple[int, int, int]

# General
WHITE: Color = (255, 255, 255)
GRAY: Color = (150, 150, 150)
DARK_GRAY: Color = (100, 100, 100)
HINT_COLOR: Color = (80, 80, 80)

# Dialog / panel backgrounds
DIALOG_BG: Color = (15, 15, 30)

# Tab selection
TAB_SELECTED: Color = (255, 255, 100)
TAB_UNSELECTED: Color = (100, 100, 120)

# Headers
HEADER_SEP: Color = (60, 60, 80)
HEADER_TEXT: Color = (180, 180, 200)
HEADER_TITLE: Color = (255, 255, 200)

# HP colors
HP_GREEN: Color = (0, 255, 0)
HP_YELLOW: Color = (255, 255, 0)
HP_RED: Color = (255, 0, 0)

# Threat levels
THREAT_LOW: Color = (100, 255, 100)
THREAT_MODERATE: Color = (255, 255, 100)
THREAT_HIGH: Color = (255, 100, 100)
