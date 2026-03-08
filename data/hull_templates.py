"""Hull profile templates for ship generation.

Each ship is composed of bow + mid + stern sections.  Every section has a
Y-profile array giving the half-width (top offset from centerline) at each
x-position.  The hull is symmetric: bottom offset = -top offset.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class HullSection:
    name: str
    profile: list[int]  # top_offset per x (bottom = -top, symmetric)
    room_type: str | None  # "bridge", "engine_room", or None (mid)


# -------------------------------------------------------------------
# Bow templates (room_type="bridge")
# -------------------------------------------------------------------

BOW_POINTED = HullSection(
    name="pointed",
    profile=[1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 10, 10, 10, 10],
    room_type="bridge",
)

BOW_BLUNT = HullSection(
    name="blunt",
    profile=[6, 7, 8, 9, 9, 10, 10, 10, 10, 10],
    room_type="bridge",
)

BOW_WEDGE = HullSection(
    name="wedge",
    profile=[1, 2, 3, 4, 5, 6, 7, 8, 8, 9, 10, 10, 10, 10, 10, 10],
    room_type="bridge",
)

BOWS = [BOW_POINTED, BOW_BLUNT, BOW_WEDGE]

# -------------------------------------------------------------------
# Mid templates (room_type=None)
# -------------------------------------------------------------------

MID_WIDE = HullSection(
    name="wide",
    profile=[11, 11, 12, 12, 12, 12, 13, 13, 13, 13, 13, 13, 13, 13,
             13, 13, 13, 13, 13, 13, 13, 13, 12, 12, 12, 12, 11, 11,
             11, 11, 11, 11, 11, 11, 11, 11],
    room_type=None,
)

MID_UNIFORM = HullSection(
    name="uniform",
    profile=[10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
             10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
             10, 10, 10, 10, 10, 10, 10, 10],
    room_type=None,
)

MID_TAPERED = HullSection(
    name="tapered",
    profile=[10, 11, 11, 12, 12, 12, 13, 13, 13, 13, 13, 13, 13, 13,
             13, 13, 13, 13, 13, 12, 12, 12, 11, 11, 11, 10, 10, 10,
             10, 10, 10, 10, 10, 10],
    room_type=None,
)

MIDS = [MID_WIDE, MID_UNIFORM, MID_TAPERED]

# -------------------------------------------------------------------
# Stern templates (room_type="engine_room")
# -------------------------------------------------------------------

STERN_TAPERED = HullSection(
    name="tapered",
    profile=[10, 10, 9, 9, 8, 8, 7, 6, 5, 5, 4, 3, 2, 2, 1, 1],
    room_type="engine_room",
)

STERN_FLARED = HullSection(
    name="flared",
    profile=[10, 10, 11, 11, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 1, 1],
    room_type="engine_room",
)

STERN_BLUNT = HullSection(
    name="blunt",
    profile=[10, 10, 9, 9, 9, 8, 8, 8, 7, 7, 6, 6],
    room_type="engine_room",
)

STERNS = [STERN_TAPERED, STERN_FLARED, STERN_BLUNT]


def get_random_hull(
    rng: random.Random,
) -> Tuple[HullSection, HullSection, HullSection]:
    """Pick one random bow, mid, and stern template."""
    bow = rng.choice(BOWS)
    mid = rng.choice(MIDS)
    stern = rng.choice(STERNS)
    return bow, mid, stern
