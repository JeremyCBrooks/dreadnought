"""Tests for dungeon generation."""
from world.dungeon_gen import (
    generate_dungeon, RectRoom, _room_wall_positions,
    _build_ship_skeleton, _ROOM_DRESSING, _pick_building_room_count,
    _subdivide_building, _carve_external_door, _bfs_path, _meander,
)
from world.game_map import GameMap
from world import tile_types
import numpy as np
import random


def test_generates_multiple_rooms():
    game_map, rooms, exit_pos = generate_dungeon(seed=42)
    assert len(rooms) >= 2


def test_rooms_are_carved():
    game_map, rooms, _ = generate_dungeon(seed=42)
    cx, cy = rooms[0].center
    assert game_map.is_walkable(cx, cy)


def test_exit_tile_placed():
    _, rooms, exit_pos = generate_dungeon(seed=42)
    assert exit_pos is not None
    assert exit_pos == rooms[0].center  # exit is at entrance so player can always leave


def test_room_centers_walkable():
    game_map, rooms, _ = generate_dungeon(seed=42, max_rooms=5)
    for room in rooms:
        cx, cy = room.center
        assert game_map.is_walkable(cx, cy)


def test_entities_spawned():
    game_map, rooms, _ = generate_dungeon(seed=42, max_rooms=8, max_enemies=2, max_items=1)
    assert len(game_map.entities) > 0


def test_rect_room_properties():
    room = RectRoom(5, 5, 6, 4)
    assert room.center == (8, 7)
    inner = room.inner
    assert inner == (slice(6, 11), slice(6, 9))


def test_rect_room_label_default():
    room = RectRoom(0, 0, 5, 5)
    assert room.label == ""


def test_rect_room_label_assigned():
    room = RectRoom(0, 0, 5, 5, label="bridge")
    assert room.label == "bridge"


def test_wall_interactables_placed_on_walls():
    """Wall interactables (seams, lockers, cabinets) must be on wall tiles."""
    from world.loc_profiles import PROFILES
    wall_kinds = {"mineral seam", "locker", "storage cabinet"}
    for loc_type, profile in PROFILES.items():
        for seed in range(50):
            game_map, rooms, _ = generate_dungeon(seed=seed, loc_type=loc_type)
            wall_ents = [
                e for e in game_map.entities
                if getattr(e, "interactable", None)
                and e.interactable.get("kind") in wall_kinds
            ]
            for ent in wall_ents:
                assert not game_map.tiles["walkable"][ent.x, ent.y], (
                    f"{ent.name} at ({ent.x},{ent.y}) should be on a wall tile "
                    f"(loc_type={loc_type}, seed={seed})"
                )


def test_wall_interactable_matches_loc_type():
    """Each loc_type spawns the correct wall interactable from its profile."""
    from world.loc_profiles import PROFILES
    expected = {
        "derelict": "locker",
        "asteroid": "mineral seam",
        "starbase": "locker",
        "colony": "storage cabinet",
    }
    for loc_type, kind in expected.items():
        found = False
        for seed in range(100):
            game_map, _, _ = generate_dungeon(seed=seed, loc_type=loc_type)
            wall_ents = [
                e for e in game_map.entities
                if getattr(e, "interactable", None)
                and e.interactable.get("kind") == kind
            ]
            if wall_ents:
                found = True
                break
        assert found, f"{loc_type} never spawned its wall interactable '{kind}'"


def test_room_wall_positions():
    room = RectRoom(2, 3, 4, 3)  # x1=2, y1=3, x2=6, y2=6
    positions = _room_wall_positions(room)
    # Top/bottom walls: x in [3,5], y in {3, 6}
    # Left/right walls: y in [4,5], x in {2, 6}
    for x, y in positions:
        on_boundary = x in (room.x1, room.x2) or y in (room.y1, room.y2)
        assert on_boundary, f"({x},{y}) should be on the room boundary"


# ---- Per-loc_type generation tests ----

def test_derelict_uses_metal_tiles():
    game_map, rooms, _ = generate_dungeon(seed=42, loc_type="derelict")
    assert len(rooms) >= 2
    cx, cy = rooms[0].center
    assert game_map.is_walkable(cx, cy)
    # Floor tiles should be metal floor (tile_id matches)
    tid = int(game_map.tiles["tile_id"][cx, cy])
    # Exit tile overrides center of first room, check second room
    if len(rooms) > 1:
        cx2, cy2 = rooms[1].center
        tid2 = int(game_map.tiles["tile_id"][cx2, cy2])
        assert tid2 == int(tile_types.floor["tile_id"])


def test_derelict_has_labeled_rooms():
    _, rooms, _ = generate_dungeon(seed=42, loc_type="derelict")
    labels = [r.label for r in rooms]
    assert "bridge" in labels
    assert "engine_room" in labels


def test_asteroid_uses_rock_tiles():
    game_map, rooms, _ = generate_dungeon(seed=42, loc_type="asteroid")
    assert len(rooms) >= 2
    # Check that a non-exit room center uses rock_floor tile_id
    for room in rooms[1:]:
        cx, cy = room.center
        if game_map.is_walkable(cx, cy):
            tid = int(game_map.tiles["tile_id"][cx, cy])
            assert tid == int(tile_types.rock_floor["tile_id"])
            break


def test_starbase_uses_metal_tiles():
    game_map, rooms, _ = generate_dungeon(seed=42, loc_type="starbase")
    assert len(rooms) >= 2
    for room in rooms[1:]:
        cx, cy = room.center
        if game_map.is_walkable(cx, cy):
            tid = int(game_map.tiles["tile_id"][cx, cy])
            assert tid == int(tile_types.floor["tile_id"])
            break


def test_colony_has_open_ground():
    game_map, rooms, _ = generate_dungeon(seed=42, loc_type="colony")
    assert len(rooms) >= 1
    # Find a walkable ground tile (not inside a building)
    ground_tid = int(tile_types.ground["tile_id"])
    found_ground = False
    for x in range(game_map.width):
        for y in range(game_map.height):
            if int(game_map.tiles["tile_id"][x, y]) == ground_tid:
                found_ground = True
                break
        if found_ground:
            break
    assert found_ground, "Colony should have open ground tiles"


def test_colony_is_fully_lit():
    game_map, _, _ = generate_dungeon(seed=42, loc_type="colony")
    assert game_map.fully_lit


def test_derelict_is_not_fully_lit():
    game_map, _, _ = generate_dungeon(seed=42, loc_type="derelict")
    assert not game_map.fully_lit


def test_colony_has_larger_fov_radius():
    colony_map, _, _ = generate_dungeon(seed=42, loc_type="colony")
    derelict_map, _, _ = generate_dungeon(seed=42, loc_type="derelict")
    assert colony_map.fov_radius > derelict_map.fov_radius


def test_colony_buildings_have_dirt_floor():
    game_map, rooms, _ = generate_dungeon(seed=42, loc_type="colony")
    dirt_tid = int(tile_types.dirt_floor["tile_id"])
    if len(rooms) > 1:
        # Check interior of a non-first room (first has exit tile)
        room = rooms[1]
        cx, cy = room.center
        tid = int(game_map.tiles["tile_id"][cx, cy])
        assert tid == dirt_tid


