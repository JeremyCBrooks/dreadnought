"""Procedural dungeon generation: room-and-corridor algorithm."""
from __future__ import annotations

import random
from typing import List, Optional, Tuple

from world.game_map import GameMap
from world import tile_types
from world.loc_profiles import get_profile, LocationProfile, RoomSpec
from game.entity import Entity, Fighter
from game.ai import HostileAI
from data import db

import numpy as np


def _safe_randint(rng: random.Random, lo: int, hi: int) -> Optional[int]:
    """Return rng.randint(lo, hi) or None when lo > hi."""
    if lo > hi:
        return None
    return rng.randint(lo, hi)


def _near_exit(x: int, y: int, exit_pos: Optional[Tuple[int, int]]) -> bool:
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
    def center(self) -> Tuple[int, int]:
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    @property
    def inner(self) -> Tuple[slice, slice]:
        return slice(self.x1 + 1, self.x2), slice(self.y1 + 1, self.y2)

    def intersects(self, other: RectRoom) -> bool:
        return (
            self.x1 <= other.x2
            and self.x2 >= other.x1
            and self.y1 <= other.y2
            and self.y2 >= other.y1
        )


def _resolve_tile(name: str) -> np.ndarray:
    """Look up a tile by attribute name on tile_types."""
    return getattr(tile_types, name)


# -------------------------------------------------------------------
# Corridor carving
# -------------------------------------------------------------------

def _carve_h_tunnel(
    game_map: GameMap, x1: int, x2: int, y: int,
    floor_tile: np.ndarray | None = None,
) -> None:
    ft = floor_tile if floor_tile is not None else tile_types.floor
    for x in range(min(x1, x2), max(x1, x2) + 1):
        if game_map.in_bounds(x, y):
            game_map.tiles[x, y] = ft


def _carve_v_tunnel(
    game_map: GameMap, y1: int, y2: int, x: int,
    floor_tile: np.ndarray | None = None,
) -> None:
    ft = floor_tile if floor_tile is not None else tile_types.floor
    for y in range(min(y1, y2), max(y1, y2) + 1):
        if game_map.in_bounds(x, y):
            game_map.tiles[x, y] = ft


def _carve_wide_h_tunnel(
    game_map: GameMap, x1: int, x2: int, y: int,
    floor_tile: np.ndarray | None = None,
) -> None:
    """Carve a 2-tile wide horizontal corridor."""
    _carve_h_tunnel(game_map, x1, x2, y, floor_tile)
    if game_map.in_bounds(0, y + 1):
        _carve_h_tunnel(game_map, x1, x2, y + 1, floor_tile)


def _carve_wide_v_tunnel(
    game_map: GameMap, y1: int, y2: int, x: int,
    floor_tile: np.ndarray | None = None,
) -> None:
    """Carve a 2-tile wide vertical corridor."""
    _carve_v_tunnel(game_map, y1, y2, x, floor_tile)
    if game_map.in_bounds(x + 1, 0):
        _carve_v_tunnel(game_map, y1, y2, x + 1, floor_tile)


def _carve_winding_tunnel(
    game_map: GameMap, x1: int, y1: int, x2: int, y2: int,
    rng: random.Random,
    floor_tile: np.ndarray | None = None,
) -> None:
    """Biased drunkard's walk from (x1,y1) to (x2,y2)."""
    ft = floor_tile if floor_tile is not None else tile_types.floor
    cx, cy = x1, y1
    max_steps = 3 * (abs(x2 - x1) + abs(y2 - y1))
    max_steps = max(max_steps, 10)

    for _ in range(max_steps):
        if game_map.in_bounds(cx, cy):
            game_map.tiles[cx, cy] = ft
        if cx == x2 and cy == y2:
            return

        roll = rng.random()
        if roll < 0.60:
            # Move toward target
            dx = 1 if x2 > cx else (-1 if x2 < cx else 0)
            dy = 1 if y2 > cy else (-1 if y2 < cy else 0)
            if rng.random() < 0.5 and dx != 0:
                cx += dx
            elif dy != 0:
                cy += dy
            elif dx != 0:
                cx += dx
        elif roll < 0.90:
            # Move perpendicular
            dx = 1 if x2 > cx else (-1 if x2 < cx else 0)
            dy = 1 if y2 > cy else (-1 if y2 < cy else 0)
            if dx != 0 and dy != 0:
                if rng.random() < 0.5:
                    cy += rng.choice([-1, 1])
                else:
                    cx += rng.choice([-1, 1])
            elif dx != 0:
                cy += rng.choice([-1, 1])
            else:
                cx += rng.choice([-1, 1])
        # else: 10% pause — no move

        # 15% chance to carve a 3x3 alcove
        if rng.random() < 0.15:
            for ax in range(cx - 1, cx + 2):
                for ay in range(cy - 1, cy + 2):
                    if game_map.in_bounds(ax, ay):
                        game_map.tiles[ax, ay] = ft

        cx = max(1, min(cx, game_map.width - 2))
        cy = max(1, min(cy, game_map.height - 2))

    # Fallback: straight corridors if we didn't reach target
    _carve_h_tunnel(game_map, cx, x2, cy, ft)
    _carve_v_tunnel(game_map, cy, y2, x2, ft)


