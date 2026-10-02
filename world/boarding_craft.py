"""Compose player + pirate ships into a single GameMap with an airtight corridor.

Algorithm:
  1. Player ship is placed at offset (0, 0).
  2. Pirate ship is placed adjacent to the player along one cardinal direction
     (east/south/west/north), with GAP tiles between the canvases so the two
     hulls never overlap.
  3. The closest pair of facing airlocks is chosen.
  4. A 1-tile-wide corridor (airlock_floor) is BFS-routed from the player's
     exterior_door to the pirate's exterior_door, traversing only SPACE tiles
     so it never crosses either ship's hull or glass.
  5. Every tile adjacent to a corridor tile that's still space gets stamped
     with a wall — the corridor is airtight.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from world import tile_types
from world.dungeon_gen import RectRoom
from world.game_map import GameMap
from world.grid import bfs, path_to

# Tiles between the two ship HULLS along the placement direction. Kept small
# so the corridor is short — the pirate ship's empty exterior canvas is
# collapsed by hull-bbox-based placement (see _placement_offsets).
GAP_BETWEEN_SHIPS: int = 2

# GameMap attributes the composite copies verbatim from the player ship map.
_INHERITED_MAP_STATE: tuple[str, ...] = ("space_seed", "debug_visible_all", "fov_radius", "fully_lit")


def _opposite(direction: tuple[int, int]) -> tuple[int, int]:
    return (-direction[0], -direction[1])


@dataclass
class CompositeLayout:
    """Result of composing two ships into one GameMap."""

    composite_map: GameMap
    player_offset: tuple[int, int]
    pirate_offset: tuple[int, int]
    spawn_room: RectRoom  # in composite coords; for spawning pirates
    corridor_tiles: list[tuple[int, int]]
    player_airlock_pos: tuple[int, int]  # exterior_door in composite coords
    pirate_airlock_pos: tuple[int, int]  # exterior_door in composite coords
    direction: tuple[int, int]  # outward-from-player direction
    # References to pirate-side entities & light_sources that were appended to
    # the shared player_map lists. Caller must remove these on resolve.
    pirate_entities_overlay: list = None  # type: ignore[assignment]
    pirate_light_sources_overlay: list = None  # type: ignore[assignment]


def find_compatible_airlock_pair(
    player_airlocks: list[dict],
    pirate_airlocks: list[dict],
    player_exit_pos: tuple[int, int] | None,
    rng: random.Random,
) -> tuple[dict, dict] | None:
    """Pick a (player_airlock, pirate_airlock) pair whose directions are opposite.

    Excludes the player's docking-hatch airlock. Returns ``None`` if no
    facing pair exists.
    """
    eligible_player = [a for a in player_airlocks if a.get("interior_door") != player_exit_pos]
    rng.shuffle(eligible_player)
    for pa in eligible_player:
        target = _opposite(tuple(pa["direction"]))
        for ra in pirate_airlocks:
            if tuple(ra["direction"]) == target:
                return pa, ra
    return None


def _hull_bbox(game_map: GameMap) -> tuple[int, int, int, int] | None:
    """Return (min_x, min_y, max_x, max_y) of non-space tiles."""
    space_tid = int(tile_types.space["tile_id"])
    non_space = game_map.tiles["tile_id"] != space_tid
    xs, ys = non_space.nonzero()
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _placement_offsets(
    player_map: GameMap,
    pirate_map: GameMap,
    p_ext: tuple[int, int],
    r_ext: tuple[int, int],
    direction: tuple[int, int],
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Position pirate so its hull is just past the player's hull (no overlap)
    and the chosen airlocks are aligned. Collapses each ship's empty canvas
    exterior so the corridor between airlocks stays short.
    """
    p_bbox = _hull_bbox(player_map)
    r_bbox = _hull_bbox(pirate_map)
    if p_bbox is None or r_bbox is None:
        # Degenerate maps; fall back to canvas-based placement.
        p_bbox = (0, 0, player_map.width - 1, player_map.height - 1)
        r_bbox = (0, 0, pirate_map.width - 1, pirate_map.height - 1)

    dx, dy = direction
    if dx == 1:  # pirate east of player
        # Use whichever offset places the pirate further east — guarantees no
        # hull overlap regardless of where the airlock sits inside its canvas.
        offset_x = max(
            p_ext[0] + GAP_BETWEEN_SHIPS + 1 - r_ext[0],  # airlock alignment
            p_bbox[2] + GAP_BETWEEN_SHIPS + 1 - r_bbox[0],  # hull non-overlap
        )
        pirate = (offset_x, p_ext[1] - r_ext[1])
    elif dx == -1:
        offset_x = min(
            p_ext[0] - GAP_BETWEEN_SHIPS - 1 - r_ext[0],
            p_bbox[0] - GAP_BETWEEN_SHIPS - 1 - r_bbox[2],
        )
        pirate = (offset_x, p_ext[1] - r_ext[1])
    elif dy == 1:
        offset_y = max(
            p_ext[1] + GAP_BETWEEN_SHIPS + 1 - r_ext[1],
            p_bbox[3] + GAP_BETWEEN_SHIPS + 1 - r_bbox[1],
        )
        pirate = (p_ext[0] - r_ext[0], offset_y)
    elif dy == -1:
        offset_y = min(
            p_ext[1] - GAP_BETWEEN_SHIPS - 1 - r_ext[1],
            p_bbox[1] - GAP_BETWEEN_SHIPS - 1 - r_bbox[3],
        )
        pirate = (p_ext[0] - r_ext[0], offset_y)
    else:
        raise ValueError(f"unsupported direction {direction}")

    shift_x = max(0, -pirate[0])
    shift_y = max(0, -pirate[1])
    return ((shift_x, shift_y), (pirate[0] + shift_x, pirate[1] + shift_y))


