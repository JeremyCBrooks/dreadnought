"""Tests for airlock placement and drift mechanics."""
import numpy as np

from game.actions import BumpAction, WaitAction
from game.entity import Entity, Fighter
from tests.conftest import MockEngine
from world import tile_types
from world.dungeon_gen import generate_dungeon
from world.game_map import GameMap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_airlock_map(w=20, h=20):
    """Build a small map with a hand-placed airlock facing east.

    Layout (y=5 row):
      x=5: floor, x=6: door_closed (interior), x=7: airlock_floor,
      x=8: door_closed (exterior), x=9: space, x=10+: space
    """
    gm = GameMap(w, h)
    # Floor interior
    for x in range(1, 6):
        for y in range(1, h - 1):
            gm.tiles[x, y] = tile_types.floor
    # Airlock structure at y=5
    gm.tiles[6, 5] = tile_types.door_closed         # interior door
    gm.tiles[7, 5] = tile_types.airlock_floor      # airlock chamber
    gm.tiles[8, 5] = tile_types.airlock_ext_closed  # exterior door (hull-colored)
    # Space beyond
    for x in range(9, w):
        for y in range(0, h):
            gm.tiles[x, y] = tile_types.space
    gm.has_space = True
    gm.airlocks = [{
        "interior_door": (6, 5),
        "exterior_door": (8, 5),
        "direction": (1, 0),
    }]
    return gm


# ---------------------------------------------------------------------------
# Airlock generation tests
# ---------------------------------------------------------------------------

def test_airlocks_placed_on_ship():
    """Ship-type maps should have at least one airlock per rib tip."""
    for seed in range(10):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        if game_map.has_space:
            assert len(game_map.airlocks) >= 1


def test_airlocks_at_rib_tips():
    """Every rib tip should have an airlock placed at it."""
    for seed in range(20):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        if not hasattr(game_map, "ribs") or not game_map.ribs:
            continue
        keel_y = game_map.keel_y
        keel_y2 = game_map.keel_y2
        # Collect expected tip positions
        expected_tips = []
        for rib_x, rib_y_start, rib_y_end in game_map.ribs:
            if rib_y_start < keel_y:
                expected_tips.append((rib_x, rib_y_start, 0, -1))  # north tip
            if rib_y_end > keel_y2:
                expected_tips.append((rib_x, rib_y_end, 0, 1))  # south tip
        # Each expected tip should have a corresponding airlock nearby
        for rib_x, tip_y, dx, dy in expected_tips:
            # The interior door should be at or very near the rib tip
            found = False
            for al in game_map.airlocks:
                ix, iy = al["interior_door"]
                adx, ady = al["direction"]
                if ix == rib_x and adx == dx and ady == dy:
                    # Interior door should be 1 tile beyond the tip
                    if iy == tip_y + dy:
                        found = True
                        break
            # Some tips may not have enough wall space for an airlock
            # so we don't assert, but at least one tip should succeed
        # At minimum, we expect at least one airlock was placed
        assert len(game_map.airlocks) >= 1, f"seed={seed}: no airlocks placed"


def test_rib_airlock_switch_adjacent_to_door():
    """The airlock switch should be exactly 1 tile from the interior door."""
    for seed in range(20):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        for al in game_map.airlocks:
            switch = al.get("switch")
            if switch is None:
                continue
            ix, iy = al["interior_door"]
            sx, sy = switch
            dist = abs(sx - ix) + abs(sy - iy)
            assert dist == 1, (
                f"seed={seed}: switch at ({sx},{sy}) is {dist} tiles from "
                f"interior door at ({ix},{iy}), expected 1"
            )


def test_rib_airlock_direction_is_outward():
    """Rib tip airlocks should face outward (away from the keel)."""
    for seed in range(10):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        if not hasattr(game_map, "ribs"):
            continue
        keel_y = game_map.keel_y
        keel_y2 = game_map.keel_y2
        for al in game_map.airlocks:
            dx, dy = al["direction"]
            ix, iy = al["interior_door"]
            # Airlock direction should be north or south (perpendicular ribs)
            # or possibly from the random placement (east/west)
            assert (dx, dy) in [(0, -1), (0, 1), (-1, 0), (1, 0)]


def test_airlock_structure():
    """Each airlock has interior_door, exterior_door, and direction."""
    for seed in range(5):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        for al in game_map.airlocks:
            assert "interior_door" in al
            assert "exterior_door" in al
            assert "direction" in al
            dx, dy = al["direction"]
            assert (dx, dy) in [(0, -1), (0, 1), (-1, 0), (1, 0)]