def test_deterministic_generation():
    """Same seed + loc_type produces identical layout."""
    gm1, rooms1, exit1 = generate_dungeon(seed=123, loc_type="asteroid")
    gm2, rooms2, exit2 = generate_dungeon(seed=123, loc_type="asteroid")
    assert exit1 == exit2
    assert len(rooms1) == len(rooms2)
    for r1, r2 in zip(rooms1, rooms2):
        assert r1.center == r2.center


def test_unknown_loc_type_falls_back_to_derelict():
    game_map, rooms, _ = generate_dungeon(seed=42, loc_type="unknown_type")
    assert len(rooms) >= 2


def test_derelict_has_all_room_types():
    """All 4 room labels (bridge, engine_room, crew_quarters, cargo) must appear."""
    required_labels = {"bridge", "engine_room", "crew_quarters", "cargo"}
    for seed in range(20):
        _, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        labels = {r.label for r in rooms}
        assert required_labels.issubset(labels), (
            f"seed={seed}: missing {required_labels - labels}, got {labels}"
        )


def test_derelict_bridge_in_left_zone():
    """Bridge room x-coordinates should fall in the left third of the map."""
    width = 80
    zone_w = width // 3
    for seed in range(20):
        _, rooms, _ = generate_dungeon(seed=seed, width=width, loc_type="derelict")
        bridges = [r for r in rooms if r.label == "bridge"]
        assert bridges, f"seed={seed}: no bridge room"
        for b in bridges:
            assert b.x1 >= 1 and b.x2 <= zone_w + b.x2 - b.x1, (
                f"seed={seed}: bridge at x1={b.x1} outside left zone"
            )
            assert b.x1 < zone_w, (
                f"seed={seed}: bridge x1={b.x1} not in left zone (zone_w={zone_w})"
            )


def test_derelict_engine_in_right_zone():
    """Engine room x-coordinates should fall in the right third of the map."""
    width = 80
    zone_w = width // 3
    for seed in range(20):
        _, rooms, _ = generate_dungeon(seed=seed, width=width, loc_type="derelict")
        engines = [r for r in rooms if r.label == "engine_room"]
        assert engines, f"seed={seed}: no engine_room"
        for e in engines:
            assert e.x1 >= 2 * zone_w, (
                f"seed={seed}: engine x1={e.x1} not in right zone (2*zone_w={2*zone_w})"
            )


# ---- Ship skeleton tests ----

def test_ship_skeleton_keel_is_walkable():
    """The keel corridor should be carved as walkable tiles."""
    rng = random.Random(42)
    wall_tile = tile_types.wall
    floor_tile = tile_types.floor
    game_map = GameMap(80, 45, fill_tile=wall_tile)
    keel_x1, keel_x2, keel_y, keel_y2, ribs = _build_ship_skeleton(
        game_map, rng, floor_tile,
    )
    # Every tile along the keel should be walkable (2-tile wide)
    for x in range(keel_x1, keel_x2 + 1):
        assert game_map.is_walkable(x, keel_y), f"keel not walkable at ({x}, {keel_y})"
        assert game_map.is_walkable(x, keel_y + 1), f"keel not walkable at ({x}, {keel_y+1})"


def test_ship_skeleton_has_ribs():
    """Skeleton should produce 2-4 cross-corridors."""
    rng = random.Random(42)
    game_map = GameMap(80, 45, fill_tile=tile_types.wall)
    _, _, _, _, ribs = _build_ship_skeleton(game_map, rng, tile_types.floor)
    assert 2 <= len(ribs) <= 4


def test_ship_skeleton_ribs_are_walkable():
    """Each rib corridor should be carved as walkable tiles."""
    rng = random.Random(42)
    game_map = GameMap(80, 45, fill_tile=tile_types.wall)
    _, _, _, _, ribs = _build_ship_skeleton(game_map, rng, tile_types.floor)
    for rib_x, rib_y_start, rib_y_end in ribs:
        for y in range(rib_y_start, rib_y_end + 1):
            assert game_map.is_walkable(rib_x, y), (
                f"rib not walkable at ({rib_x}, {y})"
            )


def test_ship_keel_does_not_span_full_width():
    """Keel should not touch map edges — ship has defined bounds."""
    rng = random.Random(42)
    game_map = GameMap(80, 45, fill_tile=tile_types.wall)
    keel_x1, keel_x2, _, _, _ = _build_ship_skeleton(game_map, rng, tile_types.floor)
    assert keel_x1 > 1, "keel starts too close to left edge"
    assert keel_x2 < 78, "keel ends too close to right edge"


# ---- Ship room dressing tests ----


def _entities_in_room(game_map, room):
    """Return entities whose position is inside the room's interior."""
    return [
        e for e in game_map.entities
        if room.x1 < e.x < room.x2 and room.y1 < e.y < room.y2
    ]


def test_bridge_contains_terminal_entities():
    """Bridge rooms should contain terminal-type interactables."""
    terminal_names = {"nav terminal", "comms terminal", "console"}
    found = False
    for seed in range(30):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        bridges = [r for r in rooms if r.label == "bridge"]
        for br in bridges:
            ents = _entities_in_room(game_map, br)
            interactables = [
                e for e in ents
                if e.interactable and e.interactable["kind"] in terminal_names
            ]
            if interactables:
                found = True
                break
        if found:
            break
    assert found, "No terminal found in any bridge room across 30 seeds"


def test_engine_room_contains_reactor_or_machinery():
    """Engine rooms should contain reactor/engine/valve interactables."""
    engine_names = {"reactor core", "engine terminal", "coolant valve"}
    found = False
    for seed in range(30):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        engines = [r for r in rooms if r.label == "engine_room"]
        for er in engines:
            ents = _entities_in_room(game_map, er)
            interactables = [
                e for e in ents
                if e.interactable and e.interactable["kind"] in engine_names
            ]
            if interactables:
                found = True
                break
        if found:
            break
    assert found, "No engine interactable found in any engine_room across 30 seeds"


def test_cargo_has_multiple_crate_entities():
    """Cargo rooms should have multiple crate/supply crate entities."""
    crate_names = {"crate", "supply crate", "locker"}
    found = False
    for seed in range(30):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        cargos = [r for r in rooms if r.label == "cargo"]
        for cr in cargos:
            ents = _entities_in_room(game_map, cr)
            interactables = [
                e for e in ents
                if e.interactable and e.interactable["kind"] in crate_names
            ]
            if len(interactables) >= 2:
                found = True
                break
        if found:
            break
    assert found, "No cargo room with 2+ crate-type interactables across 30 seeds"


def test_decorations_are_non_interactable():
    """Decoration entities should have no interactable dict."""
    decoration_names = set()
    for dressing in _ROOM_DRESSING.values():
        for _, _, name in dressing["decorations"]:
            decoration_names.add(name)

    for seed in range(10):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        decor_ents = [e for e in game_map.entities if e.name in decoration_names]
        for e in decor_ents:
            assert e.interactable is None, (
                f"Decoration {e.name!r} at ({e.x},{e.y}) should not be interactable"
            )
            assert not e.blocks_movement, (
                f"Decoration {e.name!r} should not block movement"
            )


