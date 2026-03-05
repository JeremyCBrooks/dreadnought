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
    # Wall partition blocking LOS to far corner
    for y in range(0, 20):
        gm.tiles[15, y] = tile_types.wall
    gm.fully_lit = True

    gm.update_fov(10, 10, radius=8)

    # Visible follows actual LOS
    assert gm.visible[10, 10]
    assert not gm.visible[18, 10]  # behind wall, not visible
    # Explored earned by visiting, not granted for free
    assert gm.explored[10, 10]
    assert not gm.explored[18, 10]


def test_tile_lit_graphic_between_dark_and_light():
    """The auto-generated 'lit' graphic brightness sits between dark and light."""
    tile = tile_types.floor
    dark_fg = tuple(tile["dark"]["fg"])
    light_fg = tuple(tile["light"]["fg"])
    lit_fg = tuple(tile["lit"]["fg"])
    for d, li, l in zip(dark_fg, lit_fg, light_fg):
        assert d <= li <= l


def test_fov_infinite_los():
    """Player can see distant tiles in line of sight regardless of fov_radius."""
    gm = GameMap(40, 40)
    for x in range(1, 39):
        for y in range(1, 39):
            gm.tiles[x, y] = tile_types.floor

    gm.fov_radius = 8
    gm.update_fov(20, 20)
    # Distant tile in clear LOS is visible even beyond fov_radius
    assert gm.visible[20, 3]


def test_fov_lit_mask_uses_radius():
    """Only tiles within fov_radius are marked as 'lit' (bright appearance)."""
    gm = GameMap(40, 40)
    for x in range(1, 39):
        for y in range(1, 39):
            gm.tiles[x, y] = tile_types.floor

    gm.fov_radius = 8
    gm.update_fov(20, 20)
    # Nearby tile is lit
    assert gm.lit[20, 19]
    # Distant visible tile is NOT lit
    assert gm.visible[20, 3]
    assert not gm.lit[20, 3]


def test_fov_radius_change_affects_lit():
    """Changing fov_radius changes which tiles are lit."""
    gm = GameMap(40, 40)
    for x in range(1, 39):
        for y in range(1, 39):
            gm.tiles[x, y] = tile_types.floor

    gm.fov_radius = 8
    gm.update_fov(20, 20)
    assert not gm.lit[20, 3]

    gm.fov_radius = 20
    gm.update_fov(20, 20)
    assert gm.lit[20, 3]
