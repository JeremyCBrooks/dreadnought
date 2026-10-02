"""Organic (asteroid), standard (starbase) and fallback room-and-corridor generators."""

from __future__ import annotations

import random

import numpy as np

from world.dungeon_gen.corridors import _carve_winding_tunnel, _connect_l_corridor
from world.dungeon_gen.rooms import RectRoom, _pick_room_spec, _required_specs, _roll_room
from world.dungeon_gen.windows import _place_building_windows, _place_exterior_windows
from world.game_map import GameMap
from world.loc_profiles import LocationProfile

# Room light per room label: add_light_source keyword arguments.
type RoomLights = dict[str, dict[str, object]]

# Sparse bioluminescent / mineral glow in caverns.
_CAVERN_LIGHTS: RoomLights = {
    "cavern": {"radius": 5, "color": (40, 80, 60), "intensity": 0.4},
    "shaft": {"radius": 3, "color": (60, 50, 30), "intensity": 0.3},
}

_STARBASE_LIGHTS: RoomLights = {
    "control_room": {"radius": 5, "color": (80, 160, 255), "intensity": 0.6},
    "trade_area": {"radius": 6, "color": (200, 190, 150), "intensity": 0.6},
    "dock": {"radius": 5, "color": (160, 140, 100), "intensity": 0.4},
    "cargo": {"radius": 4, "color": (160, 140, 100), "intensity": 0.3},
}


def _place_room_lights(game_map: GameMap, rooms: list[RectRoom], lights: RoomLights) -> None:
    """Light the centre of every room whose label has an entry in *lights*."""
    for room in rooms:
        light = lights.get(room.label)
        if light is not None:
            game_map.add_light_source(*room.center, **light)


def _generate_organic(
    game_map: GameMap,
    rng: random.Random,
    profile: LocationProfile,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
    **kwargs: object,
) -> list[RectRoom]:
    """Organic asteroid layout with irregular rooms and winding corridors."""
    w, h = game_map.width, game_map.height
    rooms: list[RectRoom] = []
    label_counts: dict[str, int] = {}

    for _ in range(profile.max_rooms * 3):
        if len(rooms) >= profile.max_rooms:
            break
        spec = _pick_room_spec(rng, profile, label_counts)
        room = _roll_room(rng, w, h, spec.min_w, spec.max_w, spec.min_h, spec.max_h, label=spec.label)

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

    _place_room_lights(game_map, rooms, _CAVERN_LIGHTS)

    return rooms


def _generate_standard(
    game_map: GameMap,
    rng: random.Random,
    profile: LocationProfile,
    wall_tile: np.ndarray,
    floor_tile: np.ndarray,
    **kwargs: object,
) -> list[RectRoom]:
    """Standard starbase layout — like original but with wider corridors and bigger rooms."""
    w, h = game_map.width, game_map.height
    rooms: list[RectRoom] = []
    label_counts: dict[str, int] = {}

    # Place required rooms first
    for spec in _required_specs(profile):
        for _ in range(profile.max_rooms * 3):
            room = _roll_room(rng, w, h, spec.min_w, spec.max_w, spec.min_h, spec.max_h, label=spec.label)
            if not any(room.intersects(r) for r in rooms):
                game_map.tiles[room.inner] = floor_tile
                if rooms:
                    prev_cx, prev_cy = rooms[-1].center
                    new_cx, new_cy = room.center
                    _connect_l_corridor(game_map, rng, prev_cx, prev_cy, new_cx, new_cy, floor_tile, wide=True)
                rooms.append(room)
                label_counts[spec.label] = label_counts.get(spec.label, 0) + 1
                break

    # Fill remaining rooms
    for _ in range(profile.max_rooms * 3):
        if len(rooms) >= profile.max_rooms:
            break
        spec = _pick_room_spec(rng, profile, label_counts)
        room = _roll_room(rng, w, h, spec.min_w, spec.max_w, spec.min_h, spec.max_h, label=spec.label)

        if any(room.intersects(r) for r in rooms):
            continue

        game_map.tiles[room.inner] = floor_tile

        if rooms:
            prev_cx, prev_cy = rooms[-1].center
            new_cx, new_cy = room.center
            _connect_l_corridor(game_map, rng, prev_cx, prev_cy, new_cx, new_cy, floor_tile, wide=True)

        rooms.append(room)
        label_counts[spec.label] = label_counts.get(spec.label, 0) + 1

    # Place windows on room walls facing corridors
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

    # Place windows on walls facing the hull (uncarved wall fill)
    _place_exterior_windows(game_map, rng, wall_tile, floor_tile)

    _place_room_lights(game_map, rooms, _STARBASE_LIGHTS)

    return rooms


def _generate_fallback(
    game_map: GameMap,
    rng: random.Random,
    max_rooms: int,
    room_min: int,
    room_max: int,
    floor_tile: np.ndarray,
) -> list[RectRoom]:
    """Original room-and-corridor algorithm as fallback."""
    rooms: list[RectRoom] = []
    w, h = game_map.width, game_map.height

    for _ in range(max_rooms * 3):
        if len(rooms) >= max_rooms:
            break
        room = _roll_room(rng, w, h, room_min, room_max, room_min, max(room_min, room_max - 2))

        if any(room.intersects(other) for other in rooms):
            continue

        game_map.tiles[room.inner] = floor_tile

        if rooms:
            prev_cx, prev_cy = rooms[-1].center
            new_cx, new_cy = room.center
            _connect_l_corridor(game_map, rng, prev_cx, prev_cy, new_cx, new_cy, floor_tile)

        rooms.append(room)
    return rooms
