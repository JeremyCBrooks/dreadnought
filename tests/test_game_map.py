"""Tests for GameMap."""

from game.entity import Entity
from world import tile_types
from world.game_map import GameMap


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
    for d, li, lv in zip(dark_fg, lit_fg, light_fg):
        assert d <= li <= lv


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


def test_get_interactable_at():
    gm = GameMap(10, 10)
    console = Entity(x=3, y=3, name="Console", blocks_movement=False, interactable={"kind": "console"})
    gm.entities.append(console)
    assert gm.get_interactable_at(3, 3) is console
    assert gm.get_interactable_at(4, 4) is None


def test_get_interactable_at_ignores_non_interactable():
    gm = GameMap(10, 10)
    item = Entity(x=3, y=3, name="Pipe", blocks_movement=False, item={"type": "weapon", "value": 1})
    gm.entities.append(item)
    assert gm.get_interactable_at(3, 3) is None


def test_invalidate_hazards_sets_dirty_and_lights():
    """invalidate_hazards marks hazards dirty and invalidates light cache."""
    gm = GameMap(5, 5)
    gm._hazards_dirty = False
    gm._light_dirty = False
    gm.invalidate_hazards()
    assert gm._hazards_dirty is True
    assert gm._light_dirty is True


def test_glow_tint_out_of_bounds_no_crash():
    """_glow_tint_color should handle out-of-bounds glow_mask gracefully."""
    import numpy as np

    from tests.conftest import make_arena

    gm = make_arena(10, 10)
    glow_mask = np.full((8, 8), fill_value=True, order="F")
    color = (200, 200, 200)
    # Entity at edge, camera at 0,0 — lx=9, ly=9 is out of 8x8 glow_mask
    result = gm._glow_tint_color(color, 9, 9, glow_mask, 0.5, 0, 0)
    assert result == color  # should return unchanged color


def test_describe_at_uses_spatial_index():
    """describe_at should use the spatial index, not iterate all entities."""
    gm = GameMap(10, 10)
    gm.tiles[5, 5] = tile_types.floor
    gm.explored[5, 5] = True

    item = Entity(x=5, y=5, blocks_movement=False, name="Key", item={"type": "key"})
    far = Entity(x=9, y=9, blocks_movement=False, name="Far", item={"type": "key"})
    gm.entities.extend([item, far])

    lines = gm.describe_at(5, 5)
    names = [line[0] for line in lines]
    assert any("Key" in n for n in names)
    assert not any("Far" in n for n in names)


def test_clear_fov_cache():
    """clear_fov_cache should empty the internal FOV cache dict."""
    gm = GameMap(5, 5)
    gm._fov_cache[(1, 1, 5)] = gm._empty_bool_grid()
    assert len(gm._fov_cache) == 1
    gm.clear_fov_cache()
    assert len(gm._fov_cache) == 0
