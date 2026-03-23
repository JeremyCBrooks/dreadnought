"""Tests for tile type definitions."""

from world.tile_types import (
    SHROUD,
    TILE_FLAVORS,
    _blend_graphic,
    airlock_ext_closed,
    airlock_ext_open,
    airlock_floor,
    airlock_switch_off,
    airlock_switch_on,
    control_console,
    dirt_floor,
    door_closed,
    door_open,
    exit_tile,
    floor,
    flora_low,
    flora_scrub,
    flora_sprout,
    flora_tall,
    graphic_dt,
    ground,
    hull_breach,
    new_tile,
    path,
    reactor_core,
    rock_floor,
    rock_wall,
    space,
    street_lamp,
    structure_wall,
    structure_window,
    tile_dt,
    wall,
)

# All defined tiles for parametric tests
ALL_TILES = {
    "floor": floor,
    "wall": wall,
    "exit_tile": exit_tile,
    "rock_floor": rock_floor,
    "rock_wall": rock_wall,
    "dirt_floor": dirt_floor,
    "structure_wall": structure_wall,
    "structure_window": structure_window,
    "ground": ground,
    "flora_low": flora_low,
    "flora_tall": flora_tall,
    "flora_scrub": flora_scrub,
    "flora_sprout": flora_sprout,
    "path": path,
    "space": space,
    "hull_breach": hull_breach,
    "door_closed": door_closed,
    "door_open": door_open,
    "airlock_floor": airlock_floor,
    "airlock_ext_closed": airlock_ext_closed,
    "airlock_ext_open": airlock_ext_open,
    "airlock_switch_off": airlock_switch_off,
    "airlock_switch_on": airlock_switch_on,
    "reactor_core": reactor_core,
    "control_console": control_console,
    "street_lamp": street_lamp,
}


# --- dtype structure ---


def test_tile_dtype_has_expected_fields():
    assert set(tile_dt.names) == {"walkable", "transparent", "dark", "light", "lit", "tile_id"}


def test_graphic_dtype_has_expected_fields():
    assert set(graphic_dt.names) == {"ch", "fg", "bg"}


def test_shroud_graphic():
    assert int(SHROUD["ch"]) == ord(" ")
    assert tuple(SHROUD["fg"]) == (255, 255, 255)
    assert tuple(SHROUD["bg"]) == (0, 0, 0)


# --- walkable / transparent properties ---


def test_floor_walkable_and_transparent():
    assert floor["walkable"]
    assert floor["transparent"]


def test_wall_not_walkable_or_transparent():
    assert not wall["walkable"]
    assert not wall["transparent"]


def test_exit_tile_walkable():
    assert exit_tile["walkable"]


def test_rock_floor_walkable():
    assert rock_floor["walkable"]
    assert rock_floor["transparent"]


def test_rock_wall_not_walkable():
    assert not rock_wall["walkable"]
    assert not rock_wall["transparent"]


def test_dirt_floor_walkable():
    assert dirt_floor["walkable"]
    assert dirt_floor["transparent"]


def test_structure_wall_not_walkable():
    assert not structure_wall["walkable"]
    assert not structure_wall["transparent"]


def test_structure_window_transparent_not_walkable():
    assert not structure_window["walkable"]
    assert structure_window["transparent"]


def test_ground_walkable_and_transparent():
    assert ground["walkable"]
    assert ground["transparent"]


def test_space_not_walkable():
    assert not space["walkable"]
    assert space["transparent"]


def test_hull_breach_walkable():
    assert hull_breach["walkable"]
    assert hull_breach["transparent"]


def test_door_closed_blocks():
    assert not door_closed["walkable"]
    assert not door_closed["transparent"]


def test_door_open_passable():
    assert door_open["walkable"]
    assert door_open["transparent"]


def test_airlock_ext_closed_blocks():
    assert not airlock_ext_closed["walkable"]
    assert not airlock_ext_closed["transparent"]


def test_airlock_ext_open_passable():
    assert airlock_ext_open["walkable"]
    assert airlock_ext_open["transparent"]