def _translate_airlock(airlock: dict, dx: int, dy: int) -> dict:
    """Return a new airlock dict with all positional fields shifted by (dx, dy)."""
    out = {
        "interior_door": (airlock["interior_door"][0] + dx, airlock["interior_door"][1] + dy),
        "exterior_door": (airlock["exterior_door"][0] + dx, airlock["exterior_door"][1] + dy),
        "direction": airlock["direction"],
        "switch": (
            (airlock["switch"][0] + dx, airlock["switch"][1] + dy) if airlock.get("switch") is not None else None
        ),
    }
    return out


def _bfs_corridor(
    composite: GameMap,
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]] | None:
    """4-connected BFS through SPACE tiles only. Returns path including endpoints, or None."""
    space_tid = int(tile_types.space["tile_id"])

    def passable(x: int, y: int) -> bool:
        return composite.in_bounds(x, y) and int(composite.tiles["tile_id"][x, y]) == space_tid

    if not passable(*start) or not passable(*goal):
        return None
    _, parent = bfs([start], passable)
    return path_to(parent, goal)


def compose_ships(
    player_map: GameMap,
    pirate_map: GameMap,
    pirate_rooms: list[RectRoom],
    player_airlock: dict,
    pirate_airlock: dict,
) -> CompositeLayout | None:
    """Build a composite GameMap containing both ships + an airtight corridor.

    Returns None when no airtight corridor can be routed through space (e.g.
    one of the airlocks is buried so deep in canvas exterior that the BFS
    would have to cross hull tiles to reach the other side).
    """
    pdir = tuple(player_airlock["direction"])
    rdir = tuple(pirate_airlock["direction"])
    assert rdir == _opposite(pdir), "airlocks must face each other"

    p_ext_native = tuple(player_airlock["exterior_door"])
    r_ext_native = tuple(pirate_airlock["exterior_door"])
    player_offset, pirate_offset = _placement_offsets(player_map, pirate_map, p_ext_native, r_ext_native, pdir)

    composite_w = max(player_map.width + player_offset[0], pirate_map.width + pirate_offset[0])
    composite_h = max(player_map.height + player_offset[1], pirate_map.height + pirate_offset[1])

    composite = GameMap(composite_w, composite_h, fill_tile=tile_types.space)
    # The composite stands in for the player map, so it inherits the render
    # and vacuum state the player map carried (starfield, debug reveal, FOV).
    composite.has_space = True
    for attr in _INHERITED_MAP_STATE:
        setattr(composite, attr, getattr(player_map, attr))

    # Player canvas (including its empty exterior) goes in first.
    for x in range(player_map.width):
        for y in range(player_map.height):
            composite.tiles[player_offset[0] + x, player_offset[1] + y] = player_map.tiles[x, y]
    composite.explored[
        player_offset[0] : player_offset[0] + player_map.width,
        player_offset[1] : player_offset[1] + player_map.height,
    ] = player_map.explored
    # Pirate canvas can overlap the player's empty exterior region in the
    # composite (because we placed by hull-bbox, not canvas-bbox). Skip
    # pirate's space tiles so they don't trample player structures; the
    # pirate hull tiles are guaranteed not to overlap player hull tiles.
    space_tid = int(tile_types.space["tile_id"])
    for x in range(pirate_map.width):
        for y in range(pirate_map.height):
            if int(pirate_map.tiles["tile_id"][x, y]) == space_tid:
                continue
            composite.tiles[pirate_offset[0] + x, pirate_offset[1] + y] = pirate_map.tiles[x, y]

    # Translate airlock positions into composite coords.
    p_ext = (
        player_offset[0] + player_airlock["exterior_door"][0],
        player_offset[1] + player_airlock["exterior_door"][1],
    )
    r_ext = (
        pirate_offset[0] + pirate_airlock["exterior_door"][0],
        pirate_offset[1] + pirate_airlock["exterior_door"][1],
    )
    p_int = (
        player_offset[0] + player_airlock["interior_door"][0],
        player_offset[1] + player_airlock["interior_door"][1],
    )
    r_int = (
        pirate_offset[0] + pirate_airlock["interior_door"][0],
        pirate_offset[1] + pirate_airlock["interior_door"][1],
    )

    # BFS from one tile outward of player exterior_door to one tile inward
    # of pirate exterior_door. We pathfind through SPACE tiles only — the
    # corridor never crosses either ship's hull or interior. Routed BEFORE
    # touching the shared entity/light lists so a failed composition leaves
    # the player map exactly as it was (callers retry with other seeds).
    pdx, pdy = pdir
    rdx, rdy = rdir
    bfs_start = (p_ext[0] + pdx, p_ext[1] + pdy)
    bfs_goal = (r_ext[0] + rdx, r_ext[1] + rdy)
    path = _bfs_corridor(composite, bfs_start, bfs_goal)
    if path is None:
        return None

    # ---- Merge entities, airlocks, and light sources from both ships ----
    # Player entities live ON the player_map.entities list (shared); we
    # translate their positions in place so they render at the correct spot in
    # the composite. They are untranslated again on resolve (see
    # restore_original_ship_map). Pirate entities are appended to the same
    # shared list so InteractAction etc. can find them; on resolve they're
    # removed by their references which we record on the Interdiction.
    pox, poy = player_offset
    for e in player_map.entities:
        e.x += pox
        e.y += poy
    composite.entities = player_map.entities  # share the list
    rox, roy = pirate_offset
    pirate_entities_overlay = list(pirate_map.entities)
    for e in pirate_entities_overlay:
        e.x += rox
        e.y += roy
        composite.entities.append(e)

    # Airlocks: composite gets a new list with translated copies of each
    # ship's airlocks, EXCLUDING the two connecting airlocks. Those airlocks
    # are fused permanently open as part of the corridor — leaving their
    # switches active would let the player flip one to open it as a vacuum
    # source, flooding both ships through the corridor.
    composite.airlocks = [
        _translate_airlock(a, pox, poy)
        for a in player_map.airlocks
        if tuple(a["interior_door"]) != tuple(player_airlock["interior_door"])
    ]
    composite.airlocks.extend(
        _translate_airlock(a, rox, roy)
        for a in pirate_map.airlocks
        if tuple(a["interior_door"]) != tuple(pirate_airlock["interior_door"])
    )

    # Light sources: same shared-list pattern as entities.
    for ls in player_map.light_sources:
        ls.x += pox
        ls.y += poy
    composite.light_sources = player_map.light_sources
    pirate_light_sources_overlay = list(pirate_map.light_sources)
    for ls in pirate_light_sources_overlay:
        ls.x += rox
        ls.y += roy
        composite.light_sources.append(ls)

    # Open both exterior + interior doors. Use airlock_floor (not
    # airlock_ext_open) for the exterior-door tiles: an "open exterior airlock"
    # is treated as a vacuum source by GameMap.recalculate_hazards and would
    # flood-fill vacuum through the corridor into both ship interiors. The
    # corridor is sealed end-to-end, so it should NOT be a vacuum source.
    composite.tiles[p_ext] = tile_types.airlock_floor
    composite.tiles[r_ext] = tile_types.airlock_floor
    composite.tiles[p_int] = tile_types.door_open
    composite.tiles[r_int] = tile_types.door_open

    # Carve corridor floor along the BFS path.
    path_set = set(path)
    for x, y in path:
        composite.tiles[x, y] = tile_types.airlock_floor
    # Stamp walls on every space-tile adjacent to the path so the corridor is
    # airtight. Diagonals count: movement is 8-directional, so a bare outer
    # corner at a bend would let the player step straight into space.
    for x, y in path:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if (nx, ny) in path_set:
                    continue
                if not composite.in_bounds(nx, ny):
                    continue
                if int(composite.tiles["tile_id"][nx, ny]) == space_tid:
                    composite.tiles[nx, ny] = tile_types.wall

    corridor_tiles = list(path)

    # Pick a pirate-ship room for spawning pirates — prefer the one farthest
    # from the connection airlock so they don't all rush the corridor instantly.
    def room_distance(room: RectRoom) -> int:
        rcx, rcy = room.center
        return abs(rcx - pirate_airlock["interior_door"][0]) + abs(rcy - pirate_airlock["interior_door"][1])

    chosen = max(pirate_rooms, key=room_distance) if pirate_rooms else None
    if chosen is None:
        spawn_room = RectRoom(r_int[0] - 1, r_int[1] - 1, 2, 2, label="pirate_ship")
    else:
        spawn_room = chosen.translated(*pirate_offset)
        spawn_room.label = spawn_room.label or "pirate_ship"

    return CompositeLayout(
        composite_map=composite,
        player_offset=player_offset,
        pirate_offset=pirate_offset,
        spawn_room=spawn_room,
        corridor_tiles=corridor_tiles,
        player_airlock_pos=p_ext,
        pirate_airlock_pos=r_ext,
        direction=pdir,
        pirate_entities_overlay=pirate_entities_overlay,
        pirate_light_sources_overlay=pirate_light_sources_overlay,
    )
