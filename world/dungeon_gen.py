"""Procedural dungeon generation: room-and-corridor algorithm."""
from __future__ import annotations

import collections
import heapq
import random
from typing import List, Optional, Tuple

from world.game_map import GameMap
from world import tile_types
from world.loc_profiles import get_profile, LocationProfile, RoomSpec
from world.palettes import pick_biome, make_ground_tile, make_wall_tile, make_path_tile, apply_ground_noise, scatter_flora
from game.entity import Entity, Fighter
from game.ai import CreatureAI
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
    if y + 1 < game_map.height:
        _carve_h_tunnel(game_map, x1, x2, y + 1, floor_tile)


def _carve_wide_v_tunnel(
    game_map: GameMap, y1: int, y2: int, x: int,
    floor_tile: np.ndarray | None = None,
) -> None:
    """Carve a 2-tile wide vertical corridor."""
    _carve_v_tunnel(game_map, y1, y2, x, floor_tile)
    if x + 1 < game_map.width:
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

def _random_room_pos(room: RectRoom, rng: random.Random) -> Tuple[int, int]:
    """Pick a random floor position inside a room."""
    x = rng.randint(room.x1 + 1, max(room.x1 + 1, room.x2 - 1))
    y = rng.randint(room.y1 + 1, max(room.y1 + 1, room.y2 - 1))
    return x, y


MAX_ENEMIES_PER_ROOM = 3
MAX_ENEMIES_PER_LEVEL = 12


def _spawn_enemies(
    room: RectRoom, game_map: GameMap, rng: random.Random, max_enemies: int = 2,
    exit_pos: Optional[Tuple[int, int]] = None,
    remaining: Optional[int] = None,
) -> int:
    capped = min(max_enemies, MAX_ENEMIES_PER_ROOM)
    if remaining is not None:
        capped = min(capped, remaining)
    spawned = 0
    for _ in range(rng.randint(0, capped)):
        x, y = _random_room_pos(room, rng)
        if not game_map.in_bounds(x, y) or not game_map.tiles["walkable"][x, y]:
            continue
        if game_map.get_blocking_entity(x, y):
            continue
        if _near_exit(x, y, exit_pos):
            continue
        defn = rng.choice(db.enemies())
        ai_config = {
            k: defn[k] for k in (
                "ai_initial_state", "aggro_distance", "sleep_aggro_distance",
                "can_open_doors", "flee_threshold", "memory_turns", "vision_radius",
                "move_speed",
            ) if k in defn
        }
        entity = Entity(
            x=x, y=y, char=defn["char"], color=defn["color"], name=defn["name"],
            blocks_movement=True,
            fighter=Fighter(hp=defn["hp"], max_hp=defn["hp"],
                            defense=defn["defense"], power=defn["power"]),
            ai=CreatureAI(),
            organic=defn.get("organic", True),
        )
        entity.ai_config = ai_config
        entity.ai_state = ai_config.get("ai_initial_state", "wandering")
        game_map.entities.append(entity)
        spawned += 1
    return spawned


def _spawn_items(
    room: RectRoom, game_map: GameMap, rng: random.Random, max_items: int = 1,
    exit_pos: Optional[Tuple[int, int]] = None,
) -> None:
    for _ in range(rng.randint(0, max_items)):
        x, y = _random_room_pos(room, rng)
        if not game_map.in_bounds(x, y) or not game_map.tiles["walkable"][x, y]:
            continue
        if _near_exit(x, y, exit_pos):
            continue
        if game_map.get_blocking_entity(x, y) or game_map.get_non_blocking_entity_at(x, y):
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
    if not pool:
        return

    for _ in range(count):
        defn = rng.choice(pool)
        ch, color, name = defn["char"], defn["color"], defn["name"]
        is_wall = defn.get("placement") == "wall"

        if is_wall:
            candidates = [
                (wx, wy) for wx, wy in _room_wall_positions(room)
                if game_map.in_bounds(wx, wy)
                and not game_map.tiles["walkable"][wx, wy]
                and not game_map.get_non_blocking_entity_at(wx, wy)
                and not _near_exit(wx, wy, exit_pos)
            ]
            if not candidates:
                continue
            x, y = rng.choice(candidates)
        else:
            x, y = _random_room_pos(room, rng)
            if not game_map.in_bounds(x, y) or not game_map.tiles["walkable"][x, y]:
                continue
            if game_map.get_blocking_entity(x, y) or game_map.get_non_blocking_entity_at(x, y):
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


def _place_ship_corridor_lights(
    game_map: GameMap,
    spine_x1: int, spine_x2: int, spine_y: int, spine_y2: int,
    branches: List[Tuple[int, int, int]],
    rng: random.Random,
) -> None:
    """Place warm white lights along spine and branch corridors."""
    color = (200, 190, 170)
    radius = 4
    intensity = 0.5
    spacing = rng.randint(6, 8)

    # Along the spine
    for x in range(spine_x1, spine_x2 + 1, spacing):
        y = spine_y
        if game_map.in_bounds(x, y):
            game_map.add_light_source(x, y, radius=radius, color=color, intensity=intensity)

    # Along each branch
    for br_x, br_y_start, br_y_end in branches:
        for y in range(br_y_start, br_y_end + 1, spacing):
            if game_map.in_bounds(br_x, y):
                game_map.add_light_source(br_x, y, radius=radius, color=color, intensity=intensity)


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

    # Room fixture tiles — non-walkable light sources (placed first to block entity placement)
    cx, cy = room.center
    fixture_tile = None
    fixture_light = None
    if room.label == "engine_room":
        fixture_tile = tile_types.reactor_core
        fixture_light = {"radius": 7, "color": (120, 60, 220), "intensity": 0.9}
    elif room.label == "bridge":
        fixture_tile = tile_types.control_console
        fixture_light = {"radius": 5, "color": (80, 160, 255), "intensity": 0.7}

    if fixture_tile is not None:
        # Try center first, then offsets to avoid overwriting exit tile
        candidates = [(cx, cy)]
        for dist in range(1, 4):
            for dx in range(-dist, dist + 1):
                for dy in range(-dist, dist + 1):
                    if abs(dx) == dist or abs(dy) == dist:
                        candidates.append((cx + dx, cy + dy))
        for fx, fy in candidates:
            if (game_map.in_bounds(fx, fy)
                    and game_map.tiles["walkable"][fx, fy]
                    and (fx, fy) not in occupied
                    and not _near_exit(fx, fy, exit_pos)):
                game_map.tiles[fx, fy] = fixture_tile
                occupied.add((fx, fy))
                game_map.add_light_source(fx, fy, **fixture_light)
                break

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

def _load_hull_profile(
    rng: random.Random,
    map_width: int,
) -> Tuple[List[int], List[Tuple[int, int, str | None]], int]:
    """Pick random hull sections and concatenate into a full profile.

    Returns (profile, section_bounds, margin_x) where section_bounds is a list
    of (start_x_in_profile, end_x_in_profile, room_type) tuples.
    """
    from data.hull_templates import get_random_hull

    bow, mid, stern = get_random_hull(rng)
    profile = bow.profile + mid.profile + stern.profile
    margin_x = (map_width - len(profile)) // 2

    bow_end = len(bow.profile)
    mid_end = bow_end + len(mid.profile)
    stern_end = mid_end + len(stern.profile)

    section_bounds = [
        (0, bow_end, bow.room_type),
        (bow_end, mid_end, mid.room_type),
        (mid_end, stern_end, stern.room_type),
    ]
    return profile, section_bounds, margin_x


def _rasterize_hull(
    game_map: GameMap,
    profile: List[int],
    margin_x: int,
    center_y: int,
    wall_tile: np.ndarray,
) -> None:
    """Fill hull interior with wall tiles based on the profile.

    Hull is symmetric around center_y: top = center_y - half_w,
    bottom = center_y + half_w.
    """
    for i, half_w in enumerate(profile):
        x = margin_x + i
        if not game_map.in_bounds(x, 0):
            continue
        y_top = max(0, center_y - half_w)
        y_bot = min(game_map.height - 1, center_y + half_w)
        game_map.tiles[x, y_top:y_bot + 1] = wall_tile


def _carve_spine(
    game_map: GameMap,
    profile: List[int],
    margin_x: int,
    center_y: int,
    floor_tile: np.ndarray,
) -> Tuple[int, int, int]:
    """Carve a 3-tile-wide central spine corridor centered on center_y.

    Returns (spine_x1, spine_x2, spine_y) where spine_y is center_y - 1
    (the top row of the 3-wide corridor).
    """
    # Find first and last x where profile >= 3 (corridor + wall margin on each side)
    spine_x1 = None
    spine_x2 = None
    for i, half_w in enumerate(profile):
        if half_w >= 3:
            if spine_x1 is None:
                spine_x1 = margin_x + i
            spine_x2 = margin_x + i
    if spine_x1 is None:
        spine_x1 = margin_x
        spine_x2 = margin_x + len(profile) - 1

    # 3-wide: center_y - 1, center_y, center_y + 1
    for dy in (-1, 0, 1):
        _carve_h_tunnel(game_map, spine_x1, spine_x2, center_y + dy, floor_tile)
    return spine_x1, spine_x2, center_y - 1