def test_reactor_core_transparent_not_walkable():
    assert not reactor_core["walkable"]
    assert reactor_core["transparent"]


# --- unique IDs across ALL tiles ---


def test_each_tile_has_unique_tile_id():
    ids = {name: int(t["tile_id"]) for name, t in ALL_TILES.items()}
    seen: dict[int, str] = {}
    for name, tid in ids.items():
        assert tid not in seen, f"Duplicate tile_id {tid}: {name} and {seen[tid]}"
        seen[tid] = name


# --- every tile has flavor text ---


def test_every_tile_has_flavor_entry():
    for name, tile in ALL_TILES.items():
        tid = int(tile["tile_id"])
        assert tid in TILE_FLAVORS, f"Tile '{name}' (id={tid}) missing from TILE_FLAVORS"
        label, flavors = TILE_FLAVORS[tid]
        assert isinstance(label, str) and label, f"Tile '{name}' has empty label"
        assert isinstance(flavors, list) and flavors, f"Tile '{name}' has no flavor strings"


# --- _blend_graphic ---


def test_blend_graphic_uses_light_char():
    dark = (ord("."), (0, 0, 0), (0, 0, 0))
    light = (ord("#"), (100, 100, 100), (50, 50, 50))
    result = _blend_graphic(dark, light)
    assert result[0] == ord("#"), "lit char should come from light graphic"


def test_blend_graphic_interpolates_colors():
    dark = (ord("."), (0, 0, 0), (0, 0, 0))
    light = (ord("."), (100, 200, 100), (50, 100, 50))
    ch, fg, bg = _blend_graphic(dark, light, factor=0.5)
    assert fg == (50, 100, 50)
    assert bg == (25, 50, 25)


def test_blend_graphic_factor_zero_returns_dark_colors():
    dark = (ord("."), (10, 20, 30), (5, 10, 15))
    light = (ord("#"), (100, 200, 255), (50, 100, 150))
    ch, fg, bg = _blend_graphic(dark, light, factor=0.0)
    assert fg == (10, 20, 30)
    assert bg == (5, 10, 15)


def test_blend_graphic_factor_one_returns_light_colors():
    dark = (ord("."), (10, 20, 30), (5, 10, 15))
    light = (ord("#"), (100, 200, 255), (50, 100, 150))
    ch, fg, bg = _blend_graphic(dark, light, factor=1.0)
    assert fg == (100, 200, 255)
    assert bg == (50, 100, 150)


def test_tile_lit_graphic_is_blend_of_dark_and_light():
    """The lit field on each tile should match _blend_graphic(dark, light)."""
    for name, tile in ALL_TILES.items():
        dark = (int(tile["dark"]["ch"]), tuple(tile["dark"]["fg"]), tuple(tile["dark"]["bg"]))
        light = (int(tile["light"]["ch"]), tuple(tile["light"]["fg"]), tuple(tile["light"]["bg"]))
        expected = _blend_graphic(dark, light)
        lit = tile["lit"]
        assert int(lit["ch"]) == expected[0], f"{name}: lit ch mismatch"
        assert tuple(lit["fg"]) == expected[1], f"{name}: lit fg mismatch"
        assert tuple(lit["bg"]) == expected[2], f"{name}: lit bg mismatch"


# --- new_tile with base_tile_id ---


def test_new_tile_with_base_tile_id():
    t = new_tile(
        walkable=True,
        transparent=True,
        dark=(ord("."), (0, 0, 0), (0, 0, 0)),
        light=(ord("."), (100, 100, 100), (50, 50, 50)),
        base_tile_id=9999,
    )
    assert int(t["tile_id"]) == 9999


def test_new_tile_returns_correct_dtype():
    t = new_tile(
        walkable=False,
        transparent=True,
        dark=(ord("X"), (10, 20, 30), (1, 2, 3)),
        light=(ord("X"), (100, 200, 255), (10, 20, 30)),
    )
    assert t.dtype == tile_dt
    assert not t["walkable"]
    assert t["transparent"]
    assert int(t["dark"]["ch"]) == ord("X")
