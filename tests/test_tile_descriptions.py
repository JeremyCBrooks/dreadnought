"""Tests for tile flavor text and map position descriptions."""

from game.entity import Entity, Fighter
from world import tile_types
from world.game_map import GameMap
from world.tile_types import (
    TILE_FLAVORS,
    describe_tile,
    dirt_floor,
    exit_tile,
    floor,
    flora_low,
    flora_tall,
    ground,
    path,
    rock_floor,
    rock_wall,
    structure_wall,
    wall,
)


def test_describe_floor():
    tid = int(floor["tile_id"])
    name, flavor = describe_tile(tid)
    assert name == "Floor"
    assert flavor in TILE_FLAVORS[tid][1]


def test_describe_wall():
    tid = int(wall["tile_id"])
    name, flavor = describe_tile(tid)
    assert name == "Wall"
    assert flavor in TILE_FLAVORS[tid][1]


def test_describe_exit():
    tid = int(exit_tile["tile_id"])
    name, flavor = describe_tile(tid)
    assert name == "Exit"


def test_describe_rock_floor():
    tid = int(rock_floor["tile_id"])
    name, _ = describe_tile(tid)
    assert name == "Cavern Floor"


def test_describe_rock_wall():
    tid = int(rock_wall["tile_id"])
    name, _ = describe_tile(tid)
    assert name == "Rock Wall"


def test_describe_dirt_floor():
    tid = int(dirt_floor["tile_id"])
    name, _ = describe_tile(tid)
    assert name == "Dirt Floor"


def test_describe_structure_wall():
    tid = int(structure_wall["tile_id"])
    name, _ = describe_tile(tid)
    assert name == "Structure Wall"


def test_describe_ground():
    tid = int(ground["tile_id"])
    name, _ = describe_tile(tid)
    assert name == "Open Ground"


def test_describe_ground_with_biome():
    """Biome-specific flavor text is used when biome is provided."""
    from world.palettes import BIOME_FLAVORS

    tid = int(ground["tile_id"])
    for biome_name in ("desert", "grassland", "frozen", "alien"):
        name, flavor = describe_tile(tid, biome=biome_name)
        assert name != "Open Ground", f"biome {biome_name} should have custom ground name"
        expected_flavors = BIOME_FLAVORS[biome_name][tid][1]
        assert flavor in expected_flavors, f"biome {biome_name} flavor not from biome list"


def test_describe_ground_without_biome_uses_default():
    """Without a biome, default flavors are returned."""
    tid = int(ground["tile_id"])
    name, flavor = describe_tile(tid)
    assert name == "Open Ground"
    assert flavor in TILE_FLAVORS[tid][1]


def test_describe_path_with_biome():
    """Path tiles also get biome-specific flavor text."""
    from world.palettes import BIOME_FLAVORS

    tid = int(path["tile_id"])
    for biome_name in ("desert", "frozen", "alien"):
        name, flavor = describe_tile(tid, biome=biome_name)
        assert name != "Path", f"biome {biome_name} should have custom path name"
        expected_flavors = BIOME_FLAVORS[biome_name][tid][1]
        assert flavor in expected_flavors


def test_describe_flora_with_biome():
    """Flora tiles get biome-specific flavor text."""
    from world.palettes import BIOME_FLAVORS

    for biome_name in ("grassland", "alien", "frozen"):
        for flora_tile in (flora_low, flora_tall):
            tid = int(flora_tile["tile_id"])
            if tid in BIOME_FLAVORS.get(biome_name, {}):
                name, flavor = describe_tile(tid, biome=biome_name)
                expected_flavors = BIOME_FLAVORS[biome_name][tid][1]
                assert flavor in expected_flavors


def test_flora_has_default_flavor():
    """Flora tiles have default flavor text even without biome."""
    for flora_tile in (flora_low, flora_tall):
        tid = int(flora_tile["tile_id"])
        name, flavor = describe_tile(tid)
        assert name != "Unknown"
        assert flavor != "You can't make out what this is."