def _place_rooms_in_hull(
    game_map: GameMap,
    rng: random.Random,
    profile_obj: "LocationProfile",
    hull_profile: List[int],
    section_bounds: List[Tuple[int, int, str | None]],
    margin_x: int,
    center_y: int,
    spine_y: int,
    floor_tile: np.ndarray,
) -> List[RectRoom]:
    """Place rooms inside the hull, respecting hull bounds with margin.

    Bridge/engine rooms are placed inline with the spine at the bow/stern.
    Mid rooms are placed in symmetric pairs above and below the spine.
    Returns list of placed rooms.
    """
    rooms: List[RectRoom] = []
    label_counts: dict[str, int] = {}
    h = game_map.height

    def _room_fits_hull(room: RectRoom) -> bool:
        """Check every column of the room is inside hull with 1-tile margin."""
        for x in range(room.x1, room.x2 + 1):
            xi = x - margin_x
            if xi < 0 or xi >= len(hull_profile):
                return False
            half_w = hull_profile[xi]
            if room.y1 < center_y - half_w + 1:
                return False
            if room.y2 > center_y + half_w - 1:
                return False
        return True

    def _try_place_inline(spec, x_lo, x_hi):
        """Place a room centered on spine midpoint (inline) in x range."""
        for _ in range(50):
            rw = rng.randint(spec.min_w, spec.max_w)
            rh = rng.randint(spec.min_h, spec.max_h)
            rx = _safe_randint(rng, max(1, x_lo), max(1, min(x_hi - rw, game_map.width - rw - 2)))
            if rx is None:
                continue
            ry = center_y - rh // 2
            room = RectRoom(rx, ry, rw, rh, label=spec.label)
            if any(room.intersects(r) for r in rooms):
                continue
            if not _room_fits_hull(room):
                continue
            return room
        return None

    def _try_place_above(spec, x_lo, x_hi):
        """Place a room above the spine."""
        for _ in range(50):
            rw = rng.randint(spec.min_w, spec.max_w)
            rh = rng.randint(spec.min_h, spec.max_h)
            rx = _safe_randint(rng, max(1, x_lo), max(1, min(x_hi - rw, game_map.width - rw - 2)))
            if rx is None:
                continue
            xi = max(0, min(rx - margin_x, len(hull_profile) - 1))
            half_w = hull_profile[xi]
            ry = _safe_randint(rng,
                               max(1, center_y - half_w + 1),
                               max(1, center_y - 1 - rh))
            if ry is None:
                continue
            room = RectRoom(rx, ry, rw, rh, label=spec.label)
            if any(room.intersects(r) for r in rooms):
                continue
            if not _room_fits_hull(room):
                continue
            return room
        return None

    def _mirror_room(room: RectRoom) -> Optional[RectRoom]:
        """Create a mirrored copy of a room below the spine."""
        mirror_y1 = 2 * center_y - room.y2
        rw = room.x2 - room.x1
        rh = room.y2 - room.y1
        mirror = RectRoom(room.x1, mirror_y1, rw, rh, label=room.label)
        if any(mirror.intersects(r) for r in rooms):
            return None
        if not _room_fits_hull(mirror):
            return None
        return mirror

    # Place required rooms inline with spine at section termini
    for sec_start, sec_end, room_type in section_bounds:
        if room_type is None:
            continue
        spec = next((s for s in profile_obj.room_specs if s.label == room_type), None)
        if spec is None:
            continue
        if label_counts.get(room_type, 0) >= 1:
            continue
        x_lo = margin_x + sec_start
        x_hi = margin_x + sec_end
        room = _try_place_inline(spec, x_lo, x_hi)
        if room:
            game_map.tiles[room.inner] = floor_tile
            rooms.append(room)
            label_counts[room_type] = 1

    # Place remaining rooms in symmetric pairs in the mid section
    fill_specs = [s for s in profile_obj.room_specs if not s.required]
    mid_start, mid_end, _ = section_bounds[1]
    x_lo = margin_x + mid_start
    x_hi = margin_x + mid_end

    # Guarantee one of each non-required room type first (as symmetric pairs)
    for spec in fill_specs:
        if len(rooms) >= profile_obj.max_rooms:
            break
        above = _try_place_above(spec, x_lo, x_hi)
        if above:
            game_map.tiles[above.inner] = floor_tile
            rooms.append(above)
            label_counts[spec.label] = label_counts.get(spec.label, 0) + 1
            # Mirror below
            if len(rooms) < profile_obj.max_rooms:
                below = _mirror_room(above)
                if below:
                    game_map.tiles[below.inner] = floor_tile
                    rooms.append(below)
                    label_counts[spec.label] = label_counts.get(spec.label, 0) + 1

    # Fill remaining up to max (symmetric pairs)
    for _ in range(profile_obj.max_rooms * 3):
        if len(rooms) >= profile_obj.max_rooms:
            break
        spec = _pick_room_spec(rng, profile_obj, label_counts, allowed_specs=fill_specs)
        above = _try_place_above(spec, x_lo, x_hi)
        if above:
            game_map.tiles[above.inner] = floor_tile
            rooms.append(above)
            label_counts[spec.label] = label_counts.get(spec.label, 0) + 1
            if len(rooms) < profile_obj.max_rooms:
                below = _mirror_room(above)
                if below:
                    game_map.tiles[below.inner] = floor_tile
                    rooms.append(below)
                    label_counts[spec.label] = label_counts.get(spec.label, 0) + 1

    return rooms


def _connect_room_to_spine(
    game_map: GameMap,
    room: RectRoom,
    spine_x1: int, spine_x2: int, spine_y: int,
    floor_tile: np.ndarray,
) -> Optional[Tuple[int, int, int]]:
    """Connect a room to the spine via an L-shaped corridor.

    Returns (x, y_start, y_end) describing the vertical branch, or None.
    """
    cx, cy = room.center
    sx = max(spine_x1, min(cx, spine_x2))
    # Horizontal from room center to spine x
    _carve_h_tunnel(game_map, cx, sx, cy, floor_tile)
    # Vertical from room cy to spine (3-wide: spine_y to spine_y+2)
    _carve_v_tunnel(game_map, cy, spine_y + 1, sx, floor_tile)
    y_start = min(cy, spine_y)
    y_end = max(cy, spine_y + 2)
    return (sx, y_start, y_end)


