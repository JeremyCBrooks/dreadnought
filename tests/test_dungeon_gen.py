"""Tests for dungeon generation."""
from world.dungeon_gen import (
    generate_dungeon, RectRoom, _room_wall_positions,
    _build_ship_skeleton, _ROOM_DRESSING,
)
from world.game_map import GameMap
from world import tile_types
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
