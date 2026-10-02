"""Ship generator: hull profile, spine, rooms placed inside the hull."""

from __future__ import annotations

import random

import numpy as np

from world.dungeon_gen.corridors import _carve_h_tunnel, _carve_v_tunnel
from world.dungeon_gen.rooms import RectRoom, _pick_room_spec, _safe_randint
from world.dungeon_gen.ship_dressing import _dress_ship_room, _place_ship_corridor_lights
from world.dungeon_gen.windows import _place_building_windows, _place_ship_exterior_windows
from world.game_map import GameMap
from world.loc_profiles import LocationProfile


def _load_hull_profile(
    rng: random.Random,
    map_width: int,
) -> tuple[tuple[int, ...], list[tuple[int, int, str | None]], int]:
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
    profile: tuple[int, ...],
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
        game_map.tiles[x, y_top : y_bot + 1] = wall_tile


def _carve_spine(
    game_map: GameMap,
    profile: tuple[int, ...],
    margin_x: int,
    center_y: int,
    floor_tile: np.ndarray,
) -> tuple[int, int, int]:
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
    profile_obj: LocationProfile,
    hull_profile: tuple[int, ...],
    section_bounds: list[tuple[int, int, str | None]],
    margin_x: int,
    center_y: int,
    spine_y: int,
    floor_tile: np.ndarray,
) -> list[RectRoom]:
    """Place rooms inside the hull, respecting hull bounds with margin.

    Bridge/engine rooms are placed inline with the spine at the bow/stern.
    Mid rooms are placed in symmetric pairs above and below the spine.
    Returns list of placed rooms.
    """
    rooms: list[RectRoom] = []
    label_counts: dict[str, int] = {}

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
            ry = _safe_randint(rng, max(1, center_y - half_w + 1), max(1, center_y - 1 - rh))
            if ry is None:
                continue
            room = RectRoom(rx, ry, rw, rh, label=spec.label)
            if any(room.intersects(r) for r in rooms):
                continue
            if not _room_fits_hull(room):
                continue
            return room
        return None

    def _mirror_room(room: RectRoom) -> RectRoom | None:
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
    spine_x1: int,
    spine_x2: int,
    spine_y: int,
    floor_tile: np.ndarray,
) -> tuple[int, int, int] | None:
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
    has_nav_unit: bool = False,
) -> list[RectRoom]:
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
        game_map,
        hull_profile,
        margin_x,
        center_y,
        floor_tile,
    )

    # Store hull info on game_map for airlock placement and lights
    game_map.spine_y = spine_y
    game_map.hull_profile = hull_profile
    game_map.hull_margin_x = margin_x

    # Step 4: Place rooms inside hull bounds
    rooms = _place_rooms_in_hull(
        game_map,
        rng,
        profile,
        hull_profile,
        section_bounds,
        margin_x,
        center_y,
        spine_y,
        floor_tile,
    )

    # Step 5: Connect rooms to spine, collect branch corridors
    branches: list[tuple[int, int, int]] = []
    for room in rooms:
        branch = _connect_room_to_spine(
            game_map,
            room,
            spine_x1,
            spine_x2,
            spine_y,
            floor_tile,
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
            game_map,
            rng,
            [room],
            wall_tile,
            floor_tile,
            outside_tid=corridor_tid,
        )

    # Step 8: Place windows on hull-facing walls (exterior)
    _place_ship_exterior_windows(game_map, rng, rooms, wall_tile, floor_tile)

    # Step 9: Room-specific dressing for all rooms
    exit_pos = rooms[0].center if rooms else None
    for room in rooms:
        _dress_ship_room(room, game_map, rng, exit_pos=exit_pos, has_nav_unit=(has_nav_unit and room.label == "bridge"))

    # Step 10: Corridor lights along spine and branches
    _place_ship_corridor_lights(
        game_map,
        spine_x1,
        spine_x2,
        spine_y,
        spine_y + 2,
        branches,
        rng,
        derelict=True,
        rooms=rooms,
    )

    return rooms
