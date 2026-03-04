"""Tile definitions as numpy structured arrays, with flavor descriptions."""
from __future__ import annotations

import random as _random

import numpy as np

graphic_dt = np.dtype([("ch", np.int32), ("fg", "3B"), ("bg", "3B")])

tile_dt = np.dtype([
    ("walkable", bool),
    ("transparent", bool),
    ("dark", graphic_dt),
    ("light", graphic_dt),
    ("lit", graphic_dt),
    ("tile_id", np.int32),
])

SHROUD = np.array((ord(" "), (255, 255, 255), (0, 0, 0)), dtype=graphic_dt)

_next_tile_id = 0


def _blend_graphic(dark: tuple, light: tuple, factor: float = 0.7) -> tuple:
    """Derive a 'lit' graphic by blending dark toward light."""
    ch = light[0]
    fg = tuple(int(d + (l - d) * factor) for d, l in zip(dark[1], light[1]))
    bg = tuple(int(d + (l - d) * factor) for d, l in zip(dark[2], light[2]))
    return (ch, fg, bg)


def new_tile(*, walkable: bool, transparent: bool, dark: tuple, light: tuple) -> np.ndarray:
    global _next_tile_id
    tid = _next_tile_id
    _next_tile_id += 1
    lit = _blend_graphic(dark, light)
    return np.array((walkable, transparent, dark, light, lit, tid), dtype=tile_dt)


floor = new_tile(
    walkable=True, transparent=True,
    dark=(ord("."), (100, 100, 150), (0, 0, 10)),
    light=(ord("."), (200, 200, 220), (10, 10, 30)),
)

wall = new_tile(
    walkable=False, transparent=False,
    dark=(ord("#"), (80, 80, 120), (0, 0, 20)),
    light=(ord("#"), (180, 180, 210), (30, 30, 60)),
)

exit_tile = new_tile(
    walkable=True, transparent=True,
    dark=(ord(">"), (0, 100, 100), (0, 0, 10)),
    light=(ord(">"), (0, 255, 200), (10, 10, 30)),
)

rock_floor = new_tile(
    walkable=True, transparent=True,
    dark=(ord("."), (85, 70, 50), (10, 8, 5)),
    light=(ord("."), (170, 140, 100), (20, 15, 10)),
)

rock_wall = new_tile(
    walkable=False, transparent=False,
    dark=(ord("#"), (80, 65, 45), (20, 15, 10)),
    light=(ord("#"), (160, 130, 90), (40, 30, 20)),
)

dirt_floor = new_tile(
    walkable=True, transparent=True,
    dark=(ord("."), (80, 70, 50), (8, 6, 4)),
    light=(ord("."), (160, 140, 100), (15, 12, 8)),
)

structure_wall = new_tile(
    walkable=False, transparent=False,
    dark=(ord("#"), (70, 80, 70), (12, 18, 12)),
    light=(ord("#"), (140, 160, 140), (25, 35, 25)),
)

structure_window = new_tile(
    walkable=False, transparent=True,
    dark=(ord("░"), (60, 80, 100), (10, 15, 25)),
    light=(ord("░"), (120, 180, 200), (20, 30, 50)),
)

ground = new_tile(
    walkable=True, transparent=True,
    dark=(ord(","), (65, 60, 45), (6, 5, 4)),
    light=(ord(","), (130, 120, 90), (12, 10, 7)),
)

space = new_tile(
    walkable=False, transparent=True,
    dark=(ord(" "), (5, 5, 15), (0, 0, 2)),
    light=(ord(" "), (10, 10, 20), (0, 0, 4)),
)

door_closed = new_tile(
    walkable=False, transparent=False,
    dark=(ord("+"), (80, 60, 30), (10, 8, 5)),
    light=(ord("+"), (160, 120, 60), (20, 15, 10)),
)

door_open = new_tile(
    walkable=True, transparent=True,
    dark=(ord("/"), (60, 50, 25), (10, 8, 5)),
    light=(ord("/"), (130, 100, 50), (20, 15, 10)),
)

airlock_floor = new_tile(
    walkable=True, transparent=True,
    dark=(ord("="), (120, 100, 30), (10, 8, 2)),
    light=(ord("="), (220, 180, 50), (20, 18, 5)),
)

# Exterior airlock door — hull-colored so it blends with the hull
airlock_ext_closed = new_tile(
    walkable=False, transparent=False,
    dark=(ord("+"), (80, 80, 120), (0, 0, 20)),
    light=(ord("+"), (170, 170, 210), (25, 25, 55)),
)

airlock_ext_open = new_tile(
    walkable=True, transparent=True,
    dark=(ord("/"), (70, 70, 110), (0, 0, 20)),
    light=(ord("/"), (150, 150, 200), (25, 25, 55)),
)

airlock_switch_off = new_tile(
    walkable=False, transparent=False,
    dark=(ord("/"), (80, 80, 120), (0, 0, 20)),
    light=(ord("/"), (180, 180, 210), (30, 30, 60)),
)