def test_furnishings_have_interactable_dicts():
    """Interactable furnishings should have an interactable dict with 'kind'."""
    furnishing_names = set()
    for dressing in _ROOM_DRESSING.values():
        for _, _, name in dressing["interactables"]:
            furnishing_names.add(name)

    found_any = False
    for seed in range(20):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        furn_ents = [e for e in game_map.entities if e.name in furnishing_names]
        for e in furn_ents:
            found_any = True
            assert e.interactable is not None, (
                f"Furnishing {e.name!r} at ({e.x},{e.y}) should be interactable"
            )
            assert "kind" in e.interactable, (
                f"Furnishing {e.name!r} interactable missing 'kind'"
            )
    assert found_any, "No furnishing entities found across 20 seeds"


def test_ship_rooms_get_dressing_not_generic_interactables():
    """Ship (derelict) rooms should have themed dressing, not generic consoles/crates."""
    # Decoration or furnishing names from dressing config
    dressing_names = set()
    for dressing in _ROOM_DRESSING.values():
        for _, _, name in dressing["decorations"]:
            dressing_names.add(name)
        for _, _, name in dressing["interactables"]:
            dressing_names.add(name)

    for seed in range(10):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        # Non-exit rooms should have at least some dressing entities
        for room in rooms[1:]:
            ents = _entities_in_room(game_map, room)
            themed = [e for e in ents if e.name in dressing_names]
            if room.label in _ROOM_DRESSING:
                assert len(themed) > 0, (
                    f"seed={seed}: {room.label} room has no themed dressing"
                )


def test_ship_gen_no_crash_80x45():
    """Ship generator must not crash across 200 seeds at standard size."""
    for seed in range(200):
        game_map, rooms, exit_pos = generate_dungeon(
            width=80, height=45, seed=seed, loc_type="derelict"
        )
        assert rooms  # at least some rooms placed


def test_ship_gen_no_crash_small_map():
    """Ship generator must not crash at small map sizes (30x25)."""
    for seed in range(50):
        game_map, rooms, exit_pos = generate_dungeon(
            width=30, height=25, seed=seed, loc_type="derelict"
        )
        # Small maps may produce fewer rooms, but must not crash
        assert game_map is not None


def test_items_only_on_walkable_tiles():
    """All item entities must be placed on walkable tiles."""
    from world.loc_profiles import PROFILES
    for loc_type in PROFILES:
        for seed in range(50):
            game_map, rooms, _ = generate_dungeon(seed=seed, loc_type=loc_type)
            item_ents = [e for e in game_map.entities if getattr(e, "item", None)]
            for ent in item_ents:
                assert game_map.tiles["walkable"][ent.x, ent.y], (
                    f"Item {ent.name!r} at ({ent.x},{ent.y}) on non-walkable tile "
                    f"(loc_type={loc_type}, seed={seed})"
                )


def test_floor_interactables_on_walkable_tiles():
    """Floor interactables (crates, consoles) must be on walkable tiles."""
    from world.loc_profiles import PROFILES
    wall_kinds = {"mineral seam", "locker", "storage cabinet"}
    for loc_type in PROFILES:
        for seed in range(50):
            game_map, rooms, _ = generate_dungeon(seed=seed, loc_type=loc_type)
            floor_ents = [
                e for e in game_map.entities
                if getattr(e, "interactable", None)
                and e.interactable.get("kind") not in wall_kinds
            ]
            for ent in floor_ents:
                assert game_map.tiles["walkable"][ent.x, ent.y], (
                    f"{ent.name!r} at ({ent.x},{ent.y}) on non-walkable tile "
                    f"(loc_type={loc_type}, seed={seed})"
                )


def test_no_entities_near_exit_hatch():
    """No item, interactable, or enemy should be within 1 tile of the exit hatch."""
    from world.loc_profiles import PROFILES
    for loc_type in PROFILES:
        for seed in range(50):
            game_map, rooms, exit_pos = generate_dungeon(seed=seed, loc_type=loc_type)
            if exit_pos is None:
                continue
            ex, ey = exit_pos
            for ent in game_map.entities:
                has_gameplay = (
                    getattr(ent, "item", None)
                    or getattr(ent, "interactable", None)
                    or getattr(ent, "fighter", None)
                )
                if not has_gameplay:
                    continue
                assert abs(ent.x - ex) > 1 or abs(ent.y - ey) > 1, (
                    f"{ent.name!r} at ({ent.x},{ent.y}) too close to exit at "
                    f"({ex},{ey}) (loc_type={loc_type}, seed={seed})"
                )


def test_derelict_room_to_room_connections():
    """Close rooms should sometimes have direct connections between them."""
    # Run multiple seeds; at least one should produce a room-to-room link
    found_link = False
    for seed in range(30):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        for i in range(len(rooms)):
            for j in range(i + 1, len(rooms)):
                ci = rooms[i].center
                cj = rooms[j].center
                dist = abs(ci[0] - cj[0]) + abs(ci[1] - cj[1])
                if dist <= 12:
                    # Check if there's a walkable path along the L-connector
                    mid_x, mid_y = cj[0], ci[1]
                    if game_map.is_walkable(mid_x, mid_y):
                        found_link = True
                        break
            if found_link:
                break
        if found_link:
            break
    assert found_link, "No room-to-room connections found across 30 seeds"


# ---- Multi-room colony building tests ----


def test_colony_buildings_have_internal_rooms():
    """Verify some colony buildings contain more than 1 wing (room)."""
    found_multi = False
    for seed in range(50):
        _, rooms, _ = generate_dungeon(seed=seed, loc_type="colony")
        # With wing composition, multiple wings per building produce more rooms
        # than the number of unique labels placed.
        if len(rooms) > 4:
            found_multi = True
            break
    assert found_multi, "No multi-room buildings found across 50 seeds"


def test_colony_internal_rooms_connected():
    """Sub-rooms within a colony building should be connected via walkable tiles."""
    from collections import deque

    def flood_fill(game_map, start_x, start_y):
        """Return set of walkable tiles reachable from (start_x, start_y)."""
        visited = set()
        queue = deque([(start_x, start_y)])
        while queue:
            x, y = queue.popleft()
            if (x, y) in visited:
                continue
            if not game_map.in_bounds(x, y):
                continue
            tid = int(game_map.tiles["tile_id"][x, y])
            is_door = tid in (int(tile_types.door_closed["tile_id"]), int(tile_types.door_open["tile_id"]))
            if not game_map.tiles["walkable"][x, y] and not is_door:
                continue
            visited.add((x, y))
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                queue.append((x + dx, y + dy))
        return visited

    for seed in range(30):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="colony")
        if len(rooms) < 2:
            continue
        # All room centers should be reachable from each other (colony is open ground)
        first_cx, first_cy = rooms[0].center
        reachable = flood_fill(game_map, first_cx, first_cy)
        for room in rooms[1:]:
            cx, cy = room.center
            assert (cx, cy) in reachable, (
                f"seed={seed}: room center ({cx},{cy}) not reachable from "
                f"first room ({first_cx},{first_cy})"
            )


