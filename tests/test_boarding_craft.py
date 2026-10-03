"""Tests for the composite-ship builder (compose_ships + airlock-pair search)."""

from __future__ import annotations

import random

from world import tile_types
from world.boarding_craft import (
    GAP_BETWEEN_SHIPS,
    compose_ships,
    find_compatible_airlock_pair,
)
from world.boarding_ship import generate_pirate_ship
from world.dungeon_gen import generate_player_ship

# ---- Pirate ship generator ----


def test_generate_pirate_ship_returns_full_layout():
    gm, rooms, exit_pos = generate_pirate_ship(seed=99)
    assert gm.width >= 60 and gm.height >= 30
    assert len(rooms) >= 2, "pirate ship should be a real multi-room layout"
    assert exit_pos is not None
    assert gm.airlocks, "pirate ship must have at least one airlock"


def test_generate_pirate_ship_deterministic():
    gm1, rooms1, ep1 = generate_pirate_ship(seed=1234)
    gm2, rooms2, ep2 = generate_pirate_ship(seed=1234)
    assert ep1 == ep2
    assert len(rooms1) == len(rooms2)


# ---- find_compatible_airlock_pair ----


def test_find_pair_returns_none_when_no_facing_airlocks():
    """Hand-rolled layouts where both airlocks point the same way."""
    player_alocks = [{"interior_door": (10, 10), "exterior_door": (12, 10), "direction": (1, 0)}]
    pirate_alocks = [{"interior_door": (5, 5), "exterior_door": (7, 5), "direction": (1, 0)}]
    rng = random.Random(0)
    pair = find_compatible_airlock_pair(player_alocks, pirate_alocks, player_exit_pos=None, rng=rng)
    assert pair is None


def test_find_pair_finds_facing_airlocks():
    player_alocks = [{"interior_door": (10, 10), "exterior_door": (12, 10), "direction": (1, 0)}]
    pirate_alocks = [{"interior_door": (5, 5), "exterior_door": (3, 5), "direction": (-1, 0)}]
    rng = random.Random(0)
    pair = find_compatible_airlock_pair(player_alocks, pirate_alocks, player_exit_pos=None, rng=rng)
    assert pair == (player_alocks[0], pirate_alocks[0])


def test_find_pair_excludes_docking_hatch():
    """Player's docking-hatch airlock must not be picked for boarding."""
    docking = {"interior_door": (10, 10), "exterior_door": (12, 10), "direction": (1, 0)}
    pirate_alocks = [{"interior_door": (5, 5), "exterior_door": (3, 5), "direction": (-1, 0)}]
    rng = random.Random(0)
    pair = find_compatible_airlock_pair([docking], pirate_alocks, player_exit_pos=docking["interior_door"], rng=rng)
    assert pair is None


# ---- compose_ships ----


def _real_ship_pair_that_composes(player_seed: int):
    """Try seeds until we get a (player, pirate) pair that yields a non-None layout."""
    pgm, prooms, pexit = generate_player_ship(seed=player_seed)
    for s in range(200):
        rgm, rrooms, _ = generate_pirate_ship(seed=s)
        pair = find_compatible_airlock_pair(pgm.airlocks, rgm.airlocks, player_exit_pos=pexit, rng=random.Random(0))
        if pair is None:
            continue
        layout = compose_ships(pgm, rgm, rrooms, pair[0], pair[1])
        if layout is None:
            continue
        return pgm, prooms, pexit, rgm, rrooms, pair, layout
    raise RuntimeError("could not find a composable seed")


def test_compose_creates_composite_with_both_ships():
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    assert layout.composite_map.width >= max(pgm.width + layout.player_offset[0], rgm.width + layout.pirate_offset[0])

    # Both ship interiors are present (at least one room from each has walkable interior tiles)
    def _any_room_walkable(rooms, offset, gm):
        for room in rooms:
            for x in range(room.x1 + 1, room.x2):
                for y in range(room.y1 + 1, room.y2):
                    if gm.is_walkable(x + offset[0], y + offset[1]):
                        return True
        return False

    assert _any_room_walkable(prooms, layout.player_offset, layout.composite_map)
    assert _any_room_walkable(rrooms, layout.pirate_offset, layout.composite_map)


