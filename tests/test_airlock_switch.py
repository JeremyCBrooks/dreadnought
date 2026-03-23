"""Tests for airlock switch mechanism."""

import pytest

from game.actions import ToggleDoorAction, ToggleSwitchAction
from game.entity import Entity, Fighter
from tests.conftest import MockEngine
from world import tile_types
from world.game_map import GameMap


def _make_airlock_map():
    """Build a small map with one airlock and switch.

    Layout (10x10, wall border, floor interior):
      Switch at (1, 3) — wall tile replaced with switch
      Interior door at (1, 4) — door_closed
      Airlock floor at (1, 5)
      Exterior door at (1, 6) — airlock_ext_closed
      Player at (2, 3)
    """
    gm = GameMap(10, 10)
    # Fill interior with floor
    for x in range(1, 9):
        for y in range(1, 9):
            gm.tiles[x, y] = tile_types.floor

    # Place airlock components
    gm.tiles[1, 4] = tile_types.door_closed
    gm.tiles[1, 5] = tile_types.airlock_floor
    gm.tiles[1, 6] = tile_types.airlock_ext_closed
    gm.tiles[1, 3] = tile_types.airlock_switch_off

    gm.airlocks.append(
        {
            "interior_door": (1, 4),
            "exterior_door": (1, 6),
            "direction": (0, 1),
            "switch": (1, 3),
        }
    )

    player = Entity(x=2, y=3, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    return gm, player


# ---------------------------------------------------------------------------
# Tile type properties
# ---------------------------------------------------------------------------


class TestSwitchTileProperties:
    def test_switch_off_not_walkable(self):
        assert not bool(tile_types.airlock_switch_off["walkable"])

    def test_switch_off_not_transparent(self):
        assert not bool(tile_types.airlock_switch_off["transparent"])

    def test_switch_on_not_walkable(self):
        assert not bool(tile_types.airlock_switch_on["walkable"])

    def test_switch_on_not_transparent(self):
        assert not bool(tile_types.airlock_switch_on["transparent"])

    def test_switch_off_flavor_text(self):
        tid = int(tile_types.airlock_switch_off["tile_id"])
        assert tid in tile_types.TILE_FLAVORS
        name, flavors = tile_types.TILE_FLAVORS[tid]
        assert "Off" in name
        assert len(flavors) > 0

    def test_switch_on_flavor_text(self):
        tid = int(tile_types.airlock_switch_on["tile_id"])
        assert tid in tile_types.TILE_FLAVORS
        name, flavors = tile_types.TILE_FLAVORS[tid]
        assert "On" in name
        assert len(flavors) > 0

    def test_switch_tiles_have_distinct_ids(self):
        off_id = int(tile_types.airlock_switch_off["tile_id"])
        on_id = int(tile_types.airlock_switch_on["tile_id"])
        assert off_id != on_id


# ---------------------------------------------------------------------------
# ToggleSwitchAction
# ---------------------------------------------------------------------------


class TestToggleSwitchAction:
    def test_switch_opens_exterior_door(self):
        gm, player = _make_airlock_map()
        engine = MockEngine(gm, player)

        # Switch is off, exterior door closed
        assert int(gm.tiles["tile_id"][1, 3]) == int(tile_types.airlock_switch_off["tile_id"])
        assert int(gm.tiles["tile_id"][1, 6]) == int(tile_types.airlock_ext_closed["tile_id"])

        result = ToggleSwitchAction(-1, 0).perform(engine, player)
        assert result == 1

        # Switch is now on, exterior door open
        assert int(gm.tiles["tile_id"][1, 3]) == int(tile_types.airlock_switch_on["tile_id"])
        assert int(gm.tiles["tile_id"][1, 6]) == int(tile_types.airlock_ext_open["tile_id"])

    def test_switch_closes_exterior_door(self):
        gm, player = _make_airlock_map()
        engine = MockEngine(gm, player)

        # Open first
        ToggleSwitchAction(-1, 0).perform(engine, player)
        # Then close
        result = ToggleSwitchAction(-1, 0).perform(engine, player)
        assert result == 1

        assert int(gm.tiles["tile_id"][1, 3]) == int(tile_types.airlock_switch_off["tile_id"])
        assert int(gm.tiles["tile_id"][1, 6]) == int(tile_types.airlock_ext_closed["tile_id"])

    def test_switch_blocked_by_entity(self):
        gm, player = _make_airlock_map()
        engine = MockEngine(gm, player)

        # Open door first
        ToggleSwitchAction(-1, 0).perform(engine, player)

        # Place blocking entity on exterior door
        blocker = Entity(x=1, y=6, name="Blocker", blocks_movement=True, fighter=Fighter(5, 5, 0, 1))
        gm.entities.append(blocker)

        # Try to close — should fail
        result = ToggleSwitchAction(-1, 0).perform(engine, player)
        assert result == 0
        # Switch stays on, door stays open
        assert int(gm.tiles["tile_id"][1, 3]) == int(tile_types.airlock_switch_on["tile_id"])
        assert int(gm.tiles["tile_id"][1, 6]) == int(tile_types.airlock_ext_open["tile_id"])

    def test_switch_on_non_switch_tile(self):
        gm, player = _make_airlock_map()
        engine = MockEngine(gm, player)
        # Point at a floor tile instead of the switch
        result = ToggleSwitchAction(0, -1).perform(engine, player)
        assert result == 0

    def test_switch_on_unlinked_switch(self):
        """A switch tile not in any airlock dict returns 0."""
        gm, player = _make_airlock_map()
        # Place an orphan switch at (3, 3)
        gm.tiles[3, 3] = tile_types.airlock_switch_off
        player.x, player.y = 4, 3
        engine = MockEngine(gm, player)
        result = ToggleSwitchAction(-1, 0).perform(engine, player)
        assert result == 0
        assert "connected" in engine.message_log.messages[-1][0].lower()


# ---------------------------------------------------------------------------
# ToggleDoorAction blocks exterior doors
# ---------------------------------------------------------------------------


class TestToggleDoorBlocksExterior:
    def test_cannot_manually_open_exterior_closed(self):
        gm, player = _make_airlock_map()
        player.x, player.y = 2, 6
        engine = MockEngine(gm, player)

        result = ToggleDoorAction(-1, 0).perform(engine, player)
        assert result == 0
        assert int(gm.tiles["tile_id"][1, 6]) == int(tile_types.airlock_ext_closed["tile_id"])
        assert "switch" in engine.message_log.messages[-1][0].lower()

    def test_cannot_manually_close_exterior_open(self):
        gm, player = _make_airlock_map()
        gm.tiles[1, 6] = tile_types.airlock_ext_open
        player.x, player.y = 2, 6
        engine = MockEngine(gm, player)

        result = ToggleDoorAction(-1, 0).perform(engine, player)
        assert result == 0
        assert int(gm.tiles["tile_id"][1, 6]) == int(tile_types.airlock_ext_open["tile_id"])
        assert "switch" in engine.message_log.messages[-1][0].lower()

    def test_normal_door_still_works(self):
        gm, player = _make_airlock_map()
        player.x, player.y = 2, 4
        engine = MockEngine(gm, player)

        result = ToggleDoorAction(-1, 0).perform(engine, player)
        assert result == 1
        assert int(gm.tiles["tile_id"][1, 4]) == int(tile_types.door_open["tile_id"])

    def test_close_normal_door_still_works(self):
        gm, player = _make_airlock_map()
        gm.tiles[1, 4] = tile_types.door_open
        player.x, player.y = 2, 4
        engine = MockEngine(gm, player)

        result = ToggleDoorAction(-1, 0).perform(engine, player)
        assert result == 1
        assert int(gm.tiles["tile_id"][1, 4]) == int(tile_types.door_closed["tile_id"])


# ---------------------------------------------------------------------------
# Interact direction detection
# ---------------------------------------------------------------------------


class TestAdjacentInteractDirs:
    def test_detects_switch_kind(self):
        from ui.tactical_state import TacticalState

        gm, player = _make_airlock_map()
        engine = MockEngine(gm, player)
        dirs = TacticalState._adjacent_interact_dirs(engine)
        switch_dirs = [(dx, dy, k) for dx, dy, k in dirs if k == "switch"]
        assert len(switch_dirs) == 1
        assert switch_dirs[0] == (-1, 0, "switch")

    def test_detects_switch_on_kind(self):
        from ui.tactical_state import TacticalState

        gm, player = _make_airlock_map()
        gm.tiles[1, 3] = tile_types.airlock_switch_on
        engine = MockEngine(gm, player)
        dirs = TacticalState._adjacent_interact_dirs(engine)
        switch_dirs = [(dx, dy, k) for dx, dy, k in dirs if k == "switch"]
        assert len(switch_dirs) == 1

    def test_detects_door_kind(self):
        from ui.tactical_state import TacticalState

        gm, player = _make_airlock_map()
        # Player at (2,3), door at (1,4) is diagonal — should be detected
        engine = MockEngine(gm, player)
        dirs = TacticalState._adjacent_interact_dirs(engine)
        door_dirs = [(dx, dy, k) for dx, dy, k in dirs if k == "door"]
        assert len(door_dirs) >= 1


# ---------------------------------------------------------------------------
# Dungeon generation placement
# ---------------------------------------------------------------------------


class TestSwitchPlacement:
    @pytest.mark.parametrize("seed", [42, 100, 7, 999, 2024])
    def test_dungeon_gen_places_switches(self, seed):
        """Generated dungeons with airlocks should have switch key in dict."""
        from world.dungeon_gen import generate_dungeon

        gm, rooms, exit_pos = generate_dungeon(
            width=80,
            height=60,
            max_enemies=0,
            max_items=0,
            seed=seed,
            loc_type="derelict",
        )
        for al in gm.airlocks:
            assert "switch" in al, "Airlock dict must have 'switch' key"
            if al["switch"] is not None:
                sx, sy = al["switch"]
                tid = int(gm.tiles["tile_id"][sx, sy])
                assert tid == int(tile_types.airlock_switch_off["tile_id"])

    @pytest.mark.parametrize("seed", [42, 100, 7, 999, 2024])
    def test_switch_adjacent_to_walkable(self, seed):
        """Each placed switch must be adjacent to at least one walkable tile."""
        from world.dungeon_gen import generate_dungeon

        gm, rooms, exit_pos = generate_dungeon(
            width=80,
            height=60,
            max_enemies=0,
            max_items=0,
            seed=seed,
            loc_type="derelict",
        )
        for al in gm.airlocks:
            if al["switch"] is None:
                continue
            sx, sy = al["switch"]
            has_walkable = False
            for ddx in (-1, 0, 1):
                for ddy in (-1, 0, 1):
                    if ddx == 0 and ddy == 0:
                        continue
                    nx, ny = sx + ddx, sy + ddy
                    if gm.in_bounds(nx, ny) and gm.tiles["walkable"][nx, ny]:
                        has_walkable = True
                        break
                if has_walkable:
                    break
            assert has_walkable, f"Switch at ({sx},{sy}) not adjacent to walkable tile"

    def test_switch_survives_hull_conversion(self):
        """Switch tile must not be converted to space by _convert_hull_to_space."""
        from world.dungeon_gen import generate_dungeon

        gm, rooms, exit_pos = generate_dungeon(
            width=80,
            height=60,
            max_enemies=0,
            max_items=0,
            seed=42,
            loc_type="derelict",
        )
        switch_off_tid = int(tile_types.airlock_switch_off["tile_id"])
        space_tid = int(tile_types.space["tile_id"])
        for al in gm.airlocks:
            if al["switch"] is None:
                continue
            sx, sy = al["switch"]
            tid = int(gm.tiles["tile_id"][sx, sy])
            assert tid == switch_off_tid, (
                f"Switch at ({sx},{sy}) has tid={tid}, expected {switch_off_tid} (space={space_tid})"
            )
