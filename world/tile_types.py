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


def new_tile(
    *,
    walkable: bool,
    transparent: bool,
    dark: tuple,
    light: tuple,
    base_tile_id: int | None = None,
) -> np.ndarray:
    global _next_tile_id
    if base_tile_id is not None:
        tid = base_tile_id
    else:
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

flora_low = new_tile(
    walkable=True, transparent=True,
    dark=(ord("*"), (50, 65, 35), (6, 5, 4)),
    light=(ord("*"), (100, 130, 70), (12, 10, 7)),
)

flora_tall = new_tile(
    walkable=True, transparent=True,
    dark=(ord("|"), (40, 60, 30), (6, 5, 4)),
    light=(ord("|"), (80, 120, 60), (12, 10, 7)),
)

flora_scrub = new_tile(
    walkable=True, transparent=True,
    dark=(ord(";"), (45, 55, 30), (6, 5, 4)),
    light=(ord(";"), (90, 110, 60), (12, 10, 7)),
)

flora_sprout = new_tile(
    walkable=True, transparent=True,
    dark=(ord(":"), (40, 50, 28), (6, 5, 4)),
    light=(ord(":"), (80, 100, 55), (12, 10, 7)),
)

path = new_tile(
    walkable=True, transparent=True,
    dark=(0xB7, (100, 100, 100), (15, 15, 15)),
    light=(0xB7, (180, 180, 180), (30, 30, 30)),
)

space = new_tile(
    walkable=False, transparent=True,
    dark=(ord(" "), (5, 5, 15), (0, 0, 2)),
    light=(ord(" "), (10, 10, 20), (0, 0, 4)),
)

hull_breach = new_tile(
    walkable=True, transparent=True,
    dark=(ord("X"), (150, 40, 40), (20, 0, 0)),
    light=(ord("X"), (255, 80, 60), (40, 5, 5)),
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

reactor_core = new_tile(
    walkable=False, transparent=True,
    dark=(ord("\xea"), (30, 10, 50), (10, 0, 20)),
    light=(ord("\xea"), (180, 80, 255), (40, 15, 70)),
)

control_console = new_tile(
    walkable=False, transparent=True,
    dark=(ord("\xc9"), (20, 40, 60), (5, 10, 20)),
    light=(ord("\xc9"), (80, 200, 255), (15, 40, 60)),
)

street_lamp = new_tile(
    walkable=False, transparent=True,
    dark=(ord("\xee"), (100, 90, 50), (10, 10, 5)),
    light=(ord("\xee"), (220, 200, 140), (30, 25, 15)),
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
        "Your ship's boarding ramp. Ready to depart.",
        "The landing pad beacon pulses beneath your feet.",
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
    int(path["tile_id"]): ("Path", [
        "A worn trail between buildings.",
        "Packed gravel crunches underfoot.",
        "A well-trodden path through the settlement.",
        "Compacted stone paving, smooth from use.",
    ]),
    int(flora_low["tile_id"]): ("Low Growth", [
        "A cluster of hardy plants, low to the ground.",
        "Scrubby vegetation clings to the soil.",
        "Small plants dot the ground here.",
    ]),
    int(flora_tall["tile_id"]): ("Tall Growth", [
        "Stalky plants sway gently.",
        "Tall shoots rise from the ground.",
        "Upright stems lean in the still air.",
    ]),
    int(flora_scrub["tile_id"]): ("Scrub", [
        "Low, tangled brush catches at your ankles.",
        "Wiry scrub clings to the soil.",
        "Sparse brush, dry and scratchy.",
    ]),
    int(flora_sprout["tile_id"]): ("Sprouts", [
        "Tiny shoots poke through the dirt.",
        "Small, pale sprouts dot the ground.",
        "Young growth, barely ankle-high.",
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
    int(hull_breach["tile_id"]): ("Hull Breach", [
        "A jagged tear in the hull. Vacuum howls through.",
        "Twisted metal frames a gaping hole to space.",
        "The hull is ripped open here. Stars glint beyond.",
        "A catastrophic breach. The void seeps in.",
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
    int(reactor_core["tile_id"]): ("Reactor Core", [
        "A pulsing reactor core, radiating heat and light.",
        "The ship's power plant thrums with contained energy.",
        "A glowing reactor housing, dangerously exposed.",
        "The core hums with barely-contained fusion.",
    ]),
    int(control_console["tile_id"]): ("Control Console", [
        "A bank of flickering displays and controls.",
        "The ship's main console, screens still glowing.",
        "A curved control station bristling with readouts.",
        "Navigation instruments glow faintly in the dark.",
    ]),
    int(street_lamp["tile_id"]): ("Street Lamp", [
        "A weathered lamp post, casting a warm glow.",
        "A colony light standard, humming faintly.",
        "A battered street light, still functional.",
    ]),
    int(airlock_switch_on["tile_id"]): ("Airlock Switch (On)", [
        "A heavy lever set into the wall. Currently on.",
        "An airlock control switch in the on position.",
        "A wall-mounted switch. The indicator light glows green.",
    ]),
}


def describe_tile(tile_id: int, *, biome: str | None = None) -> tuple[str, str]:
    """Return (tile_name, random_flavor_text) for a tile_id.

    If *biome* is provided, biome-specific flavor text is used for
    ground and path tiles (falling back to defaults for other tiles).
    """
    if biome:
        from world.palettes import BIOME_FLAVORS
        biome_overrides = BIOME_FLAVORS.get(biome)
        if biome_overrides and tile_id in biome_overrides:
            name, flavors = biome_overrides[tile_id]
            return name, _random.choice(flavors)
    name, flavors = TILE_FLAVORS.get(
        tile_id, ("Unknown", ["You can't make out what this is."])
    )
    return name, _random.choice(flavors)