def test_compose_corridor_is_walkable_and_airtight():
    """Every corridor tile is walkable AND every adjacent non-corridor cell is
    either a wall or a (pre-existing) ship tile - never raw vacuum."""
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    cm = layout.composite_map
    space_tid = int(tile_types.space["tile_id"])
    path_set = set(layout.corridor_tiles)
    for x, y in layout.corridor_tiles:
        assert cm.is_walkable(x, y), f"corridor tile {(x, y)} not walkable"
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in path_set:
                continue
            if not cm.in_bounds(nx, ny):
                continue
            tid = int(cm.tiles["tile_id"][nx, ny])
            # Adjacent tile must NOT be raw space - that would mean a vacuum leak.
            assert tid != space_tid, f"corridor tile {(x, y)} leaks vacuum at {(nx, ny)}"


def test_compose_corridor_does_not_cross_hull_or_glass():
    """Every corridor tile must have started as space (BFS guarantees it).
    Re-derive: walk path, every tile's pre-corridor tile_id was space."""
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    space_tid = int(tile_types.space["tile_id"])
    for x, y in layout.corridor_tiles:
        # Source tile in the COMPOSITE before corridor carving was either:
        # - in player canvas: player_map.tiles[x - player_offset[0], y - player_offset[1]]
        # - in pirate canvas: pirate_map.tiles[x - pirate_offset[0], y - pirate_offset[1]]
        # - in pure gap: composite was initialized to space
        pox, poy = layout.player_offset
        rox, roy = layout.pirate_offset
        in_player = 0 <= x - pox < pgm.width and 0 <= y - poy < pgm.height
        in_pirate = 0 <= x - rox < rgm.width and 0 <= y - roy < rgm.height
        if in_player:
            tid = int(pgm.tiles["tile_id"][x - pox, y - poy])
            assert tid == space_tid, f"corridor at {(x, y)} crossed player tile_id {tid}"
        elif in_pirate:
            tid = int(rgm.tiles["tile_id"][x - rox, y - roy])
            assert tid == space_tid, f"corridor at {(x, y)} crossed pirate tile_id {tid}"


def test_compose_corridor_at_least_gap_long():
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    assert len(layout.corridor_tiles) >= GAP_BETWEEN_SHIPS


def test_compose_path_walkable_from_player_to_pirate_airlock():
    """The corridor path connects the two airlocks - every tile walkable."""
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    cm = layout.composite_map
    assert cm.is_walkable(*layout.player_airlock_pos)
    assert cm.is_walkable(*layout.pirate_airlock_pos)
    for x, y in layout.corridor_tiles:
        assert cm.is_walkable(x, y)


def test_compose_spawn_room_is_inside_pirate_ship():
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    spawn = layout.spawn_room
    walkable_count = sum(
        1
        for x in range(spawn.x1 + 1, spawn.x2)
        for y in range(spawn.y1 + 1, spawn.y2)
        if layout.composite_map.is_walkable(x, y)
    )
    assert walkable_count > 0


def test_compose_does_not_trample_player_ship_with_pirate_vacuum():
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    cm = layout.composite_map
    pox, poy = layout.player_offset
    for x in range(pgm.width):
        for y in range(pgm.height):
            if pgm.is_walkable(x, y):
                assert cm.is_walkable(pox + x, poy + y), (
                    f"player tile ({x},{y}) trampled at composite ({pox + x},{poy + y})"
                )


def test_compose_does_not_trample_pirate_ship():
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    cm = layout.composite_map
    rox, roy = layout.pirate_offset
    for x in range(rgm.width):
        for y in range(rgm.height):
            if rgm.is_walkable(x, y):
                assert cm.is_walkable(rox + x, roy + y), (
                    f"pirate tile ({x},{y}) trampled at composite ({rox + x},{roy + y})"
                )


def test_compose_merges_pirate_entities_into_composite():
    """Pirate ship's interactables (lockers, terminals, etc.) must appear on
    the composite map at translated coords so the player can interact with them."""
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    rox, roy = layout.pirate_offset
    # Every pirate-side entity should be in composite.entities at translated coords.
    for ref in layout.pirate_entities_overlay:
        assert ref in layout.composite_map.entities