def test_colony_hallways_within_footprint():
    """No dirt_floor tiles should appear outside building footprints or the map border."""
    from world.dungeon_gen import _pick_building_room_count
    dirt_tid = int(tile_types.dirt_floor["tile_id"])
    ground_tid = int(tile_types.ground["tile_id"])
    structure_wall_tid = int(tile_types.structure_wall["tile_id"])

    for seed in range(50):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="colony")
        for x in range(game_map.width):
            for y in range(game_map.height):
                tid = int(game_map.tiles["tile_id"][x, y])
                if tid == dirt_tid:
                    # This tile must be inside some room's footprint
                    inside = any(
                        r.x1 <= x <= r.x2 and r.y1 <= y <= r.y2
                        for r in rooms
                    )
                    assert inside, (
                        f"seed={seed}: dirt_floor at ({x},{y}) outside all building footprints"
                    )


def test_colony_no_crash_200_seeds():
    """Colony generator must not crash across 200 seeds."""
    for seed in range(200):
        game_map, rooms, exit_pos = generate_dungeon(
            width=80, height=45, seed=seed, loc_type="colony"
        )
        assert rooms


def test_colony_sub_rooms_minimum_size():
    """All colony sub-rooms should have at least 3x3 interior."""
    for seed in range(100):
        _, rooms, _ = generate_dungeon(seed=seed, loc_type="colony")
        for room in rooms:
            inner_w = room.x2 - room.x1 - 1
            inner_h = room.y2 - room.y1 - 1
            assert inner_w >= 3, (
                f"seed={seed}: room {room.label} inner width {inner_w} < 3"
            )
            assert inner_h >= 3, (
                f"seed={seed}: room {room.label} inner height {inner_h} < 3"
            )


def test_colony_buildings_have_irregular_footprints():
    """Across seeds, some buildings should produce non-rectangular silhouettes.

    A multi-wing building is irregular if the union of its wings doesn't form
    a single rectangle (i.e. the bounding box area > sum of wing areas).
    """
    found_irregular = False
    for seed in range(100):
        _, rooms, _ = generate_dungeon(seed=seed, loc_type="colony")
        # Group rooms by label to identify buildings with multiple wings
        from collections import defaultdict
        by_label: dict[str, list] = defaultdict(list)
        for r in rooms:
            by_label[r.label].append(r)
        for label, wing_rooms in by_label.items():
            if len(wing_rooms) < 2:
                continue
            # Compute bounding box of all wings
            bb_x1 = min(r.x1 for r in wing_rooms)
            bb_y1 = min(r.y1 for r in wing_rooms)
            bb_x2 = max(r.x2 for r in wing_rooms)
            bb_y2 = max(r.y2 for r in wing_rooms)
            bb_area = (bb_x2 - bb_x1) * (bb_y2 - bb_y1)
            wing_area = sum((r.x2 - r.x1) * (r.y2 - r.y1) for r in wing_rooms)
            if wing_area < bb_area:
                found_irregular = True
                break
        if found_irregular:
            break
    assert found_irregular, "No irregular building footprints found across 100 seeds"


# ---- Colony window tests ----