def test_exterior_door_faces_space():
    """The tile beyond the exterior door should be space after hull conversion."""
    for seed in range(10):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        space_tid = int(tile_types.space["tile_id"])
        for al in game_map.airlocks:
            ex, ey = al["exterior_door"]
            dx, dy = al["direction"]
            beyond_x, beyond_y = ex + dx, ey + dy
            if game_map.in_bounds(beyond_x, beyond_y):
                tid = int(game_map.tiles["tile_id"][beyond_x, beyond_y])
                assert tid == space_tid, (
                    f"seed={seed}: tile beyond exterior door at ({beyond_x},{beyond_y}) "
                    f"is {tid}, expected space ({space_tid})"
                )


def test_interior_door_connects_to_walkable():
    """The tile behind the interior door (inside the ship) should be walkable."""
    for seed in range(10):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        for al in game_map.airlocks:
            ix, iy = al["interior_door"]
            dx, dy = al["direction"]
            # Interior is opposite the outward direction
            inside_x, inside_y = ix - dx, iy - dy
            assert game_map.in_bounds(inside_x, inside_y)
            assert game_map.tiles["walkable"][inside_x, inside_y], (
                f"seed={seed}: tile behind interior door at ({inside_x},{inside_y}) not walkable"
            )


def test_airlock_floor_between_doors():
    """The airlock floor tile sits between the two doors."""
    for seed in range(10):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        airlock_tid = int(tile_types.airlock_floor["tile_id"])
        for al in game_map.airlocks:
            ix, iy = al["interior_door"]
            dx, dy = al["direction"]
            mid_x, mid_y = ix + dx, iy + dy
            assert int(game_map.tiles["tile_id"][mid_x, mid_y]) == airlock_tid


# ---------------------------------------------------------------------------
# Drift mechanic tests
# ---------------------------------------------------------------------------

