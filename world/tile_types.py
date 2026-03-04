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


def new_tile(*, walkable: int, transparent: int, dark: tuple, light: tuple) -> np.ndarray:
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

ground = new_tile(
    walkable=True, transparent=True,
    dark=(ord(","), (65, 60, 45), (6, 5, 4)),
    light=(ord(","), (130, 120, 90), (12, 10, 7)),
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
    int(ground["tile_id"]): ("Open Ground", [
        "Dry, dusty terrain stretches around you.",
        "Loose soil crunches beneath your feet.",
        "Barren ground under an alien sky.",
        "Hard-packed earth between the buildings.",
    ]),
}


def describe_tile(tile_id: int) -> tuple[str, str]:
    """Return (tile_name, random_flavor_text) for a tile_id."""
    name, flavors = TILE_FLAVORS.get(
        tile_id, ("Unknown", ["You can't make out what this is."])
    )
    return name, _random.choice(flavors)
