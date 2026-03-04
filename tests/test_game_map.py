"""Tests for GameMap."""
from world.game_map import GameMap
from world import tile_types
from game.entity import Entity


def test_in_bounds():
    gm = GameMap(10, 10)
    assert gm.in_bounds(0, 0)
    assert gm.in_bounds(9, 9)
    assert not gm.in_bounds(-1, 0)
    assert not gm.in_bounds(10, 0)


def test_default_tiles_are_walls():
    gm = GameMap(5, 5)
    assert not gm.is_walkable(2, 2)


def test_floor_is_walkable():
    gm = GameMap(5, 5)
    gm.tiles[2, 2] = tile_types.floor
    assert gm.is_walkable(2, 2)


def test_get_blocking_entity():
    gm = GameMap(5, 5)
    e = Entity(x=2, y=2, blocks_movement=True)
    gm.entities.append(e)
    assert gm.get_blocking_entity(2, 2) is e
    assert gm.get_blocking_entity(3, 3) is None


def test_get_items_at():
    gm = GameMap(5, 5)
    item = Entity(x=2, y=2, blocks_movement=False, name="TestItem", item={"type": "heal", "value": 5})
    gm.entities.append(item)
    items = gm.get_items_at(2, 2)
    assert len(items) == 1
    assert items[0].name == "TestItem"


def test_get_items_at_excludes_interactables():
    gm = GameMap(5, 5)
    inter = Entity(x=2, y=2, blocks_movement=False, name="Console", interactable={"kind": "console"})
    gm.entities.append(inter)
    items = gm.get_items_at(2, 2)
    assert len(items) == 0


def test_fov_updates_visibility():
    gm = GameMap(20, 20)
    for x in range(1, 19):
        for y in range(1, 19):
            gm.tiles[x, y] = tile_types.floor

    assert not gm.visible[10, 10]
    gm.update_fov(10, 10, radius=8)
    assert gm.visible[10, 10]
    assert gm.explored[10, 10]


def test_fully_lit_still_requires_exploration():
    gm = GameMap(20, 20)
    for x in range(1, 19):
        for y in range(1, 19):
            gm.tiles[x, y] = tile_types.floor
    gm.fully_lit = True

    gm.update_fov(10, 10, radius=8)

    # Visible follows actual LOS
    assert gm.visible[10, 10]
    assert not gm.visible[0, 0]  # corner wall, not transparent
    # Explored earned by visiting, not granted for free
    assert gm.explored[10, 10]
    assert not gm.explored[0, 0]


def test_tile_lit_graphic_between_dark_and_light():
    """The auto-generated 'lit' graphic brightness sits between dark and light."""
    tile = tile_types.floor
    dark_fg = tuple(tile["dark"]["fg"])
    light_fg = tuple(tile["light"]["fg"])
    lit_fg = tuple(tile["lit"]["fg"])
    for d, li, l in zip(dark_fg, lit_fg, light_fg):
        assert d <= li <= l


def test_fov_uses_map_radius():
    """update_fov defaults to self.fov_radius, giving a larger FOV in lit areas."""
    gm = GameMap(40, 40)
    for x in range(1, 39):
        for y in range(1, 39):
            gm.tiles[x, y] = tile_types.floor

    # Default radius=8: tile 17 cells away should NOT be visible
    gm.fov_radius = 8
    gm.update_fov(20, 20)
    assert not gm.visible[20, 3]

    # Larger radius: same tile now visible
    gm.fov_radius = 20
    gm.update_fov(20, 20)
    assert gm.visible[20, 3]