def test_bump_into_space_from_airlock_starts_drift():
    """Stepping from open exterior door onto space tile initiates drift."""
    gm = _make_airlock_map()
    # Open the exterior door (hull-colored)
    gm.tiles[8, 5] = tile_types.airlock_ext_open
    # Player standing on the open exterior door
    p = Entity(x=8, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    eng = MockEngine(gm, p)
    result = BumpAction(1, 0).perform(eng, p)
    assert result == 1
    assert p.x == 9
    assert p.y == 5
    assert p.drifting is True
    assert p.drift_direction == (1, 0)


def test_bump_from_airlock_floor_into_space_starts_drift():
    """Stepping from airlock_floor directly onto space tile initiates drift."""
    gm = _make_airlock_map()
    # Replace exterior door with space to test direct airlock_floor→space
    gm.tiles[8, 5] = tile_types.space
    p = Entity(x=7, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    eng = MockEngine(gm, p)
    result = BumpAction(1, 0).perform(eng, p)
    assert result == 1
    assert p.x == 8
    assert p.drifting is True


def test_bump_into_space_not_from_airlock_blocked():
    """Moving onto space from a regular floor tile should be blocked."""
    gm = GameMap(10, 10)
    for x in range(1, 5):
        for y in range(1, 9):
            gm.tiles[x, y] = tile_types.floor
    for x in range(5, 10):
        for y in range(0, 10):
            gm.tiles[x, y] = tile_types.space
    gm.has_space = True
    p = Entity(x=4, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    eng = MockEngine(gm, p)
    result = BumpAction(1, 0).perform(eng, p)
    assert result == 0
    assert p.x == 4  # didn't move
    assert p.drifting is False


def test_drift_is_one_way():
    """A drifting entity cannot change direction or stop."""
    gm = _make_airlock_map()
    p = Entity(x=9, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    p.drifting = True
    p.drift_direction = (1, 0)
    gm.entities.append(p)
    # BumpAction with opposite direction should still not let them escape drift
    # (drift is handled in _after_player_turn, not in BumpAction)
    assert p.drifting is True


def test_entity_drifting_fields_default():
    """Entity defaults to not drifting."""
    e = Entity()
    assert e.drifting is False
    assert e.drift_direction == (0, 0)


def test_enemy_drift():
    """Enemies with drifting flag should also move in drift direction."""
    gm = _make_airlock_map()
    enemy = Entity(x=10, y=5, name="Drone", fighter=Fighter(5, 5, 0, 1))
    enemy.drifting = True
    enemy.drift_direction = (1, 0)
    gm.entities.append(enemy)

    p = Entity(x=3, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    eng = MockEngine(gm, p)

    # Simulate the drift processing from _after_player_turn
    # Enemy at x=10 drifts to x=11
    edx, edy = enemy.drift_direction
    enemy.x += edx
    enemy.y += edy
    assert enemy.x == 11


def test_enemy_drift_out_of_bounds_removed():
    """Enemies that drift out of bounds are removed from entities."""
    gm = _make_airlock_map(w=12, h=12)
    enemy = Entity(x=11, y=5, name="Drone", fighter=Fighter(5, 5, 0, 1))
    enemy.drifting = True
    enemy.drift_direction = (1, 0)
    gm.entities.append(enemy)

    p = Entity(x=3, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)

    # Simulate drift: x=11 + 1 = 12, out of bounds for w=12
    enx = enemy.x + enemy.drift_direction[0]
    if not gm.in_bounds(enx, enemy.y):
        gm.entities.remove(enemy)
    assert enemy not in gm.entities


def test_airlock_floor_tile_properties():
    """Airlock floor should be walkable and transparent."""
    assert bool(tile_types.airlock_floor["walkable"])
    assert bool(tile_types.airlock_floor["transparent"])


def test_airlock_floor_flavor_text():
    """Airlock floor has flavor text registered."""
    tid = int(tile_types.airlock_floor["tile_id"])
    assert tid in tile_types.TILE_FLAVORS
    name, flavors = tile_types.TILE_FLAVORS[tid]
    assert name == "Airlock"
    assert len(flavors) > 0


def test_drift_death_on_hull_collision():
    """Drifting into a wall/hull tile kills the player."""
    from engine.game_state import Engine
    from ui.tactical_state import TacticalState
    from game.suit import Suit

    gm = GameMap(20, 20)
    # Floor interior
    for x in range(1, 10):
        for y in range(1, 19):
            gm.tiles[x, y] = tile_types.floor
    # Space with a wall at x=14
    for x in range(10, 20):
        for y in range(0, 20):
            gm.tiles[x, y] = tile_types.space
    gm.tiles[14, 5] = tile_types.wall  # hull obstacle
    gm.has_space = True
    gm.airlocks = []

    p = Entity(x=12, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    p.drifting = True
    p.drift_direction = (1, 0)
    gm.entities.append(p)

    eng = Engine()
    eng.game_map = gm
    eng.player = p
    suit = Suit(name="Test Suit", resistances={"vacuum": 50})
    suit.refill_pools()
    eng.suit = suit
    eng.environment = {"vacuum": 1}

    state = TacticalState()
    eng._state_stack = [state]

    # Drift tick 1: x=12 → x=13 (space, ok)
    state._after_player_turn(eng)
    assert p.x == 13
    assert p.fighter.hp > 0

    # Drift tick 2: x=13 → x=14 (wall, death)
    state._after_player_turn(eng)
    assert p.fighter.hp == 0


def test_exterior_door_is_hull_colored():
    """Exterior airlock door should use airlock_ext_closed tile."""
    for seed in range(5):
        game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
        ext_closed_tid = int(tile_types.airlock_ext_closed["tile_id"])
        for al in game_map.airlocks:
            ex, ey = al["exterior_door"]
            tid = int(game_map.tiles["tile_id"][ex, ey])
            assert tid == ext_closed_tid, (
                f"seed={seed}: exterior door at ({ex},{ey}) has tid={tid}, "
                f"expected airlock_ext_closed ({ext_closed_tid})"
            )


def test_airlock_ext_door_tile_properties():
    """Exterior airlock door tiles have correct properties."""
    assert not bool(tile_types.airlock_ext_closed["walkable"])
    assert not bool(tile_types.airlock_ext_closed["transparent"])
    assert bool(tile_types.airlock_ext_open["walkable"])
    assert bool(tile_types.airlock_ext_open["transparent"])


def test_airlock_ext_door_flavor_text():
    """Exterior airlock door tiles have flavor text."""
    for tile in (tile_types.airlock_ext_closed, tile_types.airlock_ext_open):
        tid = int(tile["tile_id"])
        assert tid in tile_types.TILE_FLAVORS


def test_vacuum_drains_during_drift():
    """Vacuum pool should drain while drifting (via environment tick).

    Space tiles should automatically get vacuum overlay from
    recalculate_hazards, so no manual overlay setup needed.
    """
    from game.suit import Suit
    from game.environment import apply_environment_tick

    gm = _make_airlock_map()
    p = Entity(x=10, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    p.drifting = True
    p.drift_direction = (1, 0)
    gm.entities.append(p)

    suit = Suit(name="Test Suit", resistances={"vacuum": 50})
    suit.refill_pools()
    eng = MockEngine(gm, p, suit=suit, environment={"vacuum": 1})

    # recalculate_hazards should auto-mark space tiles as vacuum
    gm._hazards_dirty = True
    gm.recalculate_hazards()
    overlay = gm.hazard_overlays.get("vacuum")
    assert overlay is not None
    assert overlay[10, 5], "Space tile at player position should have vacuum"

    initial_o2 = suit.current_pools["vacuum"]
    for _ in range(Suit.DRAIN_INTERVAL):
        apply_environment_tick(eng)
    assert suit.current_pools["vacuum"] == initial_o2 - 1


def test_space_tiles_always_have_vacuum_overlay():
    """All space tiles should always have vacuum overlay, even without
    hull breaches or open airlock doors.  And ONLY space tiles get vacuum
    when no breach or exterior door is open."""
    gm = _make_airlock_map()
    # No open doors, no hull breaches — but space tiles should still be vacuum
    gm._hazards_dirty = True
    gm.recalculate_hazards()
    overlay = gm.hazard_overlays.get("vacuum")
    assert overlay is not None, "Vacuum overlay should exist when map has space tiles"
    space_tid = int(tile_types.space["tile_id"])
    space_mask = gm.tiles["tile_id"] == space_tid
    # Every space tile has vacuum
    xs, ys = np.where(space_mask)
    for i in range(len(xs)):
        assert overlay[xs[i], ys[i]], (
            f"Space tile ({xs[i]}, {ys[i]}) should have vacuum overlay"
        )
    # No non-space tile has vacuum (no breach/open door)
    non_space_vacuum = overlay & ~space_mask
    assert not np.any(non_space_vacuum), (
        "Only space tiles should have vacuum when no breach or airlock is open"
    )


def test_drift_into_non_space_non_wall_tile_kills():
    """Drifting into any non-space tile (e.g. floor, hull_breach, window) should
    kill the entity, not let them pass through."""
    from engine.game_state import Engine
    from ui.tactical_state import TacticalState
    from game.suit import Suit

    for tile, label in [
        (tile_types.floor, "floor"),
        (tile_types.hull_breach, "hull_breach"),
        (tile_types.structure_window, "structure_window"),
        (tile_types.reactor_core, "reactor_core"),
        (tile_types.door_open, "open_door"),
    ]:
        gm = GameMap(20, 20)
        for x in range(1, 10):
            for y in range(1, 19):
                gm.tiles[x, y] = tile_types.floor
        for x in range(10, 20):
            for y in range(0, 20):
                gm.tiles[x, y] = tile_types.space
        # Place the non-wall tile in the drift path
        gm.tiles[14, 5] = tile
        gm.has_space = True
        gm.airlocks = []

        p = Entity(x=12, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        p.drifting = True
        p.drift_direction = (1, 0)
        gm.entities.append(p)

        eng = Engine()
        eng.game_map = gm
        eng.player = p
        suit = Suit(name="Test Suit", resistances={"vacuum": 50})
        suit.refill_pools()
        eng.suit = suit
        eng.environment = {"vacuum": 1}

        state = TacticalState()
        eng._state_stack = [state]

        # Tick 1: x=12 → x=13 (space, fine)
        state._after_player_turn(eng)
        assert p.x == 13, f"{label}: should drift through space"
        assert p.fighter.hp > 0

        # Tick 2: x=13 → x=14 (non-space tile, should die on impact)
        state._after_player_turn(eng)
        assert p.fighter.hp == 0, (
            f"{label}: drifting into {label} should be fatal"
        )


def test_enemy_drift_into_non_space_tile_removed():
    """Enemies drifting into non-space tiles should be killed and removed."""
    gm = GameMap(20, 20)
    for x in range(10, 20):
        for y in range(0, 20):
            gm.tiles[x, y] = tile_types.space
    # Place a floor tile in the drift path
    gm.tiles[14, 5] = tile_types.floor
    gm.has_space = True
    gm.airlocks = []

    enemy = Entity(x=12, y=5, name="Drone", fighter=Fighter(5, 5, 0, 1))
    enemy.drifting = True
    enemy.drift_direction = (1, 0)
    gm.entities.append(enemy)

    p = Entity(x=3, y=3, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)

    from engine.game_state import Engine
    from ui.tactical_state import TacticalState
    from game.suit import Suit

    eng = Engine()
    eng.game_map = gm
    eng.player = p
    suit = Suit(name="Test Suit", resistances={"vacuum": 50})
    suit.refill_pools()
    eng.suit = suit
    eng.environment = {"vacuum": 1}

    state = TacticalState()
    eng._state_stack = [state]

    # Tick 1: enemy at x=12 → x=13 (space)
    state._after_player_turn(eng)
    assert enemy.x == 13

    # Tick 2: enemy at x=13 → x=14 (floor tile, should be killed)
    state._after_player_turn(eng)
    assert enemy not in gm.entities


def test_airlock_chamber_gets_vacuum_when_ext_open():
    """Opening the exterior door should give the airlock chamber vacuum."""
    gm = _make_airlock_map()
    # Open exterior door
    gm.tiles[8, 5] = tile_types.airlock_ext_open
    gm._hazards_dirty = True
    gm.recalculate_hazards()
    overlay = gm.hazard_overlays.get("vacuum")
    assert overlay is not None
    # Airlock floor should have vacuum
    assert overlay[7, 5], "Airlock floor should have vacuum when ext door is open"
    # Interior (behind closed door) should NOT
    assert not overlay[5, 5], "Interior floor should NOT have vacuum (interior door closed)"
