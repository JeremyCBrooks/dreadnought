"""Data-driven location profiles controlling dungeon generation style."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class RoomSpec:
    label: str
    min_w: int
    max_w: int
    min_h: int
    max_h: int
    required: bool = False
    max_count: int = -1  # -1 = unlimited


@dataclass(slots=True)
class LocationProfile:
    loc_type: str
    wall_tile: str  # attribute name on tile_types module
    floor_tile: str
    room_specs: list[RoomSpec] = field(default_factory=list)
    max_rooms: int = 12
    corridor_style: str = "straight"  # "straight" | "winding" | "open"
    generator: str = "standard"  # "standard" | "ship" | "organic" | "village"
    wall_interactable: str = "Mineral seam"  # name of wall-embedded interactable
    fully_lit: bool = False  # terrain always rendered lit; entities still need LOS
    fov_radius: int = 8  # vision range; larger in lit areas


PROFILES: dict[str, LocationProfile] = {
    "derelict": LocationProfile(
        loc_type="derelict",
        wall_tile="wall",
        floor_tile="floor",
        generator="ship",
        corridor_style="straight",
        max_rooms=10,
        wall_interactable="Locker",
        room_specs=[
            RoomSpec("bridge", 5, 8, 4, 6, required=True, max_count=1),
            RoomSpec("engine_room", 6, 9, 5, 7, required=True, max_count=1),
            RoomSpec("crew_quarters", 4, 7, 4, 6),
            RoomSpec("cargo", 5, 9, 4, 7),
        ],
    ),
    "asteroid": LocationProfile(
        loc_type="asteroid",
        wall_tile="rock_wall",
        floor_tile="rock_floor",
        generator="organic",
        corridor_style="winding",
        max_rooms=10,
        room_specs=[
            RoomSpec("cavern", 6, 12, 5, 10),
            RoomSpec("shaft", 3, 5, 6, 10),
            RoomSpec("alcove", 3, 5, 3, 5),
        ],
    ),
    "starbase": LocationProfile(
        loc_type="starbase",
        wall_tile="wall",
        floor_tile="floor",
        generator="standard",
        corridor_style="straight",
        max_rooms=12,
        wall_interactable="Locker",
        room_specs=[
            RoomSpec("trade_area", 7, 11, 6, 9, required=True, max_count=1),
            RoomSpec("dock", 6, 10, 5, 8, required=True, max_count=1),
            RoomSpec("control_room", 5, 8, 4, 7, required=True, max_count=1),
            RoomSpec("cargo", 5, 9, 4, 7),
        ],
    ),
    "colony": LocationProfile(
        loc_type="colony",
        wall_tile="structure_wall",
        floor_tile="dirt_floor",
        generator="village",
        corridor_style="open",
        max_rooms=12,
        wall_interactable="Storage cabinet",
        fully_lit=True,
        fov_radius=20,
        room_specs=[
            RoomSpec("meeting_hall", 8, 12, 7, 9, required=True, max_count=1),
            RoomSpec("trade_hall", 7, 10, 6, 8),
            RoomSpec("dining_hall", 7, 10, 6, 8),
            RoomSpec("residential", 5, 8, 5, 7),
        ],
    ),
}


def get_profile(loc_type: str) -> LocationProfile:
    """Look up a profile by loc_type, defaulting to derelict."""
    return PROFILES.get(loc_type, PROFILES["derelict"])