# -------------------------------------------------------------------
# Spawning helpers
# -------------------------------------------------------------------

def _spawn_enemies(
    room: RectRoom, game_map: GameMap, rng: random.Random, max_enemies: int = 2,
    exit_pos: Optional[Tuple[int, int]] = None,
) -> None:
    for _ in range(rng.randint(0, max_enemies)):
        x = rng.randint(room.x1 + 1, max(room.x1 + 1, room.x2 - 1))
        y = rng.randint(room.y1 + 1, max(room.y1 + 1, room.y2 - 1))
        if not game_map.in_bounds(x, y) or not game_map.tiles["walkable"][x, y]:
            continue
        if game_map.get_blocking_entity(x, y):
            continue
        if _near_exit(x, y, exit_pos):
            continue
        defn = rng.choice(db.enemies())
        game_map.entities.append(
            Entity(
                x=x, y=y, char=defn["char"], color=defn["color"], name=defn["name"],
                blocks_movement=True,
                fighter=Fighter(hp=defn["hp"], max_hp=defn["hp"],
                                defense=defn["defense"], power=defn["power"]),
                ai=HostileAI(),
            )
        )


def _spawn_items(
    room: RectRoom, game_map: GameMap, rng: random.Random, max_items: int = 1,
    exit_pos: Optional[Tuple[int, int]] = None,
) -> None:
    for _ in range(rng.randint(0, max_items)):
        x = rng.randint(room.x1 + 1, max(room.x1 + 1, room.x2 - 1))
        y = rng.randint(room.y1 + 1, max(room.y1 + 1, room.y2 - 1))
        if not game_map.in_bounds(x, y) or not game_map.tiles["walkable"][x, y]:
            continue
        if _near_exit(x, y, exit_pos):
            continue
        defn = rng.choice(db.items())
        game_map.entities.append(
            Entity(
                x=x, y=y, char=defn["char"], color=defn["color"], name=defn["name"],
                blocks_movement=False,
                item=db.build_item_data(defn),
            )
        )


def _room_wall_positions(room: RectRoom) -> List[Tuple[int, int]]:
    """Return wall-tile positions bordering the room's interior."""
    positions = []
    for x in range(room.x1 + 1, room.x2):
        positions.append((x, room.y1))
        positions.append((x, room.y2))
    for y in range(room.y1 + 1, room.y2):
        positions.append((room.x1, y))
        positions.append((room.x2, y))
    return positions


def _spawn_interactables(
    room: RectRoom,
    game_map: GameMap,
    rng: random.Random,
    count: int = 1,
    hazard_chance: float = 0.2,
    wall_interactable_name: Optional[str] = None,
    exit_pos: Optional[Tuple[int, int]] = None,
) -> None:
    floor_pool = db.floor_interactables()
    wall_defn = db.interactable_by_name(wall_interactable_name) if wall_interactable_name else None
    pool = floor_pool + ([wall_defn] if wall_defn else [])

    for _ in range(count):
        defn = rng.choice(pool)
        ch, color, name = defn["char"], defn["color"], defn["name"]
        is_wall = defn.get("placement") == "wall"

        if is_wall:
            candidates = [
                (wx, wy) for wx, wy in _room_wall_positions(room)
                if game_map.in_bounds(wx, wy)
                and not game_map.tiles["walkable"][wx, wy]
                and not game_map.get_interactable_at(wx, wy)
                and not _near_exit(wx, wy, exit_pos)
            ]
            if not candidates:
                continue
            x, y = rng.choice(candidates)
        else:
            x = rng.randint(room.x1 + 1, max(room.x1 + 1, room.x2 - 1))
            y = rng.randint(room.y1 + 1, max(room.y1 + 1, room.y2 - 1))
            if not game_map.in_bounds(x, y) or not game_map.tiles["walkable"][x, y]:
                continue
            if game_map.get_blocking_entity(x, y) or game_map.get_interactable_at(x, y):
                continue
            if _near_exit(x, y, exit_pos):
                continue

        hazard = None
        if rng.random() < hazard_chance:
            hazard = dict(rng.choice(db.hazards()))
        all_loot = db.all_loot()
        loot = rng.choice(all_loot) if rng.random() < 0.6 else None
        game_map.entities.append(
            Entity(
                x=x, y=y, char=ch, color=color, name=name,
                blocks_movement=False,
                interactable={"kind": name.lower(), "hazard": hazard, "loot": loot},
            )
        )