airlock_switch_on = new_tile(
    walkable=False, transparent=False,
    dark=(ord("\\"), (80, 120, 80), (0, 20, 0)),
    light=(ord("\\"), (180, 210, 180), (30, 60, 30)),
)

# ---------------------------------------------------------------------------
# Tile flavor text -- keyed by tile_id
# ---------------------------------------------------------------------------
TILE_FLAVORS: dict[int, tuple[str, list[str]]] = {
    int(floor["tile_id"]): ("Floor", [
        "Scuffed metal plating.",
        "Worn deck panels, slightly warped.",
        "A patch of corroded grating.",
        "Dusty floor tiles crunch underfoot.",
        "The floor hums faintly beneath you.",
        "Dull grey decking streaked with grime.",
        "Riveted plates, cold through your boots.",
    ]),
    int(wall["tile_id"]): ("Wall", [
        "Solid bulkhead, cold to the touch.",
        "Dented hull plating.",
        "Reinforced wall panel, barely holding.",
        "Thick metal wall covered in condensation.",
        "A wall of riveted steel plates.",
        "Scorched panelling with peeling paint.",
    ]),
    int(exit_tile["tile_id"]): ("Exit", [
        "The airlock back to your ship.",
        "An open hatch leading to the docking bay.",
        "The way out. Safety awaits beyond.",
    ]),
    int(rock_floor["tile_id"]): ("Cavern Floor", [
        "Rough stone, uneven underfoot.",
        "Crumbled rock dust and loose gravel.",
        "Cold mineral deposits glint faintly.",
        "Worn paths through ancient stone.",
    ]),
    int(rock_wall["tile_id"]): ("Rock Wall", [
        "Jagged stone veined with ore.",
        "Dense asteroid rock, cold and unyielding.",
        "A rough wall of compressed minerals.",
        "Pitted stone scarred by old drill marks.",
    ]),
    int(dirt_floor["tile_id"]): ("Dirt Floor", [
        "Packed earth, dry and dusty.",
        "Hard-trodden ground, cracked in places.",
        "A thin layer of red-brown soil.",
        "Compacted dirt with boot prints.",
    ]),
    int(structure_wall["tile_id"]): ("Structure Wall", [
        "Prefab panels bolted together.",
        "Weathered composite wall, slightly bowed.",
        "A makeshift partition of salvaged metal.",
        "Thin walls, you can hear the wind outside.",
    ]),
    int(structure_window["tile_id"]): ("Window", [
        "A translucent composite pane, slightly fogged.",
        "Thick glass bolted into the wall frame.",
        "A narrow window letting in pale light.",
        "Scratched viewport, you can just see through.",
    ]),
    int(ground["tile_id"]): ("Open Ground", [
        "Dry, dusty terrain stretches around you.",
        "Loose soil crunches beneath your feet.",
        "Barren ground under an alien sky.",
        "Hard-packed earth between the buildings.",
    ]),
    int(door_closed["tile_id"]): ("Closed Door", [
        "A heavy door, sealed shut.",
        "A closed bulkhead door.",
        "A reinforced door blocks the way.",
        "A sealed hatch, firmly latched.",
    ]),
    int(door_open["tile_id"]): ("Open Door", [
        "An open doorway.",
        "A door, propped open.",
        "An open hatch in the bulkhead.",
        "A doorframe, passage clear.",
    ]),
    int(airlock_ext_closed["tile_id"]): ("Exterior Airlock Door", [
        "A heavy hull door. Space lies beyond.",
        "Reinforced exterior hatch, sealed tight.",
        "The outer airlock door. Think carefully.",
        "Hull-grade plating. One-way trip beyond this.",
    ]),
    int(airlock_ext_open["tile_id"]): ("Exterior Airlock Door (Open)", [
        "The outer door gapes open. Stars beckon.",
        "An open hatch to the void. No going back.",
        "The exterior door stands open. Vacuum beyond.",
    ]),
    int(airlock_floor["tile_id"]): ("Airlock", [
        "A narrow airlock chamber. The void waits beyond.",
        "Warning stripes line the airlock floor.",
        "The airlock hums with pressure equalization systems.",
        "A cramped chamber between you and the vacuum.",
    ]),
    int(space["tile_id"]): ("Space", [
        "The cold void stretches endlessly.",
        "Stars drift silently in the dark.",
        "Infinite emptiness beyond the hull.",
        "The black of space, vast and still.",
    ]),
    int(airlock_switch_off["tile_id"]): ("Airlock Switch (Off)", [
        "A heavy lever set into the wall. Currently off.",
        "An airlock control switch in the off position.",
        "A wall-mounted switch. The indicator light is dark.",
    ]),
    int(airlock_switch_on["tile_id"]): ("Airlock Switch (On)", [
        "A heavy lever set into the wall. Currently on.",
        "An airlock control switch in the on position.",
        "A wall-mounted switch. The indicator light glows green.",
    ]),
}


def describe_tile(tile_id: int) -> tuple[str, str]:
    """Return (tile_name, random_flavor_text) for a tile_id."""
    name, flavors = TILE_FLAVORS.get(
        tile_id, ("Unknown", ["You can't make out what this is."])
    )
    return name, _random.choice(flavors)