def test_compose_merges_non_connecting_airlocks_into_composite():
    """Composite has both ships' airlocks (translated), EXCEPT the two connecting
    ones used for the corridor. The connecting airlocks are fused permanently
    open - leaving their switches active would let the player flip one and
    open it as a vacuum source flooding both ships through the corridor."""
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    cm = layout.composite_map
    p_airlock, r_airlock = pair
    # Composite has (player_airlocks - 1) + (pirate_airlocks - 1) airlocks.
    expected = (len(pgm.airlocks) - 1) + (len(rgm.airlocks) - 1)
    assert len(cm.airlocks) == expected
    # Switch positions reference composite coords (offset + native).
    pox, poy = layout.player_offset
    rox, roy = layout.pirate_offset
    # Neither connecting airlock's switch should be in the composite list.
    p_conn_switch = p_airlock.get("switch")
    r_conn_switch = r_airlock.get("switch")
    for comp in cm.airlocks:
        sw = comp.get("switch")
        if sw is None:
            continue
        if p_conn_switch is not None:
            assert sw != (p_conn_switch[0] + pox, p_conn_switch[1] + poy), (
                "player connecting-airlock switch leaked into composite.airlocks"
            )
        if r_conn_switch is not None:
            assert sw != (r_conn_switch[0] + rox, r_conn_switch[1] + roy), (
                "pirate connecting-airlock switch leaked into composite.airlocks"
            )


def test_flipping_connecting_airlock_switch_is_a_no_op():
    """The corridor-connecting airlock's switch must NOT open it as a vacuum
    source. Either the switch isn't registered (composite.airlocks excludes
    the pair) so ToggleSwitchAction reports 'not connected', or it does
    nothing functional. Either way: no airlock_ext_open is created."""
    from types import SimpleNamespace

    from game.actions import ToggleSwitchAction
    from game.entity import Entity, Fighter

    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    cm = layout.composite_map
    p_airlock, _r_airlock = pair
    if p_airlock.get("switch") is None:
        return  # this player ship's connecting airlock had no switch
    # Composite-coord position of the connecting switch
    pox, poy = layout.player_offset
    sx, sy = p_airlock["switch"][0] + pox, p_airlock["switch"][1] + poy
    # Place a player adjacent to the switch
    px, py = sx - 1, sy
    player = Entity(x=px, y=py, char="@", color=(255, 255, 255), name="P", fighter=Fighter(10, 10, 0, 1))
    cm.entities.append(player)

    class FakeLog:
        def __init__(self):
            self.msgs = []

        def add_message(self, msg, color=None):
            self.msgs.append(msg)

    engine = SimpleNamespace(game_map=cm, player=player, message_log=FakeLog())
    pre_open_count = int((cm.tiles["tile_id"] == int(tile_types.airlock_ext_open["tile_id"])).sum())
    ToggleSwitchAction(dx=1, dy=0).perform(engine, player)
    post_open_count = int((cm.tiles["tile_id"] == int(tile_types.airlock_ext_open["tile_id"])).sum())
    assert post_open_count == pre_open_count, (
        "flipping connecting-airlock switch must NOT create airlock_ext_open (vacuum source)"
    )


def test_composite_has_no_vacuum_sources_in_corridor():
    """The corridor must NOT introduce vacuum sources - the player ship is
    pressurized and any open airlock_ext_open would flood-fill vacuum
    through the corridor into both ship interiors."""
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    cm = layout.composite_map
    cm.recalculate_hazards()
    vacuum = cm.hazard_overlays.get("vacuum")
    if vacuum is not None:
        # No corridor tile may be vacuum.
        for x, y in layout.corridor_tiles:
            assert not vacuum[x, y], f"corridor tile {(x, y)} is vacuum (would flood ship interior)"
        # No interior pirate-room tile may be vacuum.
        spawn = layout.spawn_room
        for x in range(spawn.x1 + 1, spawn.x2):
            for y in range(spawn.y1 + 1, spawn.y2):
                if cm.is_walkable(x, y):
                    assert not vacuum[x, y], f"pirate room tile {(x, y)} is vacuum"


def test_ship_hulls_are_disjoint():
    """Canvases may overlap (we collapse empty exteriors), but the actual hull
    tiles of the two ships must occupy disjoint composite regions."""
    pgm, prooms, pexit, rgm, rrooms, pair, layout = _real_ship_pair_that_composes(42)
    space_tid = int(tile_types.space["tile_id"])
    cm = layout.composite_map
    pox, poy = layout.player_offset
    # Build the set of composite coords occupied by player non-space tiles.
    player_cells: set[tuple[int, int]] = set()
    for x in range(pgm.width):
        for y in range(pgm.height):
            if int(pgm.tiles["tile_id"][x, y]) != space_tid:
                player_cells.add((pox + x, poy + y))
    # And by pirate non-space tiles.
    rox, roy = layout.pirate_offset
    for x in range(rgm.width):
        for y in range(rgm.height):
            if int(rgm.tiles["tile_id"][x, y]) != space_tid:
                cell = (rox + x, roy + y)
                assert cell not in player_cells, f"pirate hull collides with player hull at {cell}"
    # Sanity: composite has the same size as max bounds.
    assert cm.width > 0 and cm.height > 0