# -------------------------------------------------------------------
# Ship room dressing (data-driven)
# -------------------------------------------------------------------

_ROOM_DRESSING = {
    "bridge": {
        "decoration_count": (2, 4),
        "interactable_count": (1, 3),
        "loot_chance": 0.4,
        "hazard_chance": 0.1,
        "decorations": [
            (".", (80, 120, 180), "Seat"),
            ("*", (60, 180, 220), "Blinking Light"),
        ],
        "interactables": [
            ("&", (80, 200, 255), "Nav Terminal"),
            ("&", (100, 180, 220), "Comms Terminal"),
            ("&", (100, 200, 255), "Console"),
        ],
    },
    "engine_room": {
        "decoration_count": (2, 4),
        "interactable_count": (1, 3),
        "loot_chance": 0.3,
        "hazard_chance": 0.4,
        "decorations": [
            ("-", (120, 120, 140), "Piping"),
            ("*", (200, 180, 0), "Warning Light"),
            ("#", (100, 100, 120), "Machinery"),
        ],
        "interactables": [
            ("*", (0, 255, 100), "Reactor Core"),
            ("&", (100, 200, 255), "Engine Terminal"),
            ("v", (80, 180, 220), "Coolant Valve"),
        ],
    },
    "cargo": {
        "decoration_count": (1, 2),
        "interactable_count": (3, 6),
        "loot_chance": 0.3,
        "hazard_chance": 0.1,
        "decorations": [
            ("~", (140, 120, 80), "Cargo Net"),
        ],
        "interactables": [
            ("=", (180, 160, 100), "Crate"),
            ("=", (160, 180, 120), "Supply Crate"),
            ("[", (150, 160, 180), "Supply Locker"),
        ],
    },
    "crew_quarters": {
        "decoration_count": (2, 4),
        "interactable_count": (1, 2),
        "loot_chance": 0.4,
        "hazard_chance": 0.05,
        "decorations": [
            ("_", (120, 100, 80), "Bunk"),
            ("-", (100, 90, 70), "Footlocker"),
        ],
        "interactables": [
            ("[", (150, 160, 180), "Personal Locker"),
            ("&", (100, 180, 200), "Personal Terminal"),
        ],
    },
}


def _dress_ship_room(
    room: RectRoom,
    game_map: GameMap,
    rng: random.Random,
    exit_pos: Optional[Tuple[int, int]] = None,
) -> None:
    """Place themed decorations and interactables in a ship room."""
    dressing = _ROOM_DRESSING.get(room.label)
    if not dressing:
        return

    occupied: set[Tuple[int, int]] = {
        (e.x, e.y) for e in game_map.entities
    }

    def _pick_floor_pos() -> Optional[Tuple[int, int]]:
        x_lo = max(room.x1 + 1, 0)
        x_hi = min(room.x2 - 1, game_map.width - 1)
        y_lo = max(room.y1 + 1, 0)
        y_hi = min(room.y2 - 1, game_map.height - 1)
        if x_lo > x_hi or y_lo > y_hi:
            return None
        for _ in range(10):
            x = rng.randint(x_lo, x_hi)
            y = rng.randint(y_lo, y_hi)
            if (x, y) not in occupied and game_map.tiles["walkable"][x, y] and not _near_exit(x, y, exit_pos):
                return x, y
        return None

    # Decorations — visual only, non-blocking, no interactable
    dec_min, dec_max = dressing["decoration_count"]
    for _ in range(rng.randint(dec_min, dec_max)):
        pos = _pick_floor_pos()
        if not pos:
            continue
        ch, color, name = rng.choice(dressing["decorations"])
        occupied.add(pos)
        game_map.entities.append(
            Entity(x=pos[0], y=pos[1], char=ch, color=color, name=name,
                   blocks_movement=False)
        )

    # Interactable furnishings
    int_min, int_max = dressing["interactable_count"]
    loot_chance = dressing["loot_chance"]
    hazard_chance = dressing["hazard_chance"]
    all_loot = db.all_loot()
    hazard_pool = db.hazards()

    for _ in range(rng.randint(int_min, int_max)):
        pos = _pick_floor_pos()
        if not pos:
            continue
        ch, color, name = rng.choice(dressing["interactables"])
        hazard = dict(rng.choice(hazard_pool)) if rng.random() < hazard_chance else None
        loot = rng.choice(all_loot) if rng.random() < loot_chance else None
        occupied.add(pos)
        game_map.entities.append(
            Entity(x=pos[0], y=pos[1], char=ch, color=color, name=name,
                   blocks_movement=False,
                   interactable={"kind": name.lower(), "hazard": hazard, "loot": loot})
        )


