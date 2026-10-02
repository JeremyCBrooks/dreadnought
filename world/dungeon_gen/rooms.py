"""Room primitives shared by every generator: RectRoom and small room helpers."""

from __future__ import annotations

import random

import numpy as np

from world import tile_types
from world.loc_profiles import LocationProfile, RoomSpec


def _safe_randint(rng: random.Random, lo: int, hi: int) -> int | None:
    """Return rng.randint(lo, hi) or None when lo > hi."""
    if lo > hi:
        return None
    return rng.randint(lo, hi)


def _near_exit(x: int, y: int, exit_pos: tuple[int, int] | None) -> bool:
    """Return True if (x, y) is within 1 tile of *exit_pos*."""
    if exit_pos is None:
        return False
    return abs(x - exit_pos[0]) <= 1 and abs(y - exit_pos[1]) <= 1


class RectRoom:
    def __init__(self, x: int, y: int, width: int, height: int, label: str = "") -> None:
        self.x1 = x
        self.y1 = y
        self.x2 = x + width
        self.y2 = y + height
        self.label = label

    @property
    def center(self) -> tuple[int, int]:
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    @property
    def inner(self) -> tuple[slice, slice]:
        return slice(self.x1 + 1, self.x2), slice(self.y1 + 1, self.y2)

    def translated(self, dx: int, dy: int) -> RectRoom:
        """Return a copy of this room shifted by (dx, dy)."""
        return RectRoom(self.x1 + dx, self.y1 + dy, self.x2 - self.x1, self.y2 - self.y1, label=self.label)

    def intersects(self, other: RectRoom) -> bool:
        return self.x1 <= other.x2 and self.x2 >= other.x1 and self.y1 <= other.y2 and self.y2 >= other.y1


def _roll_room(
    rng: random.Random,
    map_w: int,
    map_h: int,
    min_w: int,
    max_w: int,
    min_h: int,
    max_h: int,
    label: str = "",
) -> RectRoom:
    """Roll a random room on a map of the given size.

    Draw order (width, height, x, y) is part of the seed contract; do not reorder.
    """
    rw = rng.randint(min_w, max_w)
    rh = rng.randint(min_h, max_h)
    rx = rng.randint(1, max(1, map_w - rw - 2))
    ry = rng.randint(1, max(1, map_h - rh - 2))
    return RectRoom(rx, ry, rw, rh, label=label)


def _resolve_tile(name: str) -> np.ndarray:
    """Look up a tile by attribute name on tile_types."""
    return getattr(tile_types, name)


def _random_room_pos(room: RectRoom, rng: random.Random) -> tuple[int, int]:
    """Pick a random floor position inside a room."""
    x = rng.randint(room.x1 + 1, max(room.x1 + 1, room.x2 - 1))
    y = rng.randint(room.y1 + 1, max(room.y1 + 1, room.y2 - 1))
    return x, y


def _room_wall_positions(room: RectRoom) -> list[tuple[int, int]]:
    """Return wall-tile positions bordering the room's interior."""
    positions = []
    for x in range(room.x1 + 1, room.x2):
        positions.append((x, room.y1))
        positions.append((x, room.y2))
    for y in range(room.y1 + 1, room.y2):
        positions.append((room.x1, y))
        positions.append((room.x2, y))
    return positions


def _pick_room_spec(
    rng: random.Random,
    profile: LocationProfile,
    label_counts: dict[str, int],
    allowed_specs: list[RoomSpec] | None = None,
) -> RoomSpec:
    """Pick a room spec from the profile, respecting max_count limits.

    If *allowed_specs* is given, only those specs are considered.
    """
    specs = allowed_specs if allowed_specs is not None else profile.room_specs
    available = [s for s in specs if s.max_count == -1 or label_counts.get(s.label, 0) < s.max_count]
    if not available:
        # All at max — pick any unlimited spec or fall back to first
        unlimited = [s for s in specs if s.max_count == -1]
        return rng.choice(unlimited) if unlimited else specs[0]
    return rng.choice(available)


def _required_specs(profile: LocationProfile) -> list[RoomSpec]:
    return [s for s in profile.room_specs if s.required]