def test_biome_on_game_map():
    """GameMap should store biome name and pass it to underfoot."""
    gm = GameMap(10, 10)
    assert gm.biome is None
    gm.biome = "frozen"
    assert gm.biome == "frozen"


def test_describe_unknown_tile():
    name, flavor = describe_tile(9999)
    assert name == "Unknown"


def test_game_map_describe_at_unexplored():
    gm = GameMap(10, 10)
    lines = gm.describe_at(5, 5)
    assert lines[0][0] == "Unexplored."


def test_game_map_describe_at_floor():
    gm = GameMap(10, 10)
    gm.tiles[5, 5] = tile_types.floor
    gm.explored[5, 5] = True
    gm.visible[5, 5] = True
    lines = gm.describe_at(5, 5)
    assert "Floor" in lines[0][0]


def test_game_map_describe_at_rock_floor():
    gm = GameMap(10, 10)
    gm.tiles[5, 5] = tile_types.rock_floor
    gm.explored[5, 5] = True
    gm.visible[5, 5] = True
    lines = gm.describe_at(5, 5)
    assert "Cavern Floor" in lines[0][0]


def test_game_map_describe_at_with_item():
    gm = GameMap(10, 10)
    gm.tiles[5, 5] = tile_types.floor
    gm.explored[5, 5] = True
    gm.visible[5, 5] = True
    item = Entity(x=5, y=5, char="/", name="Bent Pipe", blocks_movement=False, item={"type": "weapon"})
    gm.entities.append(item)
    lines = gm.describe_at(5, 5)
    assert any("Bent Pipe" in text for text, _ in lines)


def test_game_map_describe_at_with_enemy():
    gm = GameMap(10, 10)
    gm.tiles[5, 5] = tile_types.floor
    gm.explored[5, 5] = True
    gm.visible[5, 5] = True
    enemy = Entity(x=5, y=5, char="r", name="Rat", blocks_movement=True, fighter=Fighter(1, 1, 0, 1))
    gm.entities.append(enemy)
    lines = gm.describe_at(5, 5)
    assert any("Rat" in text for text, _ in lines)


def test_game_map_describe_at_out_of_bounds():
    gm = GameMap(10, 10)
    lines = gm.describe_at(-1, -1)
    assert lines[0][0] == "Nothing there."


def test_game_map_describe_at_explored_not_visible():
    gm = GameMap(10, 10)
    gm.tiles[5, 5] = tile_types.floor
    gm.explored[5, 5] = True
    gm.visible[5, 5] = False
    lines = gm.describe_at(5, 5, visible_only=True)
    assert "recall" in lines[0][0].lower()


# ---- Ground-lines on TacticalState (non-persistent) ----


def test_ground_lines_update_on_underfoot():
    """_update_ground_underfoot replaces _ground_lines, not the message log."""
    from engine.message_log import MessageLog
    from ui.tactical_state import TacticalState

    class FakeEngine:
        pass

    gm = GameMap(10, 10)
    for x in range(1, 9):
        for y in range(1, 9):
            gm.tiles[x, y] = tile_types.floor
    gm.visible[:] = True
    gm.explored[:] = True

    player = Entity(
        x=5, y=5, char="@", color=(255, 255, 255), name="Player", blocks_movement=True, fighter=Fighter(10, 10, 0, 1)
    )
    gm.entities.append(player)

    item = Entity(x=5, y=5, char="/", name="Pipe", blocks_movement=False, item={"type": "weapon"})
    gm.entities.append(item)

    eng = FakeEngine()
    eng.game_map = gm
    eng.player = player
    eng.message_log = MessageLog()

    state = TacticalState()
    state._update_ground_underfoot(eng)

    assert len(state._ground_lines) >= 2
    assert any("Pipe" in t for t, _ in state._ground_lines)

    # Message log should NOT have ground text
    assert all("Pipe" not in t for t, _ in eng.message_log.messages)