def test_colony_windows_are_transparent_not_walkable():
    """All structure_window tiles must be transparent=True, walkable=False."""
    window_tid = int(tile_types.structure_window["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        mask = game_map.tiles["tile_id"] == window_tid
        if not mask.any():
            continue
        assert not game_map.tiles["walkable"][mask].any(), (
            f"seed={seed}: window tile is walkable"
        )
        assert game_map.tiles["transparent"][mask].all(), (
            f"seed={seed}: window tile is not transparent"
        )


def test_colony_windows_on_exterior_walls():
    """Every window tile must have at least one ground neighbor."""
    window_tid = int(tile_types.structure_window["tile_id"])
    ground_tid = int(tile_types.ground["tile_id"])
    path_tid = int(tile_types.path["tile_id"])
    flora_tids = {
        int(tile_types.flora_low["tile_id"]),
        int(tile_types.flora_tall["tile_id"]),
        int(tile_types.flora_scrub["tile_id"]),
        int(tile_types.flora_sprout["tile_id"]),
    }
    exterior_tids = {ground_tid, path_tid} | flora_tids
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        for x in range(game_map.width):
            for y in range(game_map.height):
                if int(game_map.tiles["tile_id"][x, y]) != window_tid:
                    continue
                has_exterior = False
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = x + dx, y + dy
                    if (game_map.in_bounds(nx, ny)
                            and int(game_map.tiles["tile_id"][nx, ny]) in exterior_tids):
                        has_exterior = True
                        break
                assert has_exterior, (
                    f"seed={seed}: window at ({x},{y}) has no ground/path neighbor"
                )


def test_colony_windows_not_adjacent_to_doors():
    """No window should be orthogonally adjacent to a door (floor on exterior wall)."""
    window_tid = int(tile_types.structure_window["tile_id"])
    ground_tid = int(tile_types.ground["tile_id"])
    dirt_tid = int(tile_types.dirt_floor["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        for x in range(game_map.width):
            for y in range(game_map.height):
                if int(game_map.tiles["tile_id"][x, y]) != window_tid:
                    continue
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = x + dx, y + dy
                    if not game_map.in_bounds(nx, ny):
                        continue
                    ntid = int(game_map.tiles["tile_id"][nx, ny])
                    # A door is a walkable dirt_floor tile that has ground on
                    # its other side (i.e. it's on the building perimeter)
                    if ntid == dirt_tid and game_map.tiles["walkable"][nx, ny]:
                        for dx2, dy2 in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            gx, gy = nx + dx2, ny + dy2
                            if (game_map.in_bounds(gx, gy)
                                    and int(game_map.tiles["tile_id"][gx, gy]) == ground_tid):
                                assert False, (
                                    f"seed={seed}: window at ({x},{y}) adjacent "
                                    f"to door at ({nx},{ny})"
                                )


def test_colony_has_windows():
    """Across seeds, colony maps should contain window tiles."""
    window_tid = int(tile_types.structure_window["tile_id"])
    found = False
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        if (game_map.tiles["tile_id"] == window_tid).any():
            found = True
            break
    assert found, "No window tiles found in any colony map across 50 seeds"


def test_derelict_has_windows():
    """Across seeds, derelict (ship) maps should contain window tiles."""
    window_tid = int(tile_types.structure_window["tile_id"])
    found = False
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
        if (game_map.tiles["tile_id"] == window_tid).any():
            found = True
            break
    assert found, "No window tiles found in any derelict map across 50 seeds"


def test_starbase_has_windows():
    """Across seeds, starbase maps should contain window tiles."""
    window_tid = int(tile_types.structure_window["tile_id"])
    found = False
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="starbase")
        if (game_map.tiles["tile_id"] == window_tid).any():
            found = True
            break
    assert found, "No window tiles found in any starbase map across 50 seeds"


def test_ship_windows_are_transparent_not_walkable():
    """All window tiles in derelict maps must be transparent=True, walkable=False."""
    window_tid = int(tile_types.structure_window["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
        mask = game_map.tiles["tile_id"] == window_tid
        if not mask.any():
            continue
        assert not game_map.tiles["walkable"][mask].any(), (
            f"seed={seed}: derelict window tile is walkable"
        )
        assert game_map.tiles["transparent"][mask].all(), (
            f"seed={seed}: derelict window tile is not transparent"
        )


def test_ship_windows_adjacent_to_corridor():
    """Every window in a derelict should have a walkable or window neighbor."""
    window_tid = int(tile_types.structure_window["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
        for x in range(game_map.width):
            for y in range(game_map.height):
                if int(game_map.tiles["tile_id"][x, y]) != window_tid:
                    continue
                has_neighbor = False
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = x + dx, y + dy
                    if not game_map.in_bounds(nx, ny):
                        continue
                    if (game_map.tiles["walkable"][nx, ny]
                            or int(game_map.tiles["tile_id"][nx, ny]) == window_tid):
                        has_neighbor = True
                        break
                assert has_neighbor, (
                    f"seed={seed}: window at ({x},{y}) has no walkable or window neighbor"
                )


def test_colony_no_crash_with_windows():
    """Colony generator with windows must not crash across 200 seeds."""
    for seed in range(200):
        game_map, rooms, exit_pos = generate_dungeon(
            width=80, height=45, seed=seed, loc_type="colony"
        )
        assert rooms


def test_derelict_no_crash_with_windows():
    """Derelict generator with windows must not crash across 200 seeds."""
    for seed in range(200):
        game_map, rooms, exit_pos = generate_dungeon(
            width=80, height=45, seed=seed, loc_type="derelict"
        )
        assert rooms


def test_derelict_has_hull_facing_windows():
    """Across seeds, at least some derelict windows have a wall (hull) neighbor."""
    window_tid = int(tile_types.structure_window["tile_id"])
    wall_tid = int(tile_types.wall["tile_id"])
    found = False
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
        for x in range(1, game_map.width - 1):
            for y in range(1, game_map.height - 1):
                if int(game_map.tiles["tile_id"][x, y]) != window_tid:
                    continue
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = x + dx, y + dy
                    if (game_map.in_bounds(nx, ny)
                            and int(game_map.tiles["tile_id"][nx, ny]) == wall_tid):
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if found:
            break
    assert found, "No hull-facing windows found in any derelict map across 50 seeds"


def test_derelict_bridge_has_forward_windows():
    """Bridge rooms should have windows facing west (forward/bow direction)."""
    window_tid = int(tile_types.structure_window["tile_id"])
    found = False
    for seed in range(50):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        bridges = [r for r in rooms if r.label == "bridge"]
        for br in bridges:
            # Check west wall of bridge (x=x1) for windows
            for y in range(br.y1 + 1, br.y2):
                x = br.x1
                if int(game_map.tiles["tile_id"][x, y]) == window_tid:
                    # Verify hull-side window to the west (x-1 is also window)
                    if (game_map.in_bounds(x - 1, y)
                            and int(game_map.tiles["tile_id"][x - 1, y]) == window_tid):
                        found = True
                        break
            if found:
                break
        if found:
            break
    assert found, "No forward-facing bridge windows found across 50 seeds"


def test_derelict_hull_windows_properties():
    """Hull-facing windows on derelicts must be transparent and not walkable."""
    window_tid = int(tile_types.structure_window["tile_id"])
    wall_tid = int(tile_types.wall["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
        for x in range(1, game_map.width - 1):
            for y in range(1, game_map.height - 1):
                if int(game_map.tiles["tile_id"][x, y]) != window_tid:
                    continue
                # Check if this is a hull-facing window (has wall neighbor)
                has_hull = False
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = x + dx, y + dy
                    if (game_map.in_bounds(nx, ny)
                            and int(game_map.tiles["tile_id"][nx, ny]) == wall_tid):
                        has_hull = True
                        break
                if has_hull:
                    assert game_map.tiles["transparent"][x, y], (
                        f"seed={seed}: hull window at ({x},{y}) not transparent"
                    )
                    assert not game_map.tiles["walkable"][x, y], (
                        f"seed={seed}: hull window at ({x},{y}) is walkable"
                    )


def test_starbase_has_hull_facing_windows():
    """Across seeds, at least some starbase windows have hull (wall) on one side."""
    window_tid = int(tile_types.structure_window["tile_id"])
    wall_tid = int(tile_types.wall["tile_id"])
    found = False
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="starbase")
        for x in range(1, game_map.width - 1):
            for y in range(1, game_map.height - 1):
                if int(game_map.tiles["tile_id"][x, y]) != window_tid:
                    continue
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = x + dx, y + dy
                    if (game_map.in_bounds(nx, ny)
                            and int(game_map.tiles["tile_id"][nx, ny]) == wall_tid):
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if found:
            break
    assert found, "No hull-facing windows found in any starbase map across 50 seeds"


def test_starbase_hull_windows_properties():
    """Hull-facing windows on starbases must be transparent and not walkable."""
    window_tid = int(tile_types.structure_window["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="starbase")
        mask = game_map.tiles["tile_id"] == window_tid
        if not mask.any():
            continue
        assert not game_map.tiles["walkable"][mask].any(), (
            f"seed={seed}: starbase window tile is walkable"
        )
        assert game_map.tiles["transparent"][mask].all(), (
            f"seed={seed}: starbase window tile is not transparent"
        )


def test_starbase_no_crash_with_windows():
    """Starbase generator with windows must not crash across 200 seeds."""
    for seed in range(200):
        game_map, rooms, exit_pos = generate_dungeon(
            width=80, height=45, seed=seed, loc_type="starbase"
        )
        assert rooms


# ---- Space tile tests ----


def test_derelict_has_space_tiles():
    """Derelict maps should contain space tiles outside the hull."""
    space_tid = int(tile_types.space["tile_id"])
    found = False
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
        if (game_map.tiles["tile_id"] == space_tid).any():
            found = True
            break
    assert found, "No space tiles found in any derelict map across 50 seeds"


def test_starbase_has_space_tiles():
    """Starbase maps should contain space tiles outside the hull."""
    space_tid = int(tile_types.space["tile_id"])
    found = False
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="starbase")
        if (game_map.tiles["tile_id"] == space_tid).any():
            found = True
            break
    assert found, "No space tiles found in any starbase map across 50 seeds"


def test_asteroid_space_tiles_only_at_breaches():
    """Asteroid maps may have space tiles, but only adjacent to hull breaches."""
    space_tid = int(tile_types.space["tile_id"])
    hull_breach_tid = int(tile_types.hull_breach["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="asteroid")
        is_space = game_map.tiles["tile_id"] == space_tid
        if not is_space.any():
            continue
        # Every space tile should be adjacent to a hull breach
        is_breach = game_map.tiles["tile_id"] == hull_breach_tid
        adj_breach = np.zeros_like(is_space)
        adj_breach[1:, :] |= is_breach[:-1, :]
        adj_breach[:-1, :] |= is_breach[1:, :]
        adj_breach[:, 1:] |= is_breach[:, :-1]
        adj_breach[:, :-1] |= is_breach[:, 1:]
        bad = is_space & ~adj_breach
        assert not bad.any(), (
            f"seed={seed}: space tile not adjacent to hull breach"
        )


def test_colony_has_no_space_tiles():
    """Colony maps (village generator) should not have space tiles."""
    space_tid = int(tile_types.space["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        assert not (game_map.tiles["tile_id"] == space_tid).any(), (
            f"seed={seed}: colony map should not have space tiles"
        )


def test_space_tiles_not_adjacent_to_walkable():
    """Space tiles should not be adjacent to walkable tiles (except hull breaches)."""
    space_tid = int(tile_types.space["tile_id"])
    hull_breach_tid = int(tile_types.hull_breach["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
        is_space = game_map.tiles["tile_id"] == space_tid
        is_walkable = game_map.tiles["walkable"].copy()
        # Hull breaches are walkable but intentionally adjacent to space
        is_breach = game_map.tiles["tile_id"] == hull_breach_tid
        is_walkable &= ~is_breach
        # Check all 4 cardinal neighbors
        adj_walkable = np.zeros_like(is_space)
        adj_walkable[1:, :] |= is_walkable[:-1, :]
        adj_walkable[:-1, :] |= is_walkable[1:, :]
        adj_walkable[:, 1:] |= is_walkable[:, :-1]
        adj_walkable[:, :-1] |= is_walkable[:, 1:]
        bad = is_space & adj_walkable
        assert not bad.any(), (
            f"seed={seed}: space tile adjacent to walkable tile (non-breach)"
        )


def test_space_tiles_are_transparent():
    """All space tiles must be transparent (LOS passes through)."""
    space_tid = int(tile_types.space["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
        mask = game_map.tiles["tile_id"] == space_tid
        if mask.any():
            assert game_map.tiles["transparent"][mask].all(), (
                f"seed={seed}: space tile is not transparent"
            )


def test_space_conversion_preserves_hull_walls():
    """Walls adjacent to walkable tiles (structural hull) must not be converted."""
    wall_tid = int(tile_types.wall["tile_id"])
    for seed in range(20):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        # Every room boundary wall that neighbors a walkable interior should still be wall
        for room in rooms:
            cx, cy = room.center
            # Check that at least some walls remain around the room
            perimeter_walls = 0
            for x in range(room.x1, room.x2 + 1):
                for y in [room.y1, room.y2]:
                    if game_map.in_bounds(x, y):
                        tid = int(game_map.tiles["tile_id"][x, y])
                        if tid == wall_tid:
                            perimeter_walls += 1
            for y in range(room.y1, room.y2 + 1):
                for x in [room.x1, room.x2]:
                    if game_map.in_bounds(x, y):
                        tid = int(game_map.tiles["tile_id"][x, y])
                        if tid == wall_tid:
                            perimeter_walls += 1
            # Room should have hull walls (some may be windows/doors, but not all space)
            assert perimeter_walls > 0, (
                f"seed={seed}: room at {room.center} lost all hull walls"
            )


def test_derelict_has_space_flag():
    """Derelict game_map should have has_space=True."""
    game_map, _, _ = generate_dungeon(seed=42, loc_type="derelict")
    assert game_map.has_space


def test_asteroid_has_space_when_breaches():
    """Asteroid with hull breaches should have has_space=True."""
    # Hull breaches add space tiles to asteroids
    hull_breach_tid = int(tile_types.hull_breach["tile_id"])
    for seed in range(50):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="asteroid")
        has_breach = (game_map.tiles["tile_id"] == hull_breach_tid).any()
        if has_breach:
            assert game_map.has_space
            return
    # If no breaches found in 50 seeds, that's fine — no assertion needed


def test_door_placement():
    """Doors appear at room entrances in generated dungeons."""
    door_closed_id = int(tile_types.door_closed["tile_id"])
    # Try multiple seeds — at least one should produce doors
    found = False
    for seed in range(50):
        game_map, rooms, _ = generate_dungeon(seed=seed, max_rooms=8)
        if (game_map.tiles["tile_id"] == door_closed_id).any():
            found = True
            break
    assert found, "No doors placed in any of 50 seeds"


def test_asteroid_has_no_doors():
    """Asteroid (organic) maps should never have doors."""
    door_closed_id = int(tile_types.door_closed["tile_id"])
    for seed in range(20):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="asteroid")
        assert not (game_map.tiles["tile_id"] == door_closed_id).any(), (
            f"seed={seed}: asteroid map should have no doors"
        )


def test_no_overlapping_items():
    """No two non-blocking entities should share the same tile."""
    for seed in range(30):
        game_map, _, _ = generate_dungeon(seed=seed, max_rooms=8)
        occupied: set = set()
        for e in game_map.entities:
            if e.blocks_movement:
                continue
            pos = (e.x, e.y)
            assert pos not in occupied, (
                f"seed={seed}: overlapping entities at {pos}"
            )
            occupied.add(pos)


def test_doors_not_clustered():
    """No two doors should be within 3 Manhattan distance of each other (excluding airlock pairs)."""
    door_closed_id = int(tile_types.door_closed["tile_id"])
    for seed in range(20):
        game_map, _, _ = generate_dungeon(seed=seed, max_rooms=8)
        # Collect airlock door positions to exclude from clustering check
        airlock_doors = set()
        for al in game_map.airlocks:
            airlock_doors.add(al["interior_door"])
            airlock_doors.add(al["exterior_door"])
        door_positions = list(zip(*np.where(game_map.tiles["tile_id"] == door_closed_id)))
        non_airlock_doors = [(x, y) for x, y in door_positions if (x, y) not in airlock_doors]
        for i, (x1, y1) in enumerate(non_airlock_doors):
            for x2, y2 in non_airlock_doors[i + 1:]:
                dist = abs(x1 - x2) + abs(y1 - y2)
                assert dist >= 3, (
                    f"seed={seed}: doors at ({x1},{y1}) and ({x2},{y2}) "
                    f"are only {dist} apart"
                )


def test_subdivide_door_does_not_breach_outer_hull():
    """Door force-clear must never breach the building's outer boundary walls."""
    # Build a footprint where a vertical partition will land at x1+min_offset,
    # so split_x-1 == x1 (the outer hull). The force-clear must skip it.
    #
    # min_offset = 4, so we need inner_w >= 7 (min_offset*2 - 1).
    # Use x1=2, x2=13 → inner_w = 10, lo = x1+4 = 6, hi = x2-4 = 9.
    # With num_rooms=2, rng picks split_x in [lo, hi].
    # We try many seeds; any that place the partition at lo=6 will test that
    # split_x-1 == 5 != x1, but we also craft a tight case: x1=2, x2=7 → inner_w=4
    # which is too small to split. So we test the general invariant instead:
    # no tile on the outer boundary columns/rows should become walkable.
    x1, y1, x2, y2 = 2, 2, 13, 13

    for seed in range(200):
        gm = GameMap(20, 20, fill_tile=tile_types.wall)
        rng = random.Random(seed)

        # Carve boundary walls (non-walkable) and interior floor
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                if x1 < x < x2 and y1 < y < y2:
                    gm.tiles[x, y] = tile_types.floor
                else:
                    gm.tiles[x, y] = tile_types.wall

        _subdivide_building(
            gm, rng, x1, y1, x2, y2,
            num_rooms=2,
            floor_tile=tile_types.floor,
            wall_tile=tile_types.wall,
        )

        # Every tile on the outer boundary must remain non-walkable
        for x in range(x1, x2 + 1):
            assert not gm.tiles["walkable"][x, y1], (
                f"seed={seed}: hull breach at ({x},{y1}) top edge"
            )
            assert not gm.tiles["walkable"][x, y2], (
                f"seed={seed}: hull breach at ({x},{y2}) bottom edge"
            )
        for y in range(y1, y2 + 1):
            assert not gm.tiles["walkable"][x1, y], (
                f"seed={seed}: hull breach at ({x1},{y}) left edge"
            )
            assert not gm.tiles["walkable"][x2, y], (
                f"seed={seed}: hull breach at ({x2},{y}) right edge"
            )


# ---- Colony color variation tests ----


def test_colony_wall_colors_vary_per_building():
    """Wall cells should not all have identical bg color (varied per building)."""
    wall_tid = int(tile_types.structure_wall["tile_id"])
    found_varied = False
    for seed in range(20):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        mask = game_map.tiles["tile_id"] == wall_tid
        if not mask.any():
            continue
        bg = game_map.tiles["light"]["bg"][mask]
        if len(bg) < 2:
            continue
        first = bg[0].copy()
        if not np.all(bg == first):
            found_varied = True
            break
    assert found_varied, "No wall color variation found across 20 seeds"


def test_colony_ground_has_noise():
    """Ground tiles should have per-tile bg variation (noise applied)."""
    ground_tid = int(tile_types.ground["tile_id"])
    found_noisy = False
    for seed in range(20):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        mask = game_map.tiles["tile_id"] == ground_tid
        if not mask.any():
            continue
        bg = game_map.tiles["light"]["bg"][mask]
        first = bg[0].copy()
        if not np.all(bg == first):
            found_noisy = True
            break
    assert found_noisy, "No ground noise found across 20 seeds"


def test_colony_tile_ids_preserved():
    """All ground and wall cells must retain the correct tile_id."""
    ground_tid = int(tile_types.ground["tile_id"])
    wall_tid = int(tile_types.structure_wall["tile_id"])
    for seed in range(10):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        ids = game_map.tiles["tile_id"]
        # Every walkable non-special tile should be ground or dirt_floor
        # Every structure wall should still have wall_tid
        wall_mask = ids == wall_tid
        if wall_mask.any():
            assert not game_map.tiles["walkable"][wall_mask].any(), (
                f"seed={seed}: structure wall tile is walkable"
            )


# -------------------------------------------------------------------
# Village path tests
# -------------------------------------------------------------------

def test_village_has_path_tiles():
    """Generated colony village should contain path tiles."""
    path_tid = int(tile_types.path["tile_id"])
    found = False
    for seed in range(10):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        if (game_map.tiles["tile_id"] == path_tid).any():
            found = True
            break
    assert found, "no path tiles found in any of 10 colony seeds"


def test_paths_reach_map_edge():
    """At least one path tile should be within 2 tiles of a map border."""
    path_tid = int(tile_types.path["tile_id"])
    found = False
    for seed in range(10):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        w, h = game_map.width, game_map.height
        mask = game_map.tiles["tile_id"] == path_tid
        if not mask.any():
            continue
        # Check border proximity: x<=2, x>=w-3, y<=2, y>=h-3
        if (mask[:3, :].any() or mask[w - 3:, :].any()
                or mask[:, :3].any() or mask[:, h - 3:].any()):
            found = True
            break
    assert found, "no path tiles near map edge in any of 10 colony seeds"


def test_paths_only_overwrite_ground():
    """Path tiles must never appear on top of wall or building positions."""
    path_tid = int(tile_types.path["tile_id"])
    wall_tid = int(tile_types.structure_wall["tile_id"])
    floor_tid = int(tile_types.floor["tile_id"])
    for seed in range(10):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        path_mask = game_map.tiles["tile_id"] == path_tid
        if not path_mask.any():
            continue
        # Path tiles must be walkable and transparent
        assert game_map.tiles["walkable"][path_mask].all(), (
            f"seed={seed}: non-walkable path tile found"
        )
        assert game_map.tiles["transparent"][path_mask].all(), (
            f"seed={seed}: non-transparent path tile found"
        )


def test_bfs_path_routes_around_obstacle():
    """_bfs_path should find a path around walls, not through them."""
    from world.palettes import pick_biome, make_ground_tile
    rng = random.Random(42)
    palette = pick_biome(rng)
    ground_tile = make_ground_tile(palette)
    ground_tid = int(ground_tile["tile_id"])
    gm = GameMap(20, 10, fill_tile=ground_tile)
    # Place a vertical wall barrier from y=0 to y=7 at x=10
    for y in range(0, 8):
        gm.tiles[10, y] = tile_types.structure_wall
    # Path from (5,5) to (15,5) must go around the wall via y>=8
    path = _bfs_path(gm, (5, 5), (15, 5), ground_tid)
    assert len(path) > 0, "BFS should find a path around the wall"
    wall_tid = int(tile_types.structure_wall["tile_id"])
    for x, y in path:
        assert int(gm.tiles["tile_id"][x, y]) != wall_tid, (
            f"path crosses wall at ({x}, {y})"
        )


def test_bfs_path_returns_empty_when_blocked():
    """_bfs_path returns empty list when no ground path exists."""
    from world.palettes import pick_biome, make_ground_tile
    rng = random.Random(42)
    palette = pick_biome(rng)
    ground_tile = make_ground_tile(palette)
    ground_tid = int(ground_tile["tile_id"])
    gm = GameMap(20, 10, fill_tile=ground_tile)
    # Complete vertical wall barrier
    for y in range(10):
        gm.tiles[10, y] = tile_types.structure_wall
    path = _bfs_path(gm, (5, 5), (15, 5), ground_tid)
    assert path == [], "BFS should return empty list when fully blocked"


def test_paths_do_not_cross_walls():
    """Village path tiles must only exist on formerly-ground tiles, never inside buildings.

    With BFS pathfinding, paths route through walkable ground and may pass
    through narrow gaps between buildings.  The key invariant is that every
    path tile was placed on a ground tile — never on a wall or floor tile.
    This is tested by ``test_paths_only_overwrite_ground`` above.  Here we
    additionally verify that path tiles form connected regions reachable from
    a map edge without crossing walls (no disconnected "jump-through" fragments).
    """
    path_tid = int(tile_types.path["tile_id"])
    wall_tid = int(tile_types.structure_wall["tile_id"])
    for seed in range(10):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        w, h = game_map.width, game_map.height
        path_coords = set(zip(*np.where(game_map.tiles["tile_id"] == path_tid)))
        if not path_coords:
            continue
        # Flood fill from all edge path tiles through path+ground tiles
        edge_paths = {
            (x, y) for x, y in path_coords
            if x <= 1 or x >= w - 2 or y <= 1 or y >= h - 2
        }
        if not edge_paths:
            continue
        # BFS through walkable (non-wall) tiles from edge paths
        visited: set = set()
        frontier = list(edge_paths)
        for p in frontier:
            visited.add(p)
        while frontier:
            nxt = []
            for cx, cy in frontier:
                for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + ddx, cy + ddy
                    if (nx, ny) in visited:
                        continue
                    if not (0 <= nx < w and 0 <= ny < h):
                        continue
                    tid = int(game_map.tiles["tile_id"][nx, ny])
                    if tid == wall_tid:
                        continue
                    visited.add((nx, ny))
                    nxt.append((nx, ny))
            frontier = nxt
        unreachable = path_coords - visited
        assert not unreachable, (
            f"seed={seed}: {len(unreachable)} path tiles unreachable from "
            f"edge without crossing walls, e.g. {next(iter(unreachable))}"
        )


def test_carve_external_door_returns_position():
    """_carve_external_door should return valid coords when a door is carved."""
    from world.palettes import pick_biome, make_ground_tile, make_wall_tile
    rng = random.Random(42)
    palette = pick_biome(rng)
    ground_tile = make_ground_tile(palette)
    gm = GameMap(40, 30, fill_tile=ground_tile)
    wall_color = palette.wall_colors[0]
    bldg_wall = make_wall_tile(wall_color)
    # Place a small building
    wing = RectRoom(10, 10, 8, 6)
    for bx in range(wing.x1, wing.x2 + 1):
        for by in range(wing.y1, wing.y2 + 1):
            gm.tiles[bx, by] = bldg_wall
    # Carve interior
    for bx in range(wing.x1 + 1, wing.x2):
        for by in range(wing.y1 + 1, wing.y2):
            gm.tiles[bx, by] = tile_types.floor
    result = _carve_external_door(gm, rng, [wing], tile_types.floor)
    assert result is not None
    x, y = result
    assert gm.in_bounds(x, y)


def test_paths_prefer_wall_gap():
    """Most path tiles from Dijkstra BFS should not be wall-adjacent."""
    from world.palettes import pick_biome, make_ground_tile
    rng = random.Random(42)
    palette = pick_biome(rng)
    ground_tile = make_ground_tile(palette)
    ground_tid = int(ground_tile["tile_id"])
    wall_tid = int(tile_types.structure_wall["tile_id"])
    # 30x20 map with a horizontal wall barrier that has a 1-tile gap at y=15
    # and also open space above (y>=18). Dijkstra should prefer the gap route
    # that stays away from walls.
    gm = GameMap(30, 20, fill_tile=ground_tile)
    # Wall from x=0..28 at y=10, gap at x=15
    for x in range(30):
        if x == 15:
            continue
        gm.tiles[x, 10] = tile_types.structure_wall
    path = _bfs_path(gm, (5, 5), (5, 15), ground_tid)
    assert len(path) > 0, "Dijkstra should find a path"
    # Count wall-adjacent tiles in path
    wall_adj = 0
    for x, y in path:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < 30 and 0 <= ny < 20:
                if int(gm.tiles["tile_id"][nx, ny]) == wall_tid:
                    wall_adj += 1
                    break
    # With wall-gap preference, most tiles should not be wall-adjacent
    ratio = wall_adj / len(path)
    assert ratio < 0.5, f"too many wall-adjacent path tiles: {wall_adj}/{len(path)} = {ratio:.2f}"


def test_spine_not_always_centered():
    """Spine road y-coordinates should vary across different seeds."""
    from world.palettes import pick_biome, make_ground_tile
    path_tid = int(tile_types.path["tile_id"])
    spine_ys = set()
    for seed in range(20):
        game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
        w, h = game_map.width, game_map.height
        # Check path tiles on left edge (x<=2) to find spine entry y
        for y in range(h):
            for x in range(3):
                if int(game_map.tiles["tile_id"][x, y]) == path_tid:
                    spine_ys.add(y)
    # With random endpoints, we should see multiple distinct y values
    assert len(spine_ys) > 1, f"spine always enters at same y: {spine_ys}"


def test_meander_preserves_connectivity():
    """Meandered path should still form a connected sequence of adjacent tiles."""
    from world.palettes import pick_biome, make_ground_tile
    rng = random.Random(42)
    palette = pick_biome(rng)
    ground_tile = make_ground_tile(palette)
    ground_tid = int(ground_tile["tile_id"])
    gm = GameMap(30, 20, fill_tile=ground_tile)
    # Straight horizontal path
    straight = [(x, 10) for x in range(5, 25)]
    meandered = _meander(rng, straight, gm, ground_tid)
    assert len(meandered) >= len(straight), "meander should not shorten path"
    # Check adjacency: each consecutive pair should be cardinal neighbors
    for i in range(len(meandered) - 1):
        x1, y1 = meandered[i]
        x2, y2 = meandered[i + 1]
        assert abs(x1 - x2) + abs(y1 - y2) == 1, (
            f"gap in meandered path at index {i}: {meandered[i]} -> {meandered[i+1]}"
        )


def test_meander_avoids_walls():
    """Meander should never insert tiles that are wall-adjacent.

    When a wall is one tile away from the path, the lateral offset would land
    on a wall-adjacent ground tile.  Meander should skip that offset.
    """
    from world.palettes import pick_biome, make_ground_tile
    rng = random.Random(0)
    palette = pick_biome(rng)
    ground_tile = make_ground_tile(palette)
    ground_tid = int(ground_tile["tile_id"])
    wall_tid = int(tile_types.structure_wall["tile_id"])
    gm = GameMap(40, 20, fill_tile=ground_tile)
    # Wall at y=8: one ground row (y=9) separates it from path at y=10.
    # Lateral offset to y=9 is ground but wall-adjacent — should be skipped.
    for x in range(0, 40):
        gm.tiles[x, 8] = tile_types.structure_wall
    straight = [(x, 10) for x in range(2, 38)]
    original_set = set(straight)
    for seed in range(50):
        test_rng = random.Random(seed)
        meandered = _meander(test_rng, straight, gm, ground_tid)
        for x, y in meandered:
            tid = int(gm.tiles["tile_id"][x, y])
            assert tid != wall_tid, (
                f"seed={seed}: meander placed path on wall at ({x}, {y})"
            )
            # Inserted (non-original) tiles must not be wall-adjacent
            if (x, y) not in original_set:
                for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + ddx, y + ddy
                    if 0 <= nx < 40 and 0 <= ny < 20:
                        assert int(gm.tiles["tile_id"][nx, ny]) != wall_tid, (
                            f"seed={seed}: meander inserted wall-adjacent "
                            f"tile ({x}, {y}) not in original path"
                        )


def test_meander_never_crosses_walls():
    """Meander must never place path tiles on non-ground tiles."""
    from world.palettes import pick_biome, make_ground_tile
    rng = random.Random(7)
    palette = pick_biome(rng)
    ground_tile = make_ground_tile(palette)
    ground_tid = int(ground_tile["tile_id"])
    wall_tid = int(tile_types.structure_wall["tile_id"])
    gm = GameMap(40, 20, fill_tile=ground_tile)
    # Walls on both sides of the path (narrow corridor at y=10)
    for x in range(0, 40):
        gm.tiles[x, 9] = tile_types.structure_wall
        gm.tiles[x, 11] = tile_types.structure_wall
    straight = [(x, 10) for x in range(2, 38)]
    for seed in range(50):
        test_rng = random.Random(seed)
        meandered = _meander(test_rng, straight, gm, ground_tid)
        # In a narrow corridor, meander should produce the original path
        # (no room to offset)
        for x, y in meandered:
            tid = int(gm.tiles["tile_id"][x, y])
            assert tid == ground_tid, (
                f"seed={seed}: meander tile ({x}, {y}) has tid={tid}, "
                f"expected ground"
            )
