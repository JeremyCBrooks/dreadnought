"""Village (colony) generator: buildings, paths, lights and the ship dock."""

from __future__ import annotations

import random
from collections import deque

import numpy as np

from world import tile_types
from world.dungeon_gen.buildings import (
    _carve_external_door,
    _carve_wing_doorway,
    _compose_building_wings,
    _pick_building_room_count,
    _subdivide_building,
)
from world.dungeon_gen.paths import _bfs_path, _bfs_to_set, _meander
from world.dungeon_gen.rooms import RectRoom, _pick_room_spec, _required_specs
from world.dungeon_gen.windows import _place_building_windows
from world.game_map import GameMap
from world.loc_profiles import LocationProfile, RoomSpec
from world.palettes import (
    apply_ground_noise,
    make_ground_tile,
    make_path_tile,
    make_wall_tile,
    pick_biome,
    scatter_flora,
)


def _place_building_lights(
    game_map: GameMap,
    rng: random.Random,
    sub_rooms: list[RectRoom],
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
            # Overhead - place at center if walkable
            if game_map.in_bounds(cx, cy) and game_map.tiles["walkable"][cx, cy]:
                game_map.add_light_source(cx, cy, radius=radius, color=color, intensity=intensity)
                continue

        # Wall sconce - find a wall tile inside the room that isn't a door/window
        # and has an adjacent floor tile inside the room
        xs, ys = room.inner
        sconce_candidates: list[tuple[int, int]] = []
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
                    # Opaque wall - check it has an adjacent floor inside room
                    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                        nx, ny = x + dx, y + dy
                        if (
                            game_map.in_bounds(nx, ny)
                            and xs.start <= nx < xs.stop
                            and ys.start <= ny < ys.stop
                            and game_map.tiles["walkable"][nx, ny]
                        ):
                            sconce_candidates.append((x, y))
                            break

        if sconce_candidates:
            sx, sy = rng.choice(sconce_candidates)
            game_map.add_light_source(sx, sy, radius=radius, color=color, intensity=intensity)
        else:
            # Fallback to overhead
            if game_map.in_bounds(cx, cy) and game_map.tiles["walkable"][cx, cy]:
                game_map.add_light_source(cx, cy, radius=radius, color=color, intensity=intensity)


def _place_street_lights(
    game_map: GameMap,
    spine_tiles: list[tuple[int, int]],
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
        # Try to place lamp on an adjacent ground tile
        placed = False
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            lx, ly = sx + dx, sy + dy
            if not game_map.in_bounds(lx, ly):
                continue
            tid = int(game_map.tiles["tile_id"][lx, ly])
            if tid == ground_tid:
                game_map.tiles[lx, ly] = tile_types.street_lamp
                game_map.add_light_source(lx, ly, radius=radius, color=color, intensity=intensity)
                placed = True
                break
        if not placed:
            # Fall back: place light at the spine tile itself
            game_map.add_light_source(sx, sy, radius=radius, color=color, intensity=intensity)


_DOCK_SIZE = 8  # bounding box side (tiles span 0..SIZE → SIZE+1 tiles per axis)
_DOCK_CUT = 2  # corner cut depth for the octagon


def _in_dock_octagon(dx: int, dy: int, size: int = _DOCK_SIZE, cut: int = _DOCK_CUT) -> bool:
    """Return True if offset (dx, dy) within a *size*×*size* rect is inside the octagon."""
    return dx + dy >= cut and dx + dy <= 2 * size - cut and size - dx + dy >= cut and dx + size - dy >= cut


def _on_dock_perimeter(dx: int, dy: int, size: int = _DOCK_SIZE, cut: int = _DOCK_CUT) -> bool:
    """Return True if (dx, dy) is on the octagon edge.

    Uses 8-directional neighbour check so diagonal corner transitions are
    filled in, producing a visually unbroken outline.
    """
    if not _in_dock_octagon(dx, dy, size, cut):
        return False
    for ndx, ndy in (
        (dx - 1, dy),
        (dx + 1, dy),
        (dx, dy - 1),
        (dx, dy + 1),
        (dx - 1, dy - 1),
        (dx + 1, dy - 1),
        (dx - 1, dy + 1),
        (dx + 1, dy + 1),
    ):
        if not _in_dock_octagon(ndx, ndy, size, cut):
            return True
    return False


def _place_ship_dock(
    game_map: GameMap,
    rng: random.Random,
    placed_wings: list[RectRoom],
    path_tile: np.ndarray,
    ground_tile: np.ndarray,
) -> RectRoom | None:
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
    candidates: list[tuple[int, int]] = []
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
    door_positions: list[tuple[int, int]],
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
    spine_tiles: list[tuple[int, int]] = []
    for x, y in spine_path:
        spine_tiles.append((x, y))
        if horizontal:
            if 0 < y + 1 < h - 1:
                spine_tiles.append((x, y + 1))
        else:
            if 0 < x + 1 < w - 1:
                spine_tiles.append((x + 1, y))

    # Paint spine - only overwrite ground tiles
    for x, y in spine_tiles:
        if game_map.in_bounds(x, y) and int(game_map.tiles["tile_id"][x, y]) == ground_tid:
            game_map.tiles[x, y] = path_tile

    # Branch paths from each door to nearest spine tile via BFS
    spine_set = {
        (x, y)
        for x, y in spine_tiles
        if game_map.in_bounds(x, y) and int(game_map.tiles["tile_id"][x, y]) == int(path_tile["tile_id"])
    }
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
    **kwargs: object,
) -> list[RectRoom]:
    """Colony village: open ground with irregular multi-wing buildings."""
    w, h = game_map.width, game_map.height
    rooms: list[RectRoom] = []
    label_counts: dict[str, int] = {}
    # Track all placed wing rectangles for collision checks
    placed_wings: list[RectRoom] = []

    # Pick a biome palette for this colony
    palette = pick_biome(rng)
    biome_ground = make_ground_tile(palette)
    path_tile = make_path_tile(palette, rng)

    game_map.biome = palette.name

    # Fill entire map with biome ground (shares ground tile_id)
    game_map.tiles[:] = biome_ground

    # Track door approach positions for path generation
    door_positions: list[tuple[int, int]] = []

    # Border wall around map edges
    game_map.tiles[0, :] = wall_tile
    game_map.tiles[w - 1, :] = wall_tile
    game_map.tiles[:, 0] = wall_tile
    game_map.tiles[:, h - 1] = wall_tile

    # Place ship dock landing pad before buildings so it gets a clear spot
    dock_room = _place_ship_dock(
        game_map,
        rng,
        placed_wings,
        path_tile,
        biome_ground,
    )

    # Square-footage budget: buildings may cover 50-60% of usable area
    usable_area = (w - 2) * (h - 2)
    target_coverage = rng.uniform(0.15, 0.30)
    max_sq_ft = int(usable_area * target_coverage)
    used_sq_ft = 0
    gap = 1  # minimum tiles between buildings

    # Place required rooms first, then fill
    all_specs = deque(_required_specs(profile))

    def _try_place_building(
        rx: int,
        ry: int,
        spec: RoomSpec,
    ) -> list[RectRoom] | None:
        """Attempt to place a building at (rx, ry). Return wing rects or None."""
        rw = rng.randint(spec.min_w, spec.max_w)
        rh = rng.randint(spec.min_h, spec.max_h)
        num_wings = _pick_building_room_count(rng)
        wing_tuples = _compose_building_wings(
            rng,
            rx,
            ry,
            rw,
            rh,
            num_wings,
            min_w=5,
            min_h=5,
        )
        result: list[RectRoom] = []
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
    grid_positions = [(gx, gy) for gx in range(2, w - 6, step_x) for gy in range(2, h - 6, step_y)]
    rng.shuffle(grid_positions)
    # Also add random jittered positions for gap-filling
    random_positions = [(rng.randint(2, max(2, w - 9)), rng.randint(2, max(2, h - 9))) for _ in range(150)]
    candidate_positions = grid_positions + random_positions
    retries_per_pos = 3  # retry with different wing configs

    for rx, ry in candidate_positions:
        if used_sq_ft >= max_sq_ft:
            break

        if all_specs:
            spec = all_specs.popleft()
        else:
            spec = _pick_room_spec(rng, profile, label_counts)

        wing_rects: list[RectRoom] | None = None
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
        all_sub_rooms: list[RectRoom] = []
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
                game_map,
                rng,
                wing.x1,
                wing.y1,
                wing.x2,
                wing.y2,
                num_sub,
                floor_tile,
                bldg_wall_tile,
                label=spec.label,
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

        building_sq_ft = sum((wr.x2 - wr.x1) * (wr.y2 - wr.y1) for wr in wing_rects)
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