# -------------------------------------------------------------------
# Room spec helpers
# -------------------------------------------------------------------

def _pick_room_spec(
    rng: random.Random,
    profile: LocationProfile,
    label_counts: dict[str, int],
    allowed_specs: Optional[List[RoomSpec]] = None,
) -> RoomSpec:
    """Pick a room spec from the profile, respecting max_count limits.

    If *allowed_specs* is given, only those specs are considered.
    """
    specs = allowed_specs if allowed_specs is not None else profile.room_specs
    available = [
        s for s in specs
        if s.max_count == -1 or label_counts.get(s.label, 0) < s.max_count
    ]
    if not available:
        # All at max — pick any unlimited spec or fall back to first
        unlimited = [s for s in specs if s.max_count == -1]
        return rng.choice(unlimited) if unlimited else specs[0]
    return rng.choice(available)


def _required_specs(profile: LocationProfile) -> List[RoomSpec]:
    return [s for s in profile.room_specs if s.required]


# -------------------------------------------------------------------
# Generator functions
# -------------------------------------------------------------------

def _build_ship_skeleton(
    game_map: GameMap,
    rng: random.Random,
    floor_tile: np.ndarray,
) -> Tuple[int, int, int, int, List[Tuple[int, int, int]]]:
    """Build the ship's corridor skeleton: a wide keel + perpendicular ribs.

    Returns (keel_x1, keel_x2, keel_y, keel_y2, ribs) where each rib is
    (rib_x, rib_y_start, rib_y_end).
    """
    w, h = game_map.width, game_map.height
    zone_w = w // 3

    keel_y = h // 2
    # Keel doesn't span full map — leave margins
    keel_x1 = max(2, zone_w // 2)
    keel_x2 = min(w - 3, 2 * zone_w + zone_w // 2)
    keel_y2 = keel_y + 1  # 2-tile wide

    _carve_wide_h_tunnel(game_map, keel_x1, keel_x2, keel_y, floor_tile)

    # Cross-corridors (ribs) branching perpendicular from the keel
    keel_len = keel_x2 - keel_x1
    num_ribs = rng.randint(2, 4)
    ribs: List[Tuple[int, int, int]] = []

    for i in range(num_ribs):
        # Evenly spaced along keel with jitter
        base_x = keel_x1 + (i + 1) * keel_len // (num_ribs + 1)
        rib_x = base_x + rng.randint(-2, 2)
        rib_x = max(keel_x1 + 1, min(rib_x, keel_x2 - 1))

        extent_up = rng.randint(4, 10)
        extent_down = rng.randint(4, 10)

        # Decide direction: both, up only, or down only
        direction = rng.random()
        if direction < 0.5:
            # Both directions
            rib_y_start = max(1, keel_y - extent_up)
            rib_y_end = min(h - 2, keel_y2 + extent_down)
        elif direction < 0.75:
            # Up only (port)
            rib_y_start = max(1, keel_y - extent_up)
            rib_y_end = keel_y2
        else:
            # Down only (starboard)
            rib_y_start = keel_y
            rib_y_end = min(h - 2, keel_y2 + extent_down)

        _carve_v_tunnel(game_map, rib_y_start, rib_y_end, rib_x, floor_tile)
        ribs.append((rib_x, rib_y_start, rib_y_end))

    return keel_x1, keel_x2, keel_y, keel_y2, ribs


def _nearest_skeleton_point(
    cx: int, cy: int,
    keel_x1: int, keel_x2: int, keel_y: int, keel_y2: int,
    ribs: List[Tuple[int, int, int]],
) -> Tuple[int, int]:
    """Find the closest point on the skeleton (keel or any rib) to (cx, cy)."""
    best = (keel_x1, keel_y)
    best_dist = abs(cx - keel_x1) + abs(cy - keel_y)

    # Check keel — closest x on keel, y is keel_y or keel_y2
    clamped_x = max(keel_x1, min(cx, keel_x2))
    for ky in (keel_y, keel_y2):
        d = abs(cx - clamped_x) + abs(cy - ky)
        if d < best_dist:
            best_dist = d
            best = (clamped_x, ky)

    # Check ribs
    for rib_x, rib_y_start, rib_y_end in ribs:
        clamped_y = max(rib_y_start, min(cy, rib_y_end))
        d = abs(cx - rib_x) + abs(cy - clamped_y)
        if d < best_dist:
            best_dist = d
            best = (rib_x, clamped_y)

    return best


def _connect_room_to_skeleton(
    game_map: GameMap,
    room: RectRoom,
    keel_x1: int, keel_x2: int, keel_y: int, keel_y2: int,
    ribs: List[Tuple[int, int, int]],
    floor_tile: np.ndarray,
) -> None:
    """Connect a room to the nearest skeleton point via an L-shaped corridor."""
    cx, cy = room.center
    sx, sy = _nearest_skeleton_point(cx, cy, keel_x1, keel_x2, keel_y, keel_y2, ribs)
    _carve_h_tunnel(game_map, cx, sx, cy, floor_tile)
    _carve_v_tunnel(game_map, cy, sy, sx, floor_tile)


def _generate_ship(
    game_map: GameMap,
    rng: random.Random,
    profile: LocationProfile,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> List[RectRoom]:
    """Skeleton-based ship layout for derelicts.

    Builds a wide keel corridor with perpendicular ribs, places required rooms
    in their zones, attaches middle rooms to the skeleton, and adds occasional
    room-to-room connections for tactical loops.
    """
    w, h = game_map.width, game_map.height
    rooms: List[RectRoom] = []
    label_counts: dict[str, int] = {}
    zone_w = w // 3

    # Step 1-2: Build skeleton (keel + ribs)
    keel_x1, keel_x2, keel_y, keel_y2, ribs = _build_ship_skeleton(
        game_map, rng, floor_tile,
    )
    skel = (keel_x1, keel_x2, keel_y, keel_y2, ribs)

    # Step 3: Place bridge in left zone
    bridge_spec = next((s for s in profile.room_specs if s.label == "bridge"), None)
    if bridge_spec:
        bw = rng.randint(bridge_spec.min_w, bridge_spec.max_w)
        bh = rng.randint(bridge_spec.min_h, bridge_spec.max_h)
        bx = rng.randint(1, max(1, zone_w - bw - 1))
        by = max(1, keel_y - bh // 2)
        by = min(by, h - bh - 2)
        room = RectRoom(bx, by, bw, bh, label="bridge")
        game_map.tiles[room.inner] = floor_tile
        _connect_room_to_skeleton(game_map, room, *skel, floor_tile)
        rooms.append(room)
        label_counts["bridge"] = 1

    # Place engine room in right zone
    engine_spec = next((s for s in profile.room_specs if s.label == "engine_room"), None)
    if engine_spec:
        for _attempt in range(10):
            ew = rng.randint(engine_spec.min_w, engine_spec.max_w)
            eh = rng.randint(engine_spec.min_h, engine_spec.max_h)
            engine_lo = max(1, 2 * zone_w)
            engine_hi = max(engine_lo, w - ew - 2)
            ex = rng.randint(engine_lo, engine_hi)
            ey = max(1, keel_y - eh // 2)
            ey = min(ey, h - eh - 2)
            room = RectRoom(ex, ey, ew, eh, label="engine_room")
            if not any(room.intersects(r) for r in rooms):
                game_map.tiles[room.inner] = floor_tile
                _connect_room_to_skeleton(game_map, room, *skel, floor_tile)
                rooms.append(room)
                label_counts["engine_room"] = 1
                break

    # Step 4: Place middle rooms along skeleton
    fill_specs = [s for s in profile.room_specs if not s.required]

    # Guarantee one of each non-required room type first
    for spec in fill_specs:
        if len(rooms) >= profile.max_rooms:
            break
        for _ in range(profile.max_rooms * 3):
            rw = rng.randint(spec.min_w, spec.max_w)
            rh = rng.randint(spec.min_h, spec.max_h)
            # Rooms can go anywhere along the ship length (not just middle zone)
            rx = _safe_randint(rng, max(1, keel_x1 - 3), max(1, keel_x2 - rw))
            if rx is None:
                continue
            if rng.random() < 0.5:
                ry = _safe_randint(rng, 1, max(1, keel_y - rh - 1))
            else:
                ry = _safe_randint(rng, min(keel_y2 + 2, h - rh - 2), max(keel_y2 + 2, h - rh - 2))
            if ry is None:
                continue
            room = RectRoom(rx, ry, rw, rh, label=spec.label)
            if not any(room.intersects(r) for r in rooms):
                game_map.tiles[room.inner] = floor_tile
                _connect_room_to_skeleton(game_map, room, *skel, floor_tile)
                rooms.append(room)
                label_counts[spec.label] = label_counts.get(spec.label, 0) + 1
                break

    # Fill remaining rooms
    for _ in range(profile.max_rooms * 3):
        if len(rooms) >= profile.max_rooms:
            break
        spec = _pick_room_spec(rng, profile, label_counts, allowed_specs=fill_specs)
        rw = rng.randint(spec.min_w, spec.max_w)
        rh = rng.randint(spec.min_h, spec.max_h)
        rx = _safe_randint(rng, max(1, keel_x1 - 3), max(1, keel_x2 - rw))
        if rx is None:
            continue
        if rng.random() < 0.5:
            ry = _safe_randint(rng, 1, max(1, keel_y - rh - 1))
        else:
            ry = _safe_randint(rng, min(keel_y2 + 2, h - rh - 2), max(keel_y2 + 2, h - rh - 2))
        if ry is None:
            continue
        room = RectRoom(rx, ry, rw, rh, label=spec.label)
        if any(room.intersects(r) for r in rooms):
            continue
        game_map.tiles[room.inner] = floor_tile
        _connect_room_to_skeleton(game_map, room, *skel, floor_tile)
        rooms.append(room)
        label_counts[spec.label] = label_counts.get(spec.label, 0) + 1

    # Step 5: Room-to-room connections (~30% chance for close pairs)
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            ci = rooms[i].center
            cj = rooms[j].center
            dist = abs(ci[0] - cj[0]) + abs(ci[1] - cj[1])
            if dist <= 12 and rng.random() < 0.3:
                _carve_h_tunnel(game_map, ci[0], cj[0], ci[1], floor_tile)
                _carve_v_tunnel(game_map, ci[1], cj[1], cj[0], floor_tile)

    # Step 6: Room-specific dressing for all rooms
    exit_pos = rooms[0].center if rooms else None
    for room in rooms:
        _dress_ship_room(room, game_map, rng, exit_pos=exit_pos)

    return rooms


def _generate_organic(
    game_map: GameMap,
    rng: random.Random,
    profile: LocationProfile,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> List[RectRoom]:
    """Organic asteroid layout with irregular rooms and winding corridors."""
    w, h = game_map.width, game_map.height
    rooms: List[RectRoom] = []
    label_counts: dict[str, int] = {}

    for _ in range(profile.max_rooms * 3):
        if len(rooms) >= profile.max_rooms:
            break
        spec = _pick_room_spec(rng, profile, label_counts)
        rw = rng.randint(spec.min_w, spec.max_w)
        rh = rng.randint(spec.min_h, spec.max_h)
        rx = rng.randint(1, max(1, w - rw - 2))
        ry = rng.randint(1, max(1, h - rh - 2))
        room = RectRoom(rx, ry, rw, rh, label=spec.label)

        if any(room.intersects(r) for r in rooms):
            continue

        # Carve interior
        game_map.tiles[room.inner] = floor_tile

        # Nibble 15-30% of edge floor tiles for irregular shape
        inner_xs = range(room.x1 + 1, room.x2)
        inner_ys = range(room.y1 + 1, room.y2)
        edge_tiles = []
        for ex in inner_xs:
            edge_tiles.append((ex, room.y1 + 1))
            edge_tiles.append((ex, room.y2 - 1))
        for ey in inner_ys:
            edge_tiles.append((room.x1 + 1, ey))
            edge_tiles.append((room.x2 - 1, ey))
        nibble_count = int(len(edge_tiles) * rng.uniform(0.15, 0.30))
        rng.shuffle(edge_tiles)
        for ex, ey in edge_tiles[:nibble_count]:
            if game_map.in_bounds(ex, ey):
                game_map.tiles[ex, ey] = wall_tile

        # Connect to previous room with winding tunnel
        if rooms:
            prev_cx, prev_cy = rooms[-1].center
            new_cx, new_cy = room.center
            _carve_winding_tunnel(game_map, prev_cx, prev_cy, new_cx, new_cy, rng, floor_tile)

        rooms.append(room)
        label_counts[spec.label] = label_counts.get(spec.label, 0) + 1

    return rooms


def _generate_standard(
    game_map: GameMap,
    rng: random.Random,
    profile: LocationProfile,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> List[RectRoom]:
    """Standard starbase layout — like original but with wider corridors and bigger rooms."""
    w, h = game_map.width, game_map.height
    rooms: List[RectRoom] = []
    label_counts: dict[str, int] = {}

    # Place required rooms first
    for spec in _required_specs(profile):
        for _ in range(profile.max_rooms * 3):
            rw = rng.randint(spec.min_w, spec.max_w)
            rh = rng.randint(spec.min_h, spec.max_h)
            rx = rng.randint(1, max(1, w - rw - 2))
            ry = rng.randint(1, max(1, h - rh - 2))
            room = RectRoom(rx, ry, rw, rh, label=spec.label)
            if not any(room.intersects(r) for r in rooms):
                game_map.tiles[room.inner] = floor_tile
                if rooms:
                    prev_cx, prev_cy = rooms[-1].center
                    new_cx, new_cy = room.center
                    if rng.random() < 0.5:
                        _carve_wide_h_tunnel(game_map, prev_cx, new_cx, prev_cy, floor_tile)
                        _carve_wide_v_tunnel(game_map, prev_cy, new_cy, new_cx, floor_tile)
                    else:
                        _carve_wide_v_tunnel(game_map, prev_cy, new_cy, prev_cx, floor_tile)
                        _carve_wide_h_tunnel(game_map, prev_cx, new_cx, new_cy, floor_tile)
                rooms.append(room)
                label_counts[spec.label] = label_counts.get(spec.label, 0) + 1
                break

    # Fill remaining rooms
    for _ in range(profile.max_rooms * 3):
        if len(rooms) >= profile.max_rooms:
            break
        spec = _pick_room_spec(rng, profile, label_counts)
        rw = rng.randint(spec.min_w, spec.max_w)
        rh = rng.randint(spec.min_h, spec.max_h)
        rx = rng.randint(1, max(1, w - rw - 2))
        ry = rng.randint(1, max(1, h - rh - 2))
        room = RectRoom(rx, ry, rw, rh, label=spec.label)

        if any(room.intersects(r) for r in rooms):
            continue

        game_map.tiles[room.inner] = floor_tile

        if rooms:
            prev_cx, prev_cy = rooms[-1].center
            new_cx, new_cy = room.center
            if rng.random() < 0.5:
                _carve_wide_h_tunnel(game_map, prev_cx, new_cx, prev_cy, floor_tile)
                _carve_wide_v_tunnel(game_map, prev_cy, new_cy, new_cx, floor_tile)
            else:
                _carve_wide_v_tunnel(game_map, prev_cy, new_cy, prev_cx, floor_tile)
                _carve_wide_h_tunnel(game_map, prev_cx, new_cx, new_cy, floor_tile)

        rooms.append(room)
        label_counts[spec.label] = label_counts.get(spec.label, 0) + 1

    return rooms


def _generate_village(
    game_map: GameMap,
    rng: random.Random,
    profile: LocationProfile,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> List[RectRoom]:
    """Colony village: open ground with walled buildings."""
    w, h = game_map.width, game_map.height
    rooms: List[RectRoom] = []
    label_counts: dict[str, int] = {}

    # Fill entire map with walkable ground
    game_map.tiles[:] = tile_types.ground

    # Border wall around map edges
    game_map.tiles[0, :] = wall_tile
    game_map.tiles[w - 1, :] = wall_tile
    game_map.tiles[:, 0] = wall_tile
    game_map.tiles[:, h - 1] = wall_tile

    # Place required rooms first, then fill
    all_specs: List[RoomSpec] = list(_required_specs(profile))

    for _ in range(profile.max_rooms * 4):
        if len(rooms) >= profile.max_rooms:
            break

        if all_specs:
            spec = all_specs.pop(0)
        else:
            spec = _pick_room_spec(rng, profile, label_counts)

        rw = rng.randint(spec.min_w, spec.max_w)
        rh = rng.randint(spec.min_h, spec.max_h)
        rx = rng.randint(2, max(2, w - rw - 3))
        ry = rng.randint(2, max(2, h - rh - 3))
        room = RectRoom(rx, ry, rw, rh, label=spec.label)

        # Check for overlap with 3-tile gap
        too_close = False
        for other in rooms:
            expanded = RectRoom(room.x1 - 3, room.y1 - 3, rw + 6, rh + 6)
            if expanded.intersects(other):
                too_close = True
                break
        if too_close:
            continue

        # Draw building: wall boundary, dirt floor interior
        for bx in range(room.x1, room.x2 + 1):
            for by in range(room.y1, room.y2 + 1):
                if not game_map.in_bounds(bx, by):
                    continue
                if bx == room.x1 or bx == room.x2 or by == room.y1 or by == room.y2:
                    game_map.tiles[bx, by] = wall_tile
                else:
                    game_map.tiles[bx, by] = floor_tile

        # Carve a 1-tile doorway on a random wall side
        side = rng.choice(["north", "south", "east", "west"])
        if side == "north" and room.x2 > room.x1 + 2:
            dx = rng.randint(room.x1 + 1, room.x2 - 1)
            if game_map.in_bounds(dx, room.y1):
                game_map.tiles[dx, room.y1] = floor_tile
        elif side == "south" and room.x2 > room.x1 + 2:
            dx = rng.randint(room.x1 + 1, room.x2 - 1)
            if game_map.in_bounds(dx, room.y2):
                game_map.tiles[dx, room.y2] = floor_tile
        elif side == "east" and room.y2 > room.y1 + 2:
            dy = rng.randint(room.y1 + 1, room.y2 - 1)
            if game_map.in_bounds(room.x2, dy):
                game_map.tiles[room.x2, dy] = floor_tile
        elif side == "west" and room.y2 > room.y1 + 2:
            dy = rng.randint(room.y1 + 1, room.y2 - 1)
            if game_map.in_bounds(room.x1, dy):
                game_map.tiles[room.x1, dy] = floor_tile

        rooms.append(room)
        label_counts[spec.label] = label_counts.get(spec.label, 0) + 1

    return rooms


# -------------------------------------------------------------------
# Generator dispatch
# -------------------------------------------------------------------

_GENERATORS = {
    "ship": _generate_ship,
    "organic": _generate_organic,
    "standard": _generate_standard,
    "village": _generate_village,
}


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------

def generate_dungeon(
    width: int = 80,
    height: int = 45,
    max_rooms: int = 12,
    room_min: int = 4,
    room_max: int = 10,
    seed: Optional[int] = None,
    max_enemies: int = 2,
    max_items: int = 1,
    loc_type: str = "derelict",
) -> Tuple[GameMap, List[RectRoom], Optional[Tuple[int, int]]]:
    """Returns (game_map, rooms, exit_pos)."""
    rng = random.Random(seed)
    profile = get_profile(loc_type)
    wall_tile = _resolve_tile(profile.wall_tile)
    floor_tile = _resolve_tile(profile.floor_tile)

    game_map = GameMap(width, height, fill_tile=wall_tile)
    game_map.fully_lit = profile.fully_lit
    game_map.fov_radius = profile.fov_radius
    gen_fn = _GENERATORS.get(profile.generator)
    if gen_fn:
        rooms = gen_fn(game_map, rng, profile, wall_tile, floor_tile)
    else:
        rooms = _generate_fallback(
            game_map, rng, max_rooms, room_min, room_max, floor_tile,
        )

    # Exit hatch at entrance so the player can always leave from where they entered.
    exit_pos: Optional[Tuple[int, int]] = None
    if rooms:
        exit_pos = rooms[0].center
        if game_map.in_bounds(exit_pos[0], exit_pos[1]):
            game_map.tiles[exit_pos[0], exit_pos[1]] = tile_types.exit_tile

    for room in rooms[1:]:
        _spawn_enemies(room, game_map, rng, max_enemies, exit_pos=exit_pos)
        _spawn_items(room, game_map, rng, max_items, exit_pos=exit_pos)

    # 1–3 interactables in random rooms (ship rooms get themed dressing instead,
    # but still place wall interactables for them)
    if rooms:
        if profile.generator == "ship":
            # Ship rooms already have floor dressing; only place wall interactables
            if profile.wall_interactable and len(rooms) > 1:
                for _ in range(rng.randint(1, 3)):
                    room = rng.choice(rooms[1:])
                    _spawn_interactables(
                        room, game_map, rng, count=1, hazard_chance=0.2,
                        wall_interactable_name=profile.wall_interactable,
                        exit_pos=exit_pos,
                    )
        else:
            num_interactables = rng.randint(1, 3)
            for _ in range(num_interactables):
                room = rng.choice(rooms[1:]) if len(rooms) > 1 else rooms[0]
                _spawn_interactables(
                    room, game_map, rng, count=1, hazard_chance=0.2,
                    wall_interactable_name=profile.wall_interactable,
                    exit_pos=exit_pos,
                )

    return game_map, rooms, exit_pos


def _generate_fallback(
    game_map: GameMap,
    rng: random.Random,
    max_rooms: int,
    room_min: int,
    room_max: int,
    floor_tile: np.ndarray,
) -> List[RectRoom]:
    """Original room-and-corridor algorithm as fallback."""
    rooms: List[RectRoom] = []
    w, h = game_map.width, game_map.height

    for _ in range(max_rooms * 3):
        if len(rooms) >= max_rooms:
            break
        rw = rng.randint(room_min, room_max)
        rh = rng.randint(room_min, max(room_min, room_max - 2))
        rx = rng.randint(1, max(1, w - rw - 2))
        ry = rng.randint(1, max(1, h - rh - 2))
        room = RectRoom(rx, ry, rw, rh)

        if any(room.intersects(other) for other in rooms):
            continue

        game_map.tiles[room.inner] = floor_tile

        if rooms:
            prev_cx, prev_cy = rooms[-1].center
            new_cx, new_cy = room.center
            if rng.random() < 0.5:
                _carve_h_tunnel(game_map, prev_cx, new_cx, prev_cy, floor_tile)
                _carve_v_tunnel(game_map, prev_cy, new_cy, new_cx, floor_tile)
            else:
                _carve_v_tunnel(game_map, prev_cy, new_cy, prev_cx, floor_tile)
                _carve_h_tunnel(game_map, prev_cx, new_cx, new_cy, floor_tile)

        rooms.append(room)
    return rooms


def respawn_creatures(
    game_map: GameMap,
    rooms: List[RectRoom],
    max_enemies: int = 2,
    seed: Optional[int] = None,
) -> None:
    """Remove all entities with AI (creatures) and spawn new ones in rooms[1:].
    Does not touch items or the map. Uses seed for deterministic placement if given.
    """
    game_map.entities[:] = [e for e in game_map.entities if not e.ai]
    rng = random.Random(seed)
    for room in rooms[1:]:
        _spawn_enemies(room, game_map, rng, max_enemies)