def _generate_ship(
    game_map: GameMap,
    rng: random.Random,
    profile: LocationProfile,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> List[RectRoom]:
    """Hull-profile-based ship layout for derelicts.

    Defines an intentional ship-shaped hull first (bow + mid + stern),
    rasterizes it as solid wall, then carves spine corridor and rooms inside.
    """
    w, h = game_map.width, game_map.height
    center_y = h // 2

    # Step 1: Load hull profile
    hull_profile, section_bounds, margin_x = _load_hull_profile(rng, w)

    # Step 2: Rasterize hull as solid wall
    _rasterize_hull(game_map, hull_profile, margin_x, center_y, wall_tile)

    # Step 3: Carve central spine corridor
    spine_x1, spine_x2, spine_y = _carve_spine(
        game_map, hull_profile, margin_x, center_y, floor_tile,
    )

    # Store hull info on game_map for airlock placement and lights
    game_map.spine_y = spine_y
    game_map.hull_profile = hull_profile
    game_map.hull_margin_x = margin_x

    # Step 4: Place rooms inside hull bounds
    rooms = _place_rooms_in_hull(
        game_map, rng, profile, hull_profile, section_bounds,
        margin_x, center_y, spine_y, floor_tile,
    )

    # Step 5: Connect rooms to spine, collect branch corridors
    branches: List[Tuple[int, int, int]] = []
    for room in rooms:
        branch = _connect_room_to_spine(
            game_map, room, spine_x1, spine_x2, spine_y, floor_tile,
        )
        if branch:
            branches.append(branch)

    game_map.branches = branches

    # Step 6: Room-to-room connections (~30% chance for close pairs)
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            ci = rooms[i].center
            cj = rooms[j].center
            dist = abs(ci[0] - cj[0]) + abs(ci[1] - cj[1])
            if dist <= 12 and rng.random() < 0.3:
                _carve_h_tunnel(game_map, ci[0], cj[0], ci[1], floor_tile)
                _carve_v_tunnel(game_map, ci[1], cj[1], cj[0], floor_tile)

    # Step 7: Place windows on room walls facing corridors
    corridor_tid = int(floor_tile["tile_id"])
    for room in rooms:
        _place_building_windows(
            game_map, rng, [room], wall_tile, floor_tile,
            outside_tid=corridor_tid,
        )

    # Step 8: Place windows on hull-facing walls (exterior)
    _place_ship_exterior_windows(game_map, rng, rooms, wall_tile, floor_tile)

    # Step 9: Room-specific dressing for all rooms
    exit_pos = rooms[0].center if rooms else None
    for room in rooms:
        _dress_ship_room(room, game_map, rng, exit_pos=exit_pos)

    # Step 10: Corridor lights along spine and branches
    _place_ship_corridor_lights(
        game_map, spine_x1, spine_x2, spine_y, spine_y + 2, branches, rng,
    )

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

    # Sparse bioluminescent / mineral glow in caverns
    for room in rooms:
        cx, cy = room.center
        if room.label == "cavern":
            game_map.add_light_source(cx, cy, radius=5, color=(40, 80, 60), intensity=0.4)
        elif room.label == "shaft":
            game_map.add_light_source(cx, cy, radius=3, color=(60, 50, 30), intensity=0.3)

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

    # Place windows on room walls facing corridors
    corridor_tid = int(floor_tile["tile_id"])
    for room in rooms:
        _place_building_windows(
            game_map, rng, [room], wall_tile, floor_tile,
            outside_tid=corridor_tid,
        )

    # Place windows on walls facing the hull (uncarved wall fill)
    _place_exterior_windows(game_map, rng, wall_tile, floor_tile)

    # Room lights for starbase
    for room in rooms:
        cx, cy = room.center
        if room.label == "control_room":
            game_map.add_light_source(cx, cy, radius=5, color=(80, 160, 255), intensity=0.6)
        elif room.label == "trade_area":
            game_map.add_light_source(cx, cy, radius=6, color=(200, 190, 150), intensity=0.6)
        elif room.label == "dock":
            game_map.add_light_source(cx, cy, radius=5, color=(160, 140, 100), intensity=0.4)
        elif room.label == "cargo":
            game_map.add_light_source(cx, cy, radius=4, color=(160, 140, 100), intensity=0.3)

    return rooms


def _carve_room_interior(
    game_map: GameMap,
    x1: int, y1: int, x2: int, y2: int,
    floor_tile: np.ndarray,
) -> None:
    """Carve the interior of a room bounded by outer walls at (x1,y1)-(x2,y2)."""
    for bx in range(x1 + 1, x2):
        for by in range(y1 + 1, y2):
            if game_map.in_bounds(bx, by):
                game_map.tiles[bx, by] = floor_tile


def _find_door_position_v(
    game_map: GameMap,
    rng: random.Random,
    split_x: int, y1: int, y2: int,
) -> Optional[int]:
    """Find a y-position for a door through a vertical partition at split_x.

    Prefers positions where both adjacent tiles (split_x-1, split_x+1) are
    already walkable, producing a clean 1-tile doorway.  Falls back to any
    valid position if none are ideal.
    """
    lo, hi = y1 + 2, y2 - 2
    if lo > hi:
        return None
    good = [
        y for y in range(lo, hi + 1)
        if (game_map.in_bounds(split_x - 1, y)
            and game_map.tiles["walkable"][split_x - 1, y]
            and game_map.in_bounds(split_x + 1, y)
            and game_map.tiles["walkable"][split_x + 1, y])
    ]
    if good:
        return rng.choice(good)
    return rng.randint(lo, hi)


def _find_door_position_h(
    game_map: GameMap,
    rng: random.Random,
    split_y: int, x1: int, x2: int,
) -> Optional[int]:
    """Find an x-position for a door through a horizontal partition at split_y.

    Same logic as the vertical variant but for a horizontal wall.
    """
    lo, hi = x1 + 2, x2 - 2
    if lo > hi:
        return None
    good = [
        x for x in range(lo, hi + 1)
        if (game_map.in_bounds(x, split_y - 1)
            and game_map.tiles["walkable"][x, split_y - 1]
            and game_map.in_bounds(x, split_y + 1)
            and game_map.tiles["walkable"][x, split_y + 1])
    ]
    if good:
        return rng.choice(good)
    return rng.randint(lo, hi)


def _subdivide_building(
    game_map: GameMap,
    rng: random.Random,
    x1: int, y1: int, x2: int, y2: int,
    num_rooms: int,
    floor_tile: np.ndarray,
    wall_tile: np.ndarray,
    label: str = "",
) -> List[RectRoom]:
    """Recursively subdivide a building footprint into rooms with internal doors.

    (x1, y1) and (x2, y2) are the outer wall coordinates of this sub-area.
    Interior is (x1+1..x2-1, y1+1..y2-1).
    Returns a list of RectRooms representing each carved sub-room.
    """
    inner_w = x2 - x1 - 1
    inner_h = y2 - y1 - 1

    # Min sub-room interior 3×3 → each half needs outer width ≥ 4 → min_offset 4
    min_offset = 4
    can_split_v = inner_w >= (min_offset * 2 - 1)  # vertical partition (split x)
    can_split_h = inner_h >= (min_offset * 2 - 1)  # horizontal partition (split y)

    # Base case: single room
    if num_rooms <= 1 or (not can_split_v and not can_split_h):
        _carve_room_interior(game_map, x1, y1, x2, y2, floor_tile)
        return [RectRoom(x1, y1, x2 - x1, y2 - y1, label=label)]

    # Choose split axis from viable options; prefer longer dimension
    if can_split_v and can_split_h:
        if inner_w > inner_h:
            axis = "vertical"
        elif inner_h > inner_w:
            axis = "horizontal"
        else:
            axis = rng.choice(["vertical", "horizontal"])
    elif can_split_v:
        axis = "vertical"
    else:
        axis = "horizontal"

    if axis == "vertical":
        lo = x1 + min_offset
        hi = x2 - min_offset

        # Asymmetric split: when we need >2 rooms, push the partition
        # toward one side so the larger half can subdivide further.
        if num_rooms > 2:
            if rng.random() < 0.5:
                split_x = lo  # small left, big right
            else:
                split_x = hi  # big left, small right
        else:
            split_x = rng.randint(lo, hi)

        # Draw partition wall
        for by in range(y1 + 1, y2):
            if game_map.in_bounds(split_x, by):
                game_map.tiles[split_x, by] = wall_tile

        # Assign room counts: give 1 to the smaller half, rest to the bigger
        left_w = split_x - x1
        right_w = x2 - split_x
        if left_w >= right_w:
            left_count = num_rooms - 1
            right_count = 1
        else:
            left_count = 1
            right_count = num_rooms - 1
        # For 2-room case keep even split
        if num_rooms == 2:
            left_count = right_count = 1

        left_rooms = _subdivide_building(
            game_map, rng, x1, y1, split_x, y2,
            left_count, floor_tile, wall_tile, label,
        )
        right_rooms = _subdivide_building(
            game_map, rng, split_x, y1, x2, y2,
            right_count, floor_tile, wall_tile, label,
        )

        # Carve a 1-tile doorway, preferring positions with floor on both sides
        door_y = _find_door_position_v(game_map, rng, split_x, y1, y2)
        if door_y is not None:
            game_map.tiles[split_x, door_y] = floor_tile
            # Only force-clear a side if it's still walled (perpendicular partition)
            # but never breach the building's outer boundary walls
            if (split_x - 1 > x1
                    and game_map.in_bounds(split_x - 1, door_y)
                    and not game_map.tiles["walkable"][split_x - 1, door_y]):
                game_map.tiles[split_x - 1, door_y] = floor_tile
            if (split_x + 1 < x2
                    and game_map.in_bounds(split_x + 1, door_y)
                    and not game_map.tiles["walkable"][split_x + 1, door_y]):
                game_map.tiles[split_x + 1, door_y] = floor_tile

        return left_rooms + right_rooms

    else:  # horizontal
        lo = y1 + min_offset
        hi = y2 - min_offset

        if num_rooms > 2:
            if rng.random() < 0.5:
                split_y = lo
            else:
                split_y = hi
        else:
            split_y = rng.randint(lo, hi)

        for bx in range(x1 + 1, x2):
            if game_map.in_bounds(bx, split_y):
                game_map.tiles[bx, split_y] = wall_tile

        top_h = split_y - y1
        bot_h = y2 - split_y
        if top_h >= bot_h:
            top_count = num_rooms - 1
            bot_count = 1
        else:
            top_count = 1
            bot_count = num_rooms - 1
        if num_rooms == 2:
            top_count = bot_count = 1

        top_rooms = _subdivide_building(
            game_map, rng, x1, y1, x2, split_y,
            top_count, floor_tile, wall_tile, label,
        )
        bot_rooms = _subdivide_building(
            game_map, rng, x1, split_y, x2, y2,
            bot_count, floor_tile, wall_tile, label,
        )

        door_x = _find_door_position_h(game_map, rng, split_y, x1, x2)
        if door_x is not None:
            game_map.tiles[door_x, split_y] = floor_tile
            # Never breach the building's outer boundary walls
            if (split_y - 1 > y1
                    and game_map.in_bounds(door_x, split_y - 1)
                    and not game_map.tiles["walkable"][door_x, split_y - 1]):
                game_map.tiles[door_x, split_y - 1] = floor_tile
            if (split_y + 1 < y2
                    and game_map.in_bounds(door_x, split_y + 1)
                    and not game_map.tiles["walkable"][door_x, split_y + 1]):
                game_map.tiles[door_x, split_y + 1] = floor_tile

        return top_rooms + bot_rooms


# Weighted wing count distribution for village buildings
_VILLAGE_WING_WEIGHTS = [(1, 40), (2, 45), (3, 15)]


def _pick_building_room_count(rng: random.Random) -> int:
    """Pick number of wings using weighted distribution."""
    total = sum(w for _, w in _VILLAGE_WING_WEIGHTS)
    roll = rng.randint(1, total)
    cumulative = 0
    for count, weight in _VILLAGE_WING_WEIGHTS:
        cumulative += weight
        if roll <= cumulative:
            return count
    return 1


def _compose_building_wings(
    rng: random.Random,
    main_x: int, main_y: int, main_w: int, main_h: int,
    num_wings: int,
    min_w: int = 5, min_h: int = 5,
) -> List[Tuple[int, int, int, int]]:
    """Return list of (x, y, w, h) rectangles forming a multi-wing building.

    The main wing is always first.  Secondary wings attach to random sides
    of the main wing with a random offset, producing L/T/U-shaped footprints.
    """
    wings = [(main_x, main_y, main_w, main_h)]
    if num_wings <= 1:
        return wings

    sides = ["north", "south", "east", "west"]
    rng.shuffle(sides)

    for i in range(num_wings - 1):
        side = sides[i % len(sides)]
        # Secondary wing dimensions: 60-80% of main, clamped to min
        sw = max(min_w, rng.randint(int(main_w * 0.6), max(int(main_w * 0.8), min_w)))
        sh = max(min_h, rng.randint(int(main_h * 0.6), max(int(main_h * 0.8), min_h)))

        # Minimum overlap of 3 tiles for a doorway
        min_overlap = 3
        if side in ("north", "south"):
            edge_len = main_w
            wing_edge = sw
            if wing_edge > edge_len:
                wing_edge = edge_len
                sw = wing_edge
            max_offset = max(0, edge_len - min_overlap)
            min_offset = max(0, wing_edge - edge_len + min_overlap)
            if min_offset > max_offset:
                # Can't get 3-tile overlap; just center it
                offset = max(0, (edge_len - wing_edge) // 2)
            else:
                offset = rng.randint(min(min_offset, max_offset), max(min_offset, max_offset))
            sx = main_x + offset
            if side == "north":
                sy = main_y - sh  # extends upward
            else:
                sy = main_y + main_h  # extends downward
            # Clamp offset so wing doesn't extend past main + wing width
            sx = min(sx, main_x + main_w - min_overlap)
            wings.append((sx, sy, sw, sh))
        else:  # east or west
            edge_len = main_h
            wing_edge = sh
            if wing_edge > edge_len:
                wing_edge = edge_len
                sh = wing_edge
            max_offset = max(0, edge_len - min_overlap)
            min_offset = max(0, wing_edge - edge_len + min_overlap)
            if min_offset > max_offset:
                offset = max(0, (edge_len - wing_edge) // 2)
            else:
                offset = rng.randint(min(min_offset, max_offset), max(min_offset, max_offset))
            sy = main_y + offset
            if side == "west":
                sx = main_x - sw  # extends left
            else:
                sx = main_x + main_w  # extends right
            sy = min(sy, main_y + main_h - min_overlap)
            wings.append((sx, sy, sw, sh))

    return wings


def _carve_wing_doorway(
    game_map: GameMap,
    wing_a: RectRoom, wing_b: RectRoom,
    floor_tile: np.ndarray,
) -> None:
    """Carve a 1-tile doorway through the shared wall between two adjacent wings.

    Two wings that share a side have an overlapping range of wall tiles.
    We find that overlap, carve the shared wall tile, and force-clear the
    tiles on both sides so internal partition walls don't block the passage.
    """

    def _clear_if_blocked(x: int, y: int) -> None:
        if (game_map.in_bounds(x, y)
                and not game_map.tiles["walkable"][x, y]):
            game_map.tiles[x, y] = floor_tile

    # A's east wall == B's west wall (x2a == x1b)
    if wing_a.x2 == wing_b.x1:
        y_lo = max(wing_a.y1 + 1, wing_b.y1 + 1)
        y_hi = min(wing_a.y2 - 1, wing_b.y2 - 1)
        if y_lo <= y_hi:
            door_y = (y_lo + y_hi) // 2
            x = wing_a.x2
            if game_map.in_bounds(x, door_y):
                game_map.tiles[x, door_y] = floor_tile
            _clear_if_blocked(x - 1, door_y)
            _clear_if_blocked(x + 1, door_y)
            return

    # A's west wall == B's east wall (x1a == x2b)
    if wing_a.x1 == wing_b.x2:
        y_lo = max(wing_a.y1 + 1, wing_b.y1 + 1)
        y_hi = min(wing_a.y2 - 1, wing_b.y2 - 1)
        if y_lo <= y_hi:
            door_y = (y_lo + y_hi) // 2
            x = wing_a.x1
            if game_map.in_bounds(x, door_y):
                game_map.tiles[x, door_y] = floor_tile
            _clear_if_blocked(x - 1, door_y)
            _clear_if_blocked(x + 1, door_y)
            return

    # A's south wall == B's north wall (y2a == y1b)
    if wing_a.y2 == wing_b.y1:
        x_lo = max(wing_a.x1 + 1, wing_b.x1 + 1)
        x_hi = min(wing_a.x2 - 1, wing_b.x2 - 1)
        if x_lo <= x_hi:
            door_x = (x_lo + x_hi) // 2
            y = wing_a.y2
            if game_map.in_bounds(door_x, y):
                game_map.tiles[door_x, y] = floor_tile
            _clear_if_blocked(door_x, y - 1)
            _clear_if_blocked(door_x, y + 1)
            return

    # A's north wall == B's south wall (y1a == y2b)
    if wing_a.y1 == wing_b.y2:
        x_lo = max(wing_a.x1 + 1, wing_b.x1 + 1)
        x_hi = min(wing_a.x2 - 1, wing_b.x2 - 1)
        if x_lo <= x_hi:
            door_x = (x_lo + x_hi) // 2
            y = wing_a.y1
            if game_map.in_bounds(door_x, y):
                game_map.tiles[door_x, y] = floor_tile
            _clear_if_blocked(door_x, y - 1)
            _clear_if_blocked(door_x, y + 1)
            return


def _carve_external_door(
    game_map: GameMap,
    rng: random.Random,
    wing_rooms: List[RectRoom],
    floor_tile: np.ndarray,
) -> Optional[Tuple[int, int]]:
    """Carve a 1-tile door on a building's outer wall.

    Iterates over all wing perimeter tiles and picks ones that face outward
    (adjacent to a ground tile), so the door connects the building to the
    outside.  Prefers positions where the inside tile is already walkable.

    Returns the (x, y) of the ground tile just outside the door, or None.
    """
    ground_tid = int(tile_types.ground["tile_id"])

    # Collect all wall tiles across all wings with their inward direction
    # Each entry: (wall_pos, inside_pos, outside_pos)
    door_candidates: List[Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]] = []
    for wing in wing_rooms:
        # North wall
        for x in range(wing.x1 + 1, wing.x2):
            wall = (x, wing.y1)
            inside = (x, wing.y1 + 1)
            outside = (x, wing.y1 - 1)
            if (game_map.in_bounds(*outside)
                    and int(game_map.tiles["tile_id"][outside[0], outside[1]]) == ground_tid):
                door_candidates.append((wall, inside, outside))
        # South wall
        for x in range(wing.x1 + 1, wing.x2):
            wall = (x, wing.y2)
            inside = (x, wing.y2 - 1)
            outside = (x, wing.y2 + 1)
            if (game_map.in_bounds(*outside)
                    and int(game_map.tiles["tile_id"][outside[0], outside[1]]) == ground_tid):
                door_candidates.append((wall, inside, outside))
        # West wall
        for y in range(wing.y1 + 1, wing.y2):
            wall = (wing.x1, y)
            inside = (wing.x1 + 1, y)
            outside = (wing.x1 - 1, y)
            if (game_map.in_bounds(*outside)
                    and int(game_map.tiles["tile_id"][outside[0], outside[1]]) == ground_tid):
                door_candidates.append((wall, inside, outside))
        # East wall
        for y in range(wing.y1 + 1, wing.y2):
            wall = (wing.x2, y)
            inside = (wing.x2 - 1, y)
            outside = (wing.x2 + 1, y)
            if (game_map.in_bounds(*outside)
                    and int(game_map.tiles["tile_id"][outside[0], outside[1]]) == ground_tid):
                door_candidates.append((wall, inside, outside))

    # Prefer positions where the inside tile is already walkable floor
    good = [
        (wall, inside, outside) for wall, inside, outside in door_candidates
        if (game_map.in_bounds(*wall) and game_map.in_bounds(*inside)
            and game_map.tiles["walkable"][inside[0], inside[1]])
    ]
    if good:
        wall_pos, _, outside_pos = rng.choice(good)
        game_map.tiles[wall_pos[0], wall_pos[1]] = floor_tile
        return outside_pos
    elif door_candidates:
        # Fallback: pick any position, force-clear the inside tile too
        wall_pos, inside_pos, outside_pos = rng.choice(door_candidates)
        if game_map.in_bounds(*wall_pos):
            game_map.tiles[wall_pos[0], wall_pos[1]] = floor_tile
        if game_map.in_bounds(*inside_pos):
            game_map.tiles[inside_pos[0], inside_pos[1]] = floor_tile
        return outside_pos
    return None


def _place_exterior_windows(
    game_map: GameMap,
    rng: random.Random,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> None:
    """Place window tiles on walls facing the hull (uncarved wall fill).

    Scans all wall tiles (excluding map border). A tile is a candidate if it
    has walkable floor on one side and more wall (hull) on the opposite side.
    Candidates are grouped into contiguous segments by orientation, then
    windows are placed with context-aware sizing.
    """
    w, h = game_map.width, game_map.height
    wall_tid = int(wall_tile["tile_id"])

    # Direction pairs: (dx, dy) for the inside (floor) side;
    # opposite direction is the outside (hull) side.
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]

    # Collect candidates: map (x,y) -> (inside_dx, inside_dy)
    # If a tile qualifies in multiple directions, keep only the first.
    candidates: dict[Tuple[int, int], Tuple[int, int]] = {}

    for x in range(1, w - 1):
        for y in range(1, h - 1):
            if int(game_map.tiles["tile_id"][x, y]) != wall_tid:
                continue
            for dx, dy in directions:
                inside_x, inside_y = x + dx, y + dy
                outside_x, outside_y = x - dx, y - dy
                if not game_map.in_bounds(inside_x, inside_y):
                    continue
                if not game_map.in_bounds(outside_x, outside_y):
                    continue
                if not game_map.tiles["walkable"][inside_x, inside_y]:
                    continue
                if int(game_map.tiles["tile_id"][outside_x, outside_y]) != wall_tid:
                    continue
                if (x, y) not in candidates:
                    candidates[(x, y)] = (dx, dy)
                break

    # Group candidates into contiguous segments sharing orientation.
    # Horizontal segments: same y and same (dx,dy), consecutive x.
    # Vertical segments: same x and same (dx,dy), consecutive y.
    # Sort by orientation, then by row/col.
    by_orient: dict[Tuple[int, int], list[Tuple[int, int]]] = {}
    for (x, y), direction in candidates.items():
        by_orient.setdefault(direction, []).append((x, y))

    all_segments: list[list[Tuple[int, int]]] = []
    for direction, positions in by_orient.items():
        dx, dy = direction
        if dx == 0:
            # Wall faces north/south — segments run horizontally (same y, consecutive x)
            by_row: dict[int, list[int]] = {}
            for x, y in positions:
                by_row.setdefault(y, []).append(x)
            for row_y, xs in by_row.items():
                xs.sort()
                seg: list[Tuple[int, int]] = [(xs[0], row_y)]
                for i in range(1, len(xs)):
                    if xs[i] == xs[i - 1] + 1:
                        seg.append((xs[i], row_y))
                    else:
                        all_segments.append(seg)
                        seg = [(xs[i], row_y)]
                all_segments.append(seg)
        else:
            # Wall faces east/west — segments run vertically (same x, consecutive y)
            by_col: dict[int, list[int]] = {}
            for x, y in positions:
                by_col.setdefault(x, []).append(y)
            for col_x, ys in by_col.items():
                ys.sort()
                seg = [(col_x, ys[0])]
                for i in range(1, len(ys)):
                    if ys[i] == ys[i - 1] + 1:
                        seg.append((col_x, ys[i]))
                    else:
                        all_segments.append(seg)
                        seg = [(col_x, ys[i])]
                all_segments.append(seg)

    # Place windows per segment with context-aware sizing
    for seg in all_segments:
        n = len(seg)
        if n < 2:
            continue
        if n <= 3:
            count = 1
        elif n <= 5:
            count = 2
        elif n <= 8:
            count = 3
        else:
            count = 5
        start = (n - count) // 2
        for i in range(start, start + count):
            x, y = seg[i]
            game_map.tiles[x, y] = tile_types.structure_window


def _place_ship_exterior_windows(
    game_map: GameMap,
    rng: random.Random,
    rooms: List[RectRoom],
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> None:
    """Place hull-facing windows on ship rooms.

    Bridge rooms get larger observation windows on forward (west) and side
    (north/south) walls. Other rooms get small portholes (1-2 max) on any
    hull-facing wall.
    """
    w, h = game_map.width, game_map.height
    wall_tid = int(wall_tile["tile_id"])

    # Direction pairs: (dx, dy) for the inside (floor) side
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]

    # Collect hull-facing candidates with their room association
    # candidate -> (inside_direction, room)
    candidates: dict[Tuple[int, int], Tuple[Tuple[int, int], RectRoom]] = {}

    for x in range(1, w - 1):
        for y in range(1, h - 1):
            if int(game_map.tiles["tile_id"][x, y]) != wall_tid:
                continue
            for dx, dy in directions:
                inside_x, inside_y = x + dx, y + dy
                outside_x, outside_y = x - dx, y - dy
                if not game_map.in_bounds(inside_x, inside_y):
                    continue
                if not game_map.in_bounds(outside_x, outside_y):
                    continue
                if not game_map.tiles["walkable"][inside_x, inside_y]:
                    continue
                if int(game_map.tiles["tile_id"][outside_x, outside_y]) != wall_tid:
                    continue

                # Find which room this wall belongs to
                room = None
                for r in rooms:
                    if (r.x1 <= x <= r.x2 and r.y1 <= y <= r.y2):
                        room = r
                        break
                if room is None:
                    continue

                # Filter by room type and direction
                # dx, dy is direction from wall to inside (floor side)
                # So the wall faces *away* from inside, i.e. toward (-dx, -dy)
                # Wall facing west (forward): outside is to the west, inside east
                #   -> dx=1, dy=0 (inside is east of wall)
                # Wall facing north: outside north, inside south -> dx=0, dy=1
                # Wall facing south: outside south, inside north -> dx=0, dy=-1
                # Wall facing east (aft): outside east, inside west -> dx=-1, dy=0
                if room.label == "bridge":
                    # Bridge: allow west (forward), north, south — no aft (east)
                    # Aft-facing wall: inside is west (dx=-1), so block dx=-1
                    if dx == -1 and dy == 0:
                        continue  # skip aft-facing bridge windows
                else:
                    pass  # other rooms: allow all hull-facing directions

                if (x, y) not in candidates:
                    candidates[(x, y)] = ((dx, dy), room)
                break

    # Group candidates by (room, orientation) for segment building
    grouped: dict[Tuple[str, Tuple[int, int]], list[Tuple[int, int]]] = {}
    for (x, y), ((dx, dy), room) in candidates.items():
        key = (id(room), room.label, (dx, dy))
        # Use a hashable key that includes room identity
        group_key = (room.label + str(id(room)), (dx, dy))
        grouped.setdefault(group_key, []).append((x, y))

    # Build segments and place windows
    for (room_key, direction), positions in grouped.items():
        is_bridge = room_key.startswith("bridge")
        segments = _split_into_segments(positions)
        for seg in segments:
            n = len(seg)
            if n < 2:
                continue
            if is_bridge:
                # Bridge: fill entire segment (observation windows)
                count = n
            else:
                # Other rooms: porthole sizing
                if n <= 4:
                    count = 1
                else:
                    count = 2
            start = (n - count) // 2
            # Look up the hull direction for this group from any candidate
            sample = seg[0]
            (sdx, sdy), _ = candidates[sample]
            hull_dx, hull_dy = -sdx, -sdy  # direction toward hull
            for i in range(start, start + count):
                x, y = seg[i]
                game_map.tiles[x, y] = tile_types.structure_window
                # Also replace the hull wall outside so the window isn't blocked
                hx, hy = x + hull_dx, y + hull_dy
                if game_map.in_bounds(hx, hy):
                    game_map.tiles[hx, hy] = tile_types.structure_window


def _place_building_windows(
    game_map: GameMap,
    rng: random.Random,
    wing_rects: List[RectRoom],
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
    outside_tid: Optional[int] = None,
) -> None:
    """Place window tiles on exterior walls of rooms/buildings.

    Scans each rect's 4 exterior edges (excluding corners), identifies
    candidate wall tiles that face *outside_tid* outside and walkable floor
    inside, groups them into contiguous segments, then places centered
    window tile(s) per segment.

    *outside_tid* defaults to ground for colony buildings; pass
    ``int(floor_tile["tile_id"])`` for ship/starbase corridors.
    """
    wall_tid = int(wall_tile["tile_id"])
    if outside_tid is None:
        outside_tid = int(tile_types.ground["tile_id"])

    # Collect candidate positions per side, grouped by wing & direction
    # Each candidate: (x, y)
    # Directions: outside_dx/dy tells which way is outside
    sides: list[list[Tuple[int, int]]] = []

    for wing in wing_rects:
        # North wall: y=wing.y1, x in (x1+1 .. x2-1), outside = y-1
        north = []
        for x in range(wing.x1 + 1, wing.x2):
            pos = (x, wing.y1)
            outside = (x, wing.y1 - 1)
            inside = (x, wing.y1 + 1)
            if _is_window_candidate(game_map, pos, outside, inside, wall_tid, outside_tid):
                north.append(pos)
        sides.append(north)

        # South wall: y=wing.y2, outside = y+1
        south = []
        for x in range(wing.x1 + 1, wing.x2):
            pos = (x, wing.y2)
            outside = (x, wing.y2 + 1)
            inside = (x, wing.y2 - 1)
            if _is_window_candidate(game_map, pos, outside, inside, wall_tid, outside_tid):
                south.append(pos)
        sides.append(south)

        # West wall: x=wing.x1, outside = x-1
        west = []
        for y in range(wing.y1 + 1, wing.y2):
            pos = (wing.x1, y)
            outside = (wing.x1 - 1, y)
            inside = (wing.x1 + 1, y)
            if _is_window_candidate(game_map, pos, outside, inside, wall_tid, outside_tid):
                west.append(pos)
        sides.append(west)

        # East wall: x=wing.x2, outside = x+1
        east = []
        for y in range(wing.y1 + 1, wing.y2):
            pos = (wing.x2, y)
            outside = (wing.x2 + 1, y)
            inside = (wing.x2 - 1, y)
            if _is_window_candidate(game_map, pos, outside, inside, wall_tid, outside_tid):
                east.append(pos)
        sides.append(east)

    # For each side, split candidates into contiguous segments and place windows
    for candidates in sides:
        if not candidates:
            continue
        segments = _split_into_segments(candidates)
        for seg in segments:
            _place_centered_windows(game_map, seg)


def _is_window_candidate(
    game_map: GameMap,
    pos: Tuple[int, int],
    outside: Tuple[int, int],
    inside: Tuple[int, int],
    wall_tid: int,
    outside_tid: int,
) -> bool:
    """Check if a wall tile qualifies as a window candidate."""
    if not game_map.in_bounds(*outside) or not game_map.in_bounds(*inside):
        return False
    if int(game_map.tiles["tile_id"][pos[0], pos[1]]) != wall_tid:
        return False
    if int(game_map.tiles["tile_id"][outside[0], outside[1]]) != outside_tid:
        return False
    if not game_map.tiles["walkable"][inside[0], inside[1]]:
        return False
    return True


def _split_into_segments(
    candidates: list[Tuple[int, int]],
) -> list[list[Tuple[int, int]]]:
    """Split a list of positions into contiguous segments.

    Positions are contiguous if they differ by 1 in either x or y
    (they'll all share one axis since they're on the same wall side).
    """
    if not candidates:
        return []
    segments: list[list[Tuple[int, int]]] = [[candidates[0]]]
    for pos in candidates[1:]:
        prev = segments[-1][-1]
        if abs(pos[0] - prev[0]) + abs(pos[1] - prev[1]) == 1:
            segments[-1].append(pos)
        else:
            segments.append([pos])
    return segments


def _place_centered_windows(
    game_map: GameMap,
    segment: list[Tuple[int, int]],
) -> None:
    """Place centered window tile(s) in a wall segment."""
    n = len(segment)
    if n < 3:
        return  # too narrow

    if n <= 4:
        count = 1
    elif n <= 6:
        count = 2
    else:
        count = 3

    start = (n - count) // 2
    for i in range(start, start + count):
        x, y = segment[i]
        game_map.tiles[x, y] = tile_types.structure_window


# -------------------------------------------------------------------
# Village path generation
# -------------------------------------------------------------------

def _wall_adjacent_set(game_map: GameMap, ground_tid: int) -> set:
    """Return set of ground tiles with at least one cardinal wall neighbor."""
    w, h = game_map.width, game_map.height
    wall_tid = int(tile_types.structure_wall["tile_id"])
    result: set = set()
    for x in range(w):
        for y in range(h):
            if int(game_map.tiles["tile_id"][x, y]) != ground_tid:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and int(game_map.tiles["tile_id"][nx, ny]) == wall_tid:
                    result.add((x, y))
                    break
    return result


def _bfs_path(
    game_map: GameMap,
    start: Tuple[int, int],
    end: Tuple[int, int],
    ground_tid: int,
    extra_walkable: Optional[set] = None,
    wall_cost: int = 3,
) -> List[Tuple[int, int]]:
    """Dijkstra shortest path from *start* to *end* through ground tiles.

    *extra_walkable* tiles may be traversed but are NOT target destinations.
    Delegates to ``_bfs_to_set`` with *end* as the sole target.
    """
    extra = extra_walkable or set()
    return _bfs_to_set(
        game_map, start, {end}, ground_tid, wall_cost,
        extra_walkable=extra,
    )


def _bfs_to_set(
    game_map: GameMap,
    start: Tuple[int, int],
    targets: set,
    ground_tid: int,
    wall_cost: int = 3,
    extra_walkable: Optional[set] = None,
) -> List[Tuple[int, int]]:
    """Dijkstra from *start* to the nearest coordinate in *targets*.

    *extra_walkable* tiles may be traversed but are not destinations.
    Wall-adjacent tiles cost *wall_cost* to traverse.  Returns ordered path,
    or [] if unreachable.
    """
    if start in targets:
        return [start]
    w, h = game_map.width, game_map.height
    sx, sy = start
    if not (0 <= sx < w and 0 <= sy < h):
        return []
    walkable = targets | (extra_walkable or set())
    wall_adj = _wall_adjacent_set(game_map, ground_tid)
    heap: List[Tuple[int, int, int]] = [(0, sx, sy)]
    best_cost: dict[Tuple[int, int], int] = {start: 0}
    came_from: dict[Tuple[int, int], Tuple[int, int] | None] = {start: None}
    while heap:
        cost, cx, cy = heapq.heappop(heap)
        if (cx, cy) in targets:
            path: List[Tuple[int, int]] = []
            cur: Tuple[int, int] | None = (cx, cy)
            while cur is not None:
                path.append(cur)
                cur = came_from[cur]
            path.reverse()
            return path
        if cost > best_cost.get((cx, cy), float("inf")):
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if (nx, ny) not in walkable and int(game_map.tiles["tile_id"][nx, ny]) != ground_tid:
                continue
            step = wall_cost if (nx, ny) in wall_adj else 1
            new_cost = cost + step
            if new_cost < best_cost.get((nx, ny), float("inf")):
                best_cost[(nx, ny)] = new_cost
                came_from[(nx, ny)] = (cx, cy)
                heapq.heappush(heap, (new_cost, nx, ny))
    return []


def _meander(
    rng: random.Random,
    path: List[Tuple[int, int]],
    game_map: GameMap,
    ground_tid: int,
    freq: int = 6,
) -> List[Tuple[int, int]]:
    """Add gentle lateral wobble to a path for organic feel.

    Every *freq* tiles, attempt a 1-tile lateral jog: step sideways from
    the previous tile, then forward to the current tile.  Both inserted tiles
    must be ground, in bounds, and not adjacent to any wall.  In tight spaces
    (corridors, wall-adjacent areas) the offset is simply skipped.
    """
    if len(path) < 3:
        return list(path)
    w, h = game_map.width, game_map.height
    wall_tid = int(tile_types.structure_wall["tile_id"])

    def _is_wall_adjacent(x: int, y: int) -> bool:
        for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + ddx, y + ddy
            if 0 <= nx < w and 0 <= ny < h:
                if int(game_map.tiles["tile_id"][nx, ny]) == wall_tid:
                    return True
        return False

    def _is_valid_offset(x: int, y: int) -> bool:
        if not (0 < x < w - 1 and 0 < y < h - 1):
            return False
        if int(game_map.tiles["tile_id"][x, y]) != ground_tid:
            return False
        if _is_wall_adjacent(x, y):
            return False
        return True

    result: List[Tuple[int, int]] = [path[0]]
    for i in range(1, len(path)):
        if i % freq == 0 and i < len(path) - 1:
            px, py = path[i - 1]
            cx, cy = path[i]
            dx, dy = cx - px, cy - py
            # Lateral direction (perpendicular to travel)
            if dx != 0:
                offsets = [(0, -1), (0, 1)]
            elif dy != 0:
                offsets = [(-1, 0), (1, 0)]
            else:
                offsets = []
            rng.shuffle(offsets)
            for ox, oy in offsets:
                # Two-tile jog: prev+lateral, then current+lateral (=prev+lateral+forward)
                # Step 1: from prev, go lateral
                s1x, s1y = px + ox, py + oy
                # Step 2: from step1, go forward (same direction as travel)
                s2x, s2y = s1x + dx, s1y + dy
                # s2 must be adjacent to current tile
                if abs(s2x - cx) + abs(s2y - cy) != 1:
                    continue
                if _is_valid_offset(s1x, s1y) and _is_valid_offset(s2x, s2y):
                    result.append((s1x, s1y))
                    result.append((s2x, s2y))
                    break
        result.append(path[i])
    return result


def _place_building_lights(
    game_map: GameMap,
    rng: random.Random,
    sub_rooms: List[RectRoom],
) -> None:
    """Place warm indoor lights in some rooms of a colony building.

    Per-building: roll whether this building is lit at all (~60% chance).
    Then per-room: ~50% chance each room has a light.
    Light is either overhead (center) or a wall sconce.
    """
    if rng.random() > 0.60:
        return  # building is dark

    color = (200, 180, 130)  # warm indoor light
    radius = 4
    intensity = 0.45

    door_tids = {
        int(tile_types.door_closed["tile_id"]),
        int(tile_types.door_open["tile_id"]),
    }
    window_tid = int(tile_types.structure_window["tile_id"])
    wall_tid_set: set[int] = set()
    # structure_wall is the main colony wall type
    wall_tid_set.add(int(tile_types.structure_wall["tile_id"]))

    for room in sub_rooms:
        if rng.random() > 0.50:
            continue  # this room stays dark

        cx, cy = room.center
        # Decide: overhead (center) or wall sconce
        if rng.random() < 0.5:
            # Overhead — place at center if walkable
            if (game_map.in_bounds(cx, cy)
                    and game_map.tiles["walkable"][cx, cy]):
                game_map.add_light_source(cx, cy, radius=radius, color=color, intensity=intensity)
                continue

        # Wall sconce — find a wall tile inside the room that isn't a door/window
        # and has an adjacent floor tile inside the room
        xs, ys = room.inner
        sconce_candidates: List[Tuple[int, int]] = []
        for x in range(room.x1, room.x2 + 1):
            for y in range(room.y1, room.y2 + 1):
                if not game_map.in_bounds(x, y):
                    continue
                tid = int(game_map.tiles["tile_id"][x, y])
                if tid in door_tids or tid == window_tid:
                    continue
                if game_map.tiles["walkable"][x, y]:
                    continue  # not a wall
                if not game_map.tiles["transparent"][x, y]:
                    # Opaque wall — check it has an adjacent floor inside room
                    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                        nx, ny = x + dx, y + dy
                        if (game_map.in_bounds(nx, ny)
                                and xs.start <= nx < xs.stop
                                and ys.start <= ny < ys.stop
                                and game_map.tiles["walkable"][nx, ny]):
                            sconce_candidates.append((x, y))
                            break

        if sconce_candidates:
            sx, sy = rng.choice(sconce_candidates)
            game_map.add_light_source(sx, sy, radius=radius, color=color, intensity=intensity)
        else:
            # Fallback to overhead
            if (game_map.in_bounds(cx, cy)
                    and game_map.tiles["walkable"][cx, cy]):
                game_map.add_light_source(cx, cy, radius=radius, color=color, intensity=intensity)


def _place_street_lights(
    game_map: GameMap,
    spine_tiles: List[Tuple[int, int]],
    rng: random.Random,
) -> None:
    """Place street lamp tiles and light sources along the village spine road."""
    spacing = rng.randint(12, 15)
    color = (180, 160, 110)
    radius = 5
    intensity = 0.5
    ground_tid = int(tile_types.ground["tile_id"])

    for i in range(0, len(spine_tiles), spacing):
        sx, sy = spine_tiles[i]
        # Try to place lamp on an adjacent non-walkable ground tile
        placed = False
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            lx, ly = sx + dx, sy + dy
            if not game_map.in_bounds(lx, ly):
                continue
            tid = int(game_map.tiles["tile_id"][lx, ly])
            if tid == ground_tid and not game_map.tiles["walkable"][lx, ly]:
                # Non-walkable ground — skip, ground is walkable
                continue
            if tid == ground_tid:
                game_map.tiles[lx, ly] = tile_types.street_lamp
                game_map.add_light_source(lx, ly, radius=radius, color=color, intensity=intensity)
                placed = True
                break
        if not placed:
            # Fall back: place light at the spine tile itself
            game_map.add_light_source(sx, sy, radius=radius, color=color, intensity=intensity)


_DOCK_SIZE = 8   # bounding box side (tiles span 0..SIZE → SIZE+1 tiles per axis)
_DOCK_CUT = 2    # corner cut depth for the octagon


def _in_dock_octagon(dx: int, dy: int, size: int = _DOCK_SIZE, cut: int = _DOCK_CUT) -> bool:
    """Return True if offset (dx, dy) within a *size*×*size* rect is inside the octagon."""
    return (dx + dy >= cut
            and dx + dy <= 2 * size - cut
            and size - dx + dy >= cut
            and dx + size - dy >= cut)


def _on_dock_perimeter(dx: int, dy: int, size: int = _DOCK_SIZE, cut: int = _DOCK_CUT) -> bool:
    """Return True if (dx, dy) is on the octagon edge.

    Uses 8-directional neighbour check so diagonal corner transitions are
    filled in, producing a visually unbroken outline.
    """
    if not _in_dock_octagon(dx, dy, size, cut):
        return False
    for ndx, ndy in ((dx - 1, dy), (dx + 1, dy), (dx, dy - 1), (dx, dy + 1),
                      (dx - 1, dy - 1), (dx + 1, dy - 1), (dx - 1, dy + 1), (dx + 1, dy + 1)):
        if not _in_dock_octagon(ndx, ndy, size, cut):
            return True
    return False


def _place_ship_dock(
    game_map: GameMap,
    rng: random.Random,
    placed_wings: List[RectRoom],
    path_tile: np.ndarray,
    ground_tile: np.ndarray,
) -> Optional[RectRoom]:
    """Place an octagonal ship dock landing pad with path-tile outline.

    Returns a RectRoom bounding box labelled 'ship_dock', or None on failure.
    The dock is added to *placed_wings* for building collision avoidance.
    """
    w, h = game_map.width, game_map.height
    gap = 2  # buffer from buildings and border
    # RectRoom(x, y, size, size) → x2 = x+size, tiles x..x+size = size+1 tiles.
    # _DOCK_SIZE must be even so tile count (size+1) is odd → true center.
    dock_side = _DOCK_SIZE  # RectRoom width/height parameter

    margin = 4  # distance from map border
    max_x = w - margin - dock_side
    max_y = h - margin - dock_side
    if max_x < margin or max_y < margin:
        return None

    # Candidate positions: prefer edges, then random interior
    candidates: List[Tuple[int, int]] = []
    for _ in range(30):
        side = rng.randint(0, 3)
        if side == 0:
            candidates.append((rng.randint(margin, max_x), margin))
        elif side == 1:
            candidates.append((rng.randint(margin, max_x), max_y))
        elif side == 2:
            candidates.append((margin, rng.randint(margin, max_y)))
        else:
            candidates.append((max_x, rng.randint(margin, max_y)))
    for _ in range(20):
        candidates.append((rng.randint(margin, max_x), rng.randint(margin, max_y)))

    for rx, ry in candidates:
        if rx < 2 or ry < 2 or rx + dock_side >= w - 2 or ry + dock_side >= h - 2:
            continue
        dock_rect = RectRoom(rx, ry, dock_side, dock_side, label="ship_dock")
        expanded = RectRoom(rx - gap, ry - gap, dock_side + gap * 2, dock_side + gap * 2)
        if any(expanded.intersects(o) for o in placed_wings):
            continue

        # Paint octagonal dock
        for x in range(dock_rect.x1, dock_rect.x2 + 1):
            for y in range(dock_rect.y1, dock_rect.y2 + 1):
                dx, dy = x - dock_rect.x1, y - dock_rect.y1
                if not _in_dock_octagon(dx, dy):
                    continue
                if _on_dock_perimeter(dx, dy):
                    game_map.tiles[x, y] = path_tile
                else:
                    game_map.tiles[x, y] = ground_tile

        placed_wings.append(dock_rect)
        return dock_rect

    return None


def _generate_village_paths(
    game_map: GameMap,
    rng: random.Random,
    door_positions: List[Tuple[int, int]],
    path_tile: np.ndarray,
    ground_tid: int,
) -> None:
    """Paint paths: a main spine road + branches from each door to the spine.

    Uses BFS pathfinding so paths route around buildings rather than through them.
    """
    w, h = game_map.width, game_map.height
    if door_positions:
        cx = sum(p[0] for p in door_positions) // len(door_positions)
        cy = sum(p[1] for p in door_positions) // len(door_positions)
    else:
        cx, cy = w // 2, h // 2

    # Pick spine orientation and randomized endpoints
    if rng.random() < 0.5:
        # Horizontal: left edge -> right edge with random y
        sy_start = rng.randint(3, h - 4)
        sy_end = rng.randint(3, h - 4)
        start = (1, sy_start)
        end = (w - 2, sy_end)
        horizontal = True
    else:
        # Vertical: top edge -> bottom edge with random x
        sx_start = rng.randint(3, w - 4)
        sx_end = rng.randint(3, w - 4)
        start = (sx_start, 1)
        end = (sx_end, h - 2)
        horizontal = False

    # Dijkstra spine through ground tiles
    spine_path = _bfs_path(game_map, start, end, ground_tid)
    if not spine_path:
        # Fallback: try the other orientation with centroid
        if horizontal:
            start = (cx, 1)
            end = (cx, h - 2)
            horizontal = False
        else:
            start = (1, cy)
            end = (w - 2, cy)
            horizontal = True
        spine_path = _bfs_path(game_map, start, end, ground_tid)

    # Apply meander to spine for organic feel
    if spine_path:
        spine_path = _meander(rng, spine_path, game_map, ground_tid)

    # Widen spine to 2 tiles
    spine_tiles: List[Tuple[int, int]] = []
    for x, y in spine_path:
        spine_tiles.append((x, y))
        if horizontal:
            if 0 < y + 1 < h - 1:
                spine_tiles.append((x, y + 1))
        else:
            if 0 < x + 1 < w - 1:
                spine_tiles.append((x + 1, y))

    # Paint spine — only overwrite ground tiles
    for x, y in spine_tiles:
        if game_map.in_bounds(x, y) and int(game_map.tiles["tile_id"][x, y]) == ground_tid:
            game_map.tiles[x, y] = path_tile

    # Branch paths from each door to nearest spine tile via BFS
    spine_set = {(x, y) for x, y in spine_tiles
                 if game_map.in_bounds(x, y) and int(game_map.tiles["tile_id"][x, y]) == int(path_tile["tile_id"])}
    path_tid = int(path_tile["tile_id"])
    for door_x, door_y in door_positions:
        if not spine_set:
            break
        # Multi-target BFS: find shortest path from door to any spine tile
        branch = _bfs_to_set(game_map, (door_x, door_y), spine_set, ground_tid)
        for x, y in branch:
            if game_map.in_bounds(x, y) and int(game_map.tiles["tile_id"][x, y]) == ground_tid:
                game_map.tiles[x, y] = path_tile

    # Place street lights along the spine (use single-lane path, not widened tiles)
    _place_street_lights(game_map, list(spine_path), rng)


def _generate_village(
    game_map: GameMap,
    rng: random.Random,
    profile: LocationProfile,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> List[RectRoom]:
    """Colony village: open ground with irregular multi-wing buildings."""
    w, h = game_map.width, game_map.height
    rooms: List[RectRoom] = []
    label_counts: dict[str, int] = {}
    # Track all placed wing rectangles for collision checks
    placed_wings: List[RectRoom] = []

    # Pick a biome palette for this colony
    palette = pick_biome(rng)
    biome_ground = make_ground_tile(palette)
    path_tile = make_path_tile(palette, rng)

    game_map.biome = palette.name

    # Fill entire map with biome ground (shares ground tile_id)
    game_map.tiles[:] = biome_ground

    # Track door approach positions for path generation
    door_positions: List[Tuple[int, int]] = []

    # Border wall around map edges
    game_map.tiles[0, :] = wall_tile
    game_map.tiles[w - 1, :] = wall_tile
    game_map.tiles[:, 0] = wall_tile
    game_map.tiles[:, h - 1] = wall_tile

    # Place ship dock landing pad before buildings so it gets a clear spot
    dock_room = _place_ship_dock(
        game_map, rng, placed_wings, path_tile, biome_ground,
    )

    # Square-footage budget: buildings may cover 50-60% of usable area
    usable_area = (w - 2) * (h - 2)
    target_coverage = rng.uniform(0.15, 0.30)
    max_sq_ft = int(usable_area * target_coverage)
    used_sq_ft = 0
    gap = 1  # minimum tiles between buildings

    # Place required rooms first, then fill
    all_specs: List[RoomSpec] = list(_required_specs(profile))

    def _try_place_building(
        rx: int, ry: int, spec: RoomSpec,
    ) -> Optional[List[RectRoom]]:
        """Attempt to place a building at (rx, ry). Return wing rects or None."""
        rw = rng.randint(spec.min_w, spec.max_w)
        rh = rng.randint(spec.min_h, spec.max_h)
        num_wings = _pick_building_room_count(rng)
        wing_tuples = _compose_building_wings(
            rng, rx, ry, rw, rh, num_wings, min_w=5, min_h=5,
        )
        result: List[RectRoom] = []
        for wx, wy, ww, wh in wing_tuples:
            if wx < 2 or wy < 2 or wx + ww >= w - 2 or wy + wh >= h - 2:
                return None
            wing_rect = RectRoom(wx, wy, ww, wh, label=spec.label)
            expanded = RectRoom(wx - gap, wy - gap, ww + gap * 2, wh + gap * 2)
            for other in placed_wings:
                if expanded.intersects(other):
                    return None
            result.append(wing_rect)
        return result

    # Build a shuffled grid of candidate positions covering the map
    # Buildings must start at x/y >= 2 to keep 1-tile ground gap from border
    step_x, step_y = 7, 6  # dense grid for good coverage
    grid_positions = [
        (gx, gy)
        for gx in range(2, w - 6, step_x)
        for gy in range(2, h - 6, step_y)
    ]
    rng.shuffle(grid_positions)
    # Also add random jittered positions for gap-filling
    random_positions = [
        (rng.randint(2, max(2, w - 9)), rng.randint(2, max(2, h - 9)))
        for _ in range(150)
    ]
    candidate_positions = grid_positions + random_positions
    retries_per_pos = 3  # retry with different wing configs

    for rx, ry in candidate_positions:
        if used_sq_ft >= max_sq_ft:
            break

        if all_specs:
            spec = all_specs.pop(0)
        else:
            spec = _pick_room_spec(rng, profile, label_counts)

        wing_rects: Optional[List[RectRoom]] = None
        for _ in range(retries_per_pos):
            wing_rects = _try_place_building(rx, ry, spec)
            if wing_rects is not None:
                break
        if wing_rects is None:
            continue

        # Pick a per-building wall color from the biome palette
        bldg_wall_tile = make_wall_tile(rng.choice(palette.wall_colors))

        # Place all wings: fill with wall
        for wing in wing_rects:
            for bx in range(wing.x1, wing.x2 + 1):
                for by in range(wing.y1, wing.y2 + 1):
                    if game_map.in_bounds(bx, by):
                        game_map.tiles[bx, by] = bldg_wall_tile

        # Subdivide each wing into sub-rooms or carve as single room.
        # Larger wings (inner ≥ 7 in both dims) get 2-3 sub-rooms.
        all_sub_rooms: List[RectRoom] = []
        for wing in wing_rects:
            inner_w = wing.x2 - wing.x1 - 1
            inner_h = wing.y2 - wing.y1 - 1
            # Min offset for subdivision is 4, so need inner ≥ 7 on both axes
            if inner_w >= 7 and inner_h >= 7:
                num_sub = rng.randint(2, 3)
            elif inner_w >= 7 or inner_h >= 7:
                num_sub = 2
            else:
                num_sub = 1
            sub_rooms = _subdivide_building(
                game_map, rng,
                wing.x1, wing.y1, wing.x2, wing.y2,
                num_sub, floor_tile, bldg_wall_tile, label=spec.label,
            )
            all_sub_rooms.extend(sub_rooms)

        # Carve doorways between adjacent wing pairs
        for i in range(len(wing_rects)):
            for j in range(i + 1, len(wing_rects)):
                _carve_wing_doorway(game_map, wing_rects[i], wing_rects[j], floor_tile)

        # Carve external door on the building's outer perimeter
        door_pos = _carve_external_door(game_map, rng, wing_rects, floor_tile)
        if door_pos is not None:
            door_positions.append(door_pos)

        # Place windows on exterior walls
        _place_building_windows(game_map, rng, wing_rects, bldg_wall_tile, floor_tile)

        # Interior lights (after walls/doors/windows are finalized)
        _place_building_lights(game_map, rng, all_sub_rooms)

        building_sq_ft = sum(
            (wr.x2 - wr.x1) * (wr.y2 - wr.y1) for wr in wing_rects
        )
        used_sq_ft += building_sq_ft
        placed_wings.extend(wing_rects)
        rooms.extend(all_sub_rooms)
        label_counts[spec.label] = label_counts.get(spec.label, 0) + 1

    # Generate paths connecting building doors to a main road
    ground_tid = int(tile_types.ground["tile_id"])
    # Include dock center as a door position so it gets a branch path to the road
    if dock_room is not None:
        door_positions.append(dock_room.center)
    _generate_village_paths(game_map, rng, door_positions, path_tile, ground_tid)

    # Scatter flora on ground tiles (before noise so flora gets the same bg noise)
    scatter_flora(game_map, rng, palette, ground_tid)

    # Apply per-tile ground noise for visual variety (ground + flora share bg)
    flora_tids = [
        int(tile_types.flora_low["tile_id"]),
        int(tile_types.flora_tall["tile_id"]),
        int(tile_types.flora_scrub["tile_id"]),
        int(tile_types.flora_sprout["tile_id"]),
    ]
    apply_ground_noise(game_map, rng, ground_tid, palette.noise_range, extra_tids=flora_tids)

    # Hard repaint the entire dock: perimeter = path, interior = ground, no exceptions.
    if dock_room is not None:
        for x in range(dock_room.x1, dock_room.x2 + 1):
            for y in range(dock_room.y1, dock_room.y2 + 1):
                dx, dy = x - dock_room.x1, y - dock_room.y1
                if not _in_dock_octagon(dx, dy):
                    continue
                if _on_dock_perimeter(dx, dy):
                    game_map.tiles[x, y] = path_tile
                else:
                    game_map.tiles[x, y] = biome_ground
        # Insert dock as rooms[0] so exit/spawn uses it
        rooms.insert(0, dock_room)

    return rooms


# -------------------------------------------------------------------
# -------------------------------------------------------------------
# Door placement
# -------------------------------------------------------------------

def _is_room_adjacent(x: int, y: int, rooms: List[RectRoom]) -> bool:
    """Return True if (x, y) is cardinally adjacent to any room's inner area."""
    for room in rooms:
        ix, iy = room.inner
        # Check if any cardinal neighbor falls inside the room interior
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            if ix.start <= nx < ix.stop and iy.start <= ny < iy.stop:
                return True
    return False


def _place_doors(
    game_map: GameMap,
    rng: random.Random,
    floor_tile: np.ndarray,
    rooms: List[RectRoom],
    door_chance: float = 0.65,
    min_spacing: int = 3,
) -> None:
    """Place closed doors at room entrances — chokepoints adjacent to a room's
    inner area, with minimum spacing to avoid door clusters."""
    floor_tid = int(floor_tile["tile_id"])
    w, h = game_map.width, game_map.height

    candidates: List[Tuple[int, int]] = []
    for x in range(1, w - 1):
        for y in range(1, h - 1):
            if int(game_map.tiles["tile_id"][x, y]) != floor_tid:
                continue
            n = bool(game_map.tiles["walkable"][x, y - 1])
            s = bool(game_map.tiles["walkable"][x, y + 1])
            e = bool(game_map.tiles["walkable"][x + 1, y])
            w_ = bool(game_map.tiles["walkable"][x - 1, y])

            is_chokepoint = False
            # Vertical chokepoint: walls E+W, floor N+S
            if not e and not w_ and n and s:
                is_chokepoint = True
            # Horizontal chokepoint: walls N+S, floor E+W
            elif not n and not s and e and w_:
                is_chokepoint = True

            if is_chokepoint and _is_room_adjacent(x, y, rooms):
                candidates.append((x, y))

    # Place doors with minimum spacing
    placed: List[Tuple[int, int]] = []
    entity_positions = {(e.x, e.y) for e in game_map.entities}
    rng.shuffle(candidates)
    for x, y in candidates:
        if rng.random() >= door_chance:
            continue
        if (x, y) in entity_positions:
            continue
        # Enforce minimum spacing from already-placed doors
        too_close = False
        for px, py in placed:
            if abs(x - px) + abs(y - py) < min_spacing:
                too_close = True
                break
        if not too_close:
            game_map.tiles[x, y] = tile_types.door_closed
            placed.append((x, y))


# Generator dispatch
# -------------------------------------------------------------------

_GENERATORS = {
    "ship": _generate_ship,
    "organic": _generate_organic,
    "standard": _generate_standard,
    "village": _generate_village,
}


# -------------------------------------------------------------------
# Space conversion — replace outer hull walls with space tiles
# -------------------------------------------------------------------


def _place_airlocks(
    game_map: GameMap,
    rng: random.Random,
    rooms: List[RectRoom],
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
) -> None:
    """Place 1-2 airlocks on the hull exterior.

    Each airlock is a 3-tile extension outward from a hull wall:
    [interior_door] [airlock_floor] [exterior_door]
    surrounded by wall tiles to preserve structure during hull conversion.
    Must be called before _convert_hull_to_space().
    """
    wall_tid = int(wall_tile["tile_id"])
    num_airlocks = rng.randint(1, 2)
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]  # N, S, W, E

    # Collect all walkable positions (room interiors + corridors)
    walkable_mask = game_map.tiles["walkable"]

    candidates: List[tuple] = []  # (wall_x, wall_y, dx, dy)

    for room in rooms:
        for wx, wy in _room_wall_positions(room):
            if not game_map.in_bounds(wx, wy):
                continue
            if int(game_map.tiles["tile_id"][wx, wy]) != wall_tid:
                continue
            for dx, dy in directions:
                # Interior side: tile inside the room (opposite of outward direction)
                ix, iy = wx - dx, wy - dy
                if not game_map.in_bounds(ix, iy):
                    continue
                if not walkable_mask[ix, iy]:
                    continue

                # The 3 outward tiles: wall pos (becomes interior door),
                # wall+1*dir (airlock floor), wall+2*dir (exterior door)
                positions = [
                    (wx + i * dx, wy + i * dy) for i in range(3)
                ]
                # All 3 must be in bounds and currently wall tiles
                valid = True
                for px, py in positions:
                    if not game_map.in_bounds(px, py):
                        valid = False
                        break
                    if int(game_map.tiles["tile_id"][px, py]) != wall_tid:
                        valid = False
                        break
                if not valid:
                    continue

                # Perpendicular directions for wall checks
                if dx == 0:
                    perp = [(1, 0), (-1, 0)]
                else:
                    perp = [(0, 1), (0, -1)]

                # The tile beyond the exterior door must be wall (will become space),
                # and its perpendicular neighbors must also be wall to avoid
                # creating space tiles adjacent to walkable corridors/rooms.
                bx, by = wx + 3 * dx, wy + 3 * dy
                if not game_map.in_bounds(bx, by):
                    continue
                if int(game_map.tiles["tile_id"][bx, by]) != wall_tid:
                    continue
                # Check all cardinal neighbors of beyond-tile are wall
                beyond_ok = True
                for cdx, cdy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                    bnx, bny = bx + cdx, by + cdy
                    # Skip the exterior door direction (back toward airlock)
                    if (cdx, cdy) == (-dx, -dy):
                        continue
                    if not game_map.in_bounds(bnx, bny):
                        beyond_ok = False
                        break
                    if int(game_map.tiles["tile_id"][bnx, bny]) != wall_tid:
                        beyond_ok = False
                        break
                if not beyond_ok:
                    continue

                # Check that surrounding wall tiles exist for chamber walls
                # (perpendicular neighbors of the airlock tiles must be wall)
                walls_ok = True
                for px, py in positions:
                    for pdx, pdy in perp:
                        nx, ny = px + pdx, py + pdy
                        if not game_map.in_bounds(nx, ny):
                            walls_ok = False
                            break
                        if int(game_map.tiles["tile_id"][nx, ny]) != wall_tid:
                            walls_ok = False
                            break
                    if not walls_ok:
                        break
                if not walls_ok:
                    continue

                candidates.append((wx, wy, dx, dy))

    rng.shuffle(candidates)
    placed = 0
    used_positions: set = set()

    for wx, wy, dx, dy in candidates:
        if placed >= num_airlocks:
            break

        # Ensure no overlap with already-placed airlocks
        positions = [(wx + i * dx, wy + i * dy) for i in range(3)]
        if any((px, py) in used_positions for px, py in positions):
            continue

        # Carve the airlock
        # Position 0: interior door (at hull wall)
        game_map.tiles[positions[0][0], positions[0][1]] = tile_types.door_closed
        # Position 1: airlock floor
        game_map.tiles[positions[1][0], positions[1][1]] = tile_types.airlock_floor
        # Position 2: exterior door (hull-colored)
        game_map.tiles[positions[2][0], positions[2][1]] = tile_types.airlock_ext_closed

        for px, py in positions:
            used_positions.add((px, py))

        # Place switch on a wall tile cardinally adjacent to the interior door
        door_x, door_y = positions[0]
        switch_pos = None
        for sdx, sdy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            sx, sy = door_x + sdx, door_y + sdy
            if not game_map.in_bounds(sx, sy):
                continue
            if (sx, sy) in used_positions:
                continue
            stid = int(game_map.tiles["tile_id"][sx, sy])
            if stid != wall_tid:
                continue
            switch_pos = (sx, sy)
            break

        if switch_pos:
            game_map.tiles[switch_pos[0], switch_pos[1]] = tile_types.airlock_switch_off
            used_positions.add(switch_pos)

        game_map.airlocks.append({
            "interior_door": positions[0],
            "exterior_door": positions[2],
            "direction": (dx, dy),
            "switch": switch_pos,
        })
        placed += 1


def _place_hull_breaches(
    game_map: GameMap, rng: random.Random, wall_tile: np.ndarray,
) -> None:
    """Place 1-3 hull breaches on a derelict/ship map.

    Finds wall tiles adjacent to both a space tile and a walkable tile
    (hull boundary) and replaces them with hull_breach.
    """
    space_tid = int(tile_types.space["tile_id"])
    wall_tid = int(wall_tile["tile_id"])
    candidates: list[tuple[int, int]] = []

    for x in range(1, game_map.width - 1):
        for y in range(1, game_map.height - 1):
            if int(game_map.tiles["tile_id"][x, y]) != wall_tid:
                continue
            has_space = False
            has_walkable = False
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not game_map.in_bounds(nx, ny):
                    continue
                tid = int(game_map.tiles["tile_id"][nx, ny])
                if tid == space_tid:
                    has_space = True
                if bool(game_map.tiles["walkable"][nx, ny]):
                    has_walkable = True
            if has_space and has_walkable:
                candidates.append((x, y))

    if not candidates:
        return

    entity_positions = {(e.x, e.y) for e in game_map.entities}
    candidates = [(x, y) for x, y in candidates if (x, y) not in entity_positions]
    if not candidates:
        return
    count = min(rng.randint(1, 3), len(candidates))
    chosen = rng.sample(candidates, count)
    for bx, by in chosen:
        game_map.tiles[bx, by] = tile_types.hull_breach
        game_map.hull_breaches.append((bx, by))


def _place_asteroid_breaches(
    game_map: GameMap, rng: random.Random,
) -> None:
    """Place 1-2 hull breaches on an asteroid/cave map.

    Finds rock_wall tiles at the map perimeter adjacent to interior walkable
    tiles, replaces them with hull_breach, and converts the tile beyond the
    breach to space.
    """
    rock_wall_tid = int(tile_types.rock_wall["tile_id"])
    candidates: list[tuple[int, int, int, int]] = []  # (x, y, beyond_x, beyond_y)

    for x in range(game_map.width):
        for y in range(game_map.height):
            if int(game_map.tiles["tile_id"][x, y]) != rock_wall_tid:
                continue
            # Must be at map perimeter or adjacent to map edge
            at_edge = (x <= 1 or x >= game_map.width - 2
                       or y <= 1 or y >= game_map.height - 2)
            if not at_edge:
                continue
            # Check for adjacent interior walkable tile and a direction for space
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                bx, by = x - dx, y - dy  # beyond = opposite direction
                if not game_map.in_bounds(nx, ny):
                    continue
                if not game_map.in_bounds(bx, by):
                    continue
                if bool(game_map.tiles["walkable"][nx, ny]):
                    candidates.append((x, y, bx, by))
                    break

    if not candidates:
        return

    count = min(rng.randint(1, 2), len(candidates))
    chosen = rng.sample(candidates, count)
    for bx, by, sx, sy in chosen:
        game_map.tiles[bx, by] = tile_types.hull_breach
        game_map.hull_breaches.append((bx, by))
        game_map.tiles[sx, sy] = tile_types.space
    game_map.has_space = True


def _convert_hull_to_space(game_map: GameMap, wall_tile: np.ndarray) -> None:
    """Replace wall tiles not adjacent to any walkable or window tile with space.

    Uses numpy array shifts for vectorized adjacency checking (no Python loops).
    Walls adjacent (8-directional) to walkable or window tiles are structural
    hull and kept.  Then a cleanup pass converts hull filler behind exterior
    windows (adjacent to a window but not to any walkable tile) to space so
    that windows actually provide a view into space.
    """
    wall_tid = int(wall_tile["tile_id"])
    window_tid = int(tile_types.structure_window["tile_id"])

    is_wall = game_map.tiles["tile_id"] == wall_tid
    is_walkable = game_map.tiles["walkable"].copy()
    is_window = game_map.tiles["tile_id"] == window_tid

    # A tile is "interesting" if walkable or a window
    interesting = is_walkable | is_window

    # Check adjacency to interesting tiles in all 8 directions
    # (diagonal checks prevent corner gaps that allow FOV peek-through)
    adj = np.zeros_like(interesting)
    # Cardinal
    adj[1:, :] |= interesting[:-1, :]   # neighbor to the left
    adj[:-1, :] |= interesting[1:, :]   # neighbor to the right
    adj[:, 1:] |= interesting[:, :-1]   # neighbor above
    adj[:, :-1] |= interesting[:, 1:]   # neighbor below
    # Diagonal
    adj[1:, 1:] |= interesting[:-1, :-1]
    adj[1:, :-1] |= interesting[:-1, 1:]
    adj[:-1, 1:] |= interesting[1:, :-1]
    adj[:-1, :-1] |= interesting[1:, 1:]

    # Wall tiles NOT adjacent to anything interesting become space
    to_space = is_wall & ~adj
    game_map.tiles[to_space] = tile_types.space

    # Cleanup: walls adjacent to windows but not to any walkable tile are
    # hull filler behind exterior windows — convert to space so windows
    # actually look out into space.
    is_wall_now = game_map.tiles["tile_id"] == wall_tid
    is_window_now = game_map.tiles["tile_id"] == window_tid

    adj_walkable = np.zeros_like(is_walkable)
    adj_walkable[1:, :] |= is_walkable[:-1, :]
    adj_walkable[:-1, :] |= is_walkable[1:, :]
    adj_walkable[:, 1:] |= is_walkable[:, :-1]
    adj_walkable[:, :-1] |= is_walkable[:, 1:]

    adj_window = np.zeros_like(is_window_now)
    adj_window[1:, :] |= is_window_now[:-1, :]
    adj_window[:-1, :] |= is_window_now[1:, :]
    adj_window[:, 1:] |= is_window_now[:, :-1]
    adj_window[:, :-1] |= is_window_now[:, 1:]

    hull_filler = is_wall_now & adj_window & ~adj_walkable
    game_map.tiles[hull_filler] = tile_types.space

    # Second cleanup: walls only diagonally adjacent to a window (corner "ears")
    # that are not cardinally adjacent to any walkable or window tile.
    is_wall_now2 = game_map.tiles["tile_id"] == wall_tid
    is_window_now2 = game_map.tiles["tile_id"] == window_tid
    is_walkable2 = game_map.tiles["walkable"].copy()
    cardinal_interesting = np.zeros_like(is_wall_now2)
    cardinal_interesting[1:, :] |= (is_walkable2 | is_window_now2)[:-1, :]
    cardinal_interesting[:-1, :] |= (is_walkable2 | is_window_now2)[1:, :]
    cardinal_interesting[:, 1:] |= (is_walkable2 | is_window_now2)[:, :-1]
    cardinal_interesting[:, :-1] |= (is_walkable2 | is_window_now2)[:, 1:]
    diag_window = np.zeros_like(is_wall_now2)
    diag_window[1:, 1:] |= is_window_now2[:-1, :-1]
    diag_window[1:, :-1] |= is_window_now2[:-1, 1:]
    diag_window[:-1, 1:] |= is_window_now2[1:, :-1]
    diag_window[:-1, :-1] |= is_window_now2[1:, 1:]
    corner_ears = is_wall_now2 & diag_window & ~cardinal_interesting
    game_map.tiles[corner_ears] = tile_types.space

    # Third cleanup: iteratively remove wall stubs (wall tiles with 3+ space
    # cardinal neighbors) until none remain.
    space_tid = int(tile_types.space["tile_id"])
    for _ in range(5):
        is_wall_pass = game_map.tiles["tile_id"] == wall_tid
        is_space = game_map.tiles["tile_id"] == space_tid
        space_neighbors = np.zeros(game_map.tiles.shape, dtype=int)
        space_neighbors[1:, :] += is_space[:-1, :]
        space_neighbors[:-1, :] += is_space[1:, :]
        space_neighbors[:, 1:] += is_space[:, :-1]
        space_neighbors[:, :-1] += is_space[:, 1:]
        stubs = is_wall_pass & (space_neighbors >= 3)
        if not np.any(stubs):
            break
        game_map.tiles[stubs] = tile_types.space


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
    max_total_enemies: int = MAX_ENEMIES_PER_LEVEL,
) -> Tuple[GameMap, List[RectRoom], Optional[Tuple[int, int]]]:
    """Returns (game_map, rooms, exit_pos)."""
    rng = random.Random(seed)
    profile = get_profile(loc_type)
    wall_tile = _resolve_tile(profile.wall_tile)
    floor_tile = _resolve_tile(profile.floor_tile)

    game_map = GameMap(width, height, fill_tile=wall_tile)
    game_map.fully_lit = profile.fully_lit
    game_map.fov_radius = profile.fov_radius
    from debug import VISIBLE_ALL
    game_map.debug_visible_all = VISIBLE_ALL
    gen_fn = _GENERATORS.get(profile.generator)
    if gen_fn:
        rooms = gen_fn(game_map, rng, profile, wall_tile, floor_tile)
    else:
        rooms = _generate_fallback(
            game_map, rng, max_rooms, room_min, room_max, floor_tile,
        )

    # Place doors at room entrances (skip organic/cave layouts)
    if rooms and profile.generator != "organic":
        _place_doors(game_map, rng, floor_tile, rooms)

    # Exit hatch at entrance so the player can always leave from where they entered.
    exit_pos: Optional[Tuple[int, int]] = None
    if rooms:
        exit_pos = rooms[0].center
        if game_map.in_bounds(exit_pos[0], exit_pos[1]):
            game_map.tiles[exit_pos[0], exit_pos[1]] = tile_types.exit_tile

    total_spawned = 0
    for room in rooms[1:]:
        remaining = max_total_enemies - total_spawned
        if remaining > 0:
            total_spawned += _spawn_enemies(
                room, game_map, rng, max_enemies,
                exit_pos=exit_pos, remaining=remaining,
            )
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

    # Place airlocks before hull conversion (need wall tiles to identify hull)
    if profile.generator in ("ship", "standard"):
        _place_airlocks(game_map, rng, rooms, wall_tile, floor_tile)

    # Convert outer hull walls to space tiles for ship/starbase maps
    if profile.generator in ("ship", "standard"):
        _convert_hull_to_space(game_map, wall_tile)
        game_map.has_space = True
        # Ensure space beyond airlock exterior doors
        for al in game_map.airlocks:
            ex, ey = al["exterior_door"]
            dx, dy = al["direction"]
            bx, by = ex + dx, ey + dy
            if game_map.in_bounds(bx, by):
                game_map.tiles[bx, by] = tile_types.space
        # Hull breaches — starbases only have a 20% chance
        if profile.loc_type != "starbase" or rng.random() < 0.2:
            _place_hull_breaches(game_map, rng, wall_tile)

    # Hull breaches for asteroid/organic maps
    if profile.generator == "organic":
        _place_asteroid_breaches(game_map, rng)

    game_map._hazards_dirty = True
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
    max_total_enemies: int = MAX_ENEMIES_PER_LEVEL,
) -> None:
    """Remove all entities with AI (creatures) and spawn new ones in rooms[1:].
    Does not touch items or the map. Uses seed for deterministic placement if given.
    """
    game_map.entities[:] = [e for e in game_map.entities if not e.ai]
    rng = random.Random(seed)
    total_spawned = 0
    for room in rooms[1:]:
        remaining = max_total_enemies - total_spawned
        if remaining <= 0:
            break
        total_spawned += _spawn_enemies(room, game_map, rng, max_enemies, remaining=remaining)
