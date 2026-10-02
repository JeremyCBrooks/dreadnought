"""Data-driven ship room dressing and corridor lighting."""

from __future__ import annotations

import random
from dataclasses import asdict

from data.hazards import HAZARDS
from data.items import all_loot
from game.entity import Entity
from world import tile_types
from world.dungeon_gen.rooms import RectRoom, _near_exit
from world.game_map import GameMap

_ROOM_DRESSING = {
    "bridge": {
        "decoration_count": (2, 4),
        "interactable_count": (1, 3),
        "loot_chance": 0.4,
        "hazard_chance": 0.1,
        "decorations": [
            (".", (80, 120, 180), "Seat"),
            ("*", (60, 180, 220), "Blinking Light"),
        ],
        "interactables": [
            ("&", (80, 200, 255), "Nav Terminal"),
            ("&", (100, 180, 220), "Comms Terminal"),
        ],
    },
    "engine_room": {
        "decoration_count": (2, 4),
        "interactable_count": (1, 3),
        "loot_chance": 0.3,
        "hazard_chance": 0.4,
        "decorations": [
            ("-", (120, 120, 140), "Piping"),
            ("*", (200, 180, 0), "Warning Light"),
            ("#", (100, 100, 120), "Machinery"),
        ],
        "interactables": [
            ("&", (100, 200, 255), "Engine Terminal"),
            ("v", (80, 180, 220), "Coolant Valve"),
        ],
    },
    "cargo": {
        "decoration_count": (1, 2),
        "interactable_count": (3, 6),
        "loot_chance": 0.3,
        "hazard_chance": 0.1,
        "decorations": [
            ("~", (140, 120, 80), "Cargo Net"),
        ],
        "interactables": [
            ("=", (180, 160, 100), "Crate"),
            ("=", (160, 180, 120), "Supply Crate"),
            ("[", (150, 160, 180), "Supply Locker"),
        ],
    },
    "crew_quarters": {
        "decoration_count": (2, 4),
        "interactable_count": (1, 2),
        "loot_chance": 0.4,
        "hazard_chance": 0.05,
        "decorations": [
            ("_", (120, 100, 80), "Bunk"),
            ("-", (100, 90, 70), "Footlocker"),
        ],
        "interactables": [
            ("[", (150, 160, 180), "Personal Locker"),
            ("&", (100, 180, 200), "Personal Terminal"),
        ],
    },
}


def _place_ship_corridor_lights(
    game_map: GameMap,
    spine_x1: int,
    spine_x2: int,
    spine_y: int,
    spine_y2: int,
    branches: list[tuple[int, int, int]],
    rng: random.Random,
    derelict: bool = False,
    rooms: list[RectRoom] | None = None,
) -> None:
    """Place warm white lights along spine and branch corridors.

    If *derelict*, only a random subset (1 to 50% of total) are placed,
    and 25-75% of those flicker.
    """
    color = (200, 190, 170)
    radius = 4
    intensity = 0.5
    spacing = rng.randint(6, 8)

    # Collect all candidate positions
    candidates: list[tuple[int, int]] = []
    for x in range(spine_x1, spine_x2 + 1, spacing):
        if game_map.in_bounds(x, spine_y):
            candidates.append((x, spine_y))
    for br_x, br_y_start, br_y_end in branches:
        for y in range(br_y_start, br_y_end + 1, spacing):
            if game_map.in_bounds(br_x, y):
                candidates.append((br_x, y))

    # Exclude positions inside bridge and engine room
    if rooms:
        fixture_rooms = [r for r in rooms if r.label in ("bridge", "engine_room")]

        def _in_fixture_room(x: int, y: int) -> bool:
            for r in fixture_rooms:
                if r.x1 <= x <= r.x2 and r.y1 <= y <= r.y2:
                    return True
            return False

        candidates = [(x, y) for x, y in candidates if not _in_fixture_room(x, y)]

    if derelict and len(candidates) > 1:
        min_lights = max(1, round(len(candidates) * 0.10))
        max_lights = max(min_lights, round(len(candidates) * 0.75))
        count = rng.randint(min_lights, max_lights)
        chosen = rng.sample(candidates, count)
        flicker_count = min(2, rng.randint(0, 2))
        rng.shuffle(chosen)
        for i, (x, y) in enumerate(chosen):
            game_map.add_light_source(
                x,
                y,
                radius=radius,
                color=color,
                intensity=intensity,
                flicker=(i < flicker_count),
            )
    else:
        for x, y in candidates:
            game_map.add_light_source(x, y, radius=radius, color=color, intensity=intensity)


def _dress_ship_room(
    room: RectRoom,
    game_map: GameMap,
    rng: random.Random,
    exit_pos: tuple[int, int] | None = None,
    has_nav_unit: bool = False,
) -> None:
    """Place themed decorations and interactables in a ship room."""
    dressing = _ROOM_DRESSING.get(room.label)
    if not dressing:
        return

    occupied: set[tuple[int, int]] = {(e.x, e.y) for e in game_map.entities}

    # Room fixture tiles — non-walkable light sources (placed first to block entity placement)
    cx, cy = room.center
    fixture_tile = None
    fixture_light = None
    if room.label == "engine_room":
        fixture_tile = tile_types.reactor_core
        fixture_light = {"radius": 7, "color": (120, 60, 220), "intensity": 0.9, "flicker": rng.random() < 0.05}
    elif room.label == "bridge":
        fixture_tile = tile_types.control_console
        fixture_light = {"radius": 5, "color": (80, 160, 255), "intensity": 0.7, "flicker": rng.random() < 0.05}

    if fixture_tile is not None:
        # Try center first, then offsets to avoid overwriting exit tile
        candidates = [(cx, cy)]
        for dist in range(1, 4):
            for dx in range(-dist, dist + 1):
                for dy in range(-dist, dist + 1):
                    if abs(dx) == dist or abs(dy) == dist:
                        candidates.append((cx + dx, cy + dy))
        for fx, fy in candidates:
            if (
                game_map.in_bounds(fx, fy)
                and game_map.tiles["walkable"][fx, fy]
                and (fx, fy) not in occupied
                and not _near_exit(fx, fy, exit_pos)
            ):
                game_map.tiles[fx, fy] = fixture_tile
                occupied.add((fx, fy))
                game_map.add_light_source(fx, fy, **fixture_light)
                break

    def _pick_floor_pos() -> tuple[int, int] | None:
        x_lo = max(room.x1 + 1, 0)
        x_hi = min(room.x2 - 1, game_map.width - 1)
        y_lo = max(room.y1 + 1, 0)
        y_hi = min(room.y2 - 1, game_map.height - 1)
        if x_lo > x_hi or y_lo > y_hi:
            return None
        for _ in range(10):
            x = rng.randint(x_lo, x_hi)
            y = rng.randint(y_lo, y_hi)
            if (x, y) not in occupied and game_map.tiles["walkable"][x, y] and not _near_exit(x, y, exit_pos):
                return x, y
        return None

    # Decorations — visual only, non-blocking, no interactable
    dec_min, dec_max = dressing["decoration_count"]
    for _ in range(rng.randint(dec_min, dec_max)):
        pos = _pick_floor_pos()
        if not pos:
            continue
        ch, color, name = rng.choice(dressing["decorations"])
        occupied.add(pos)
        game_map.entities.append(Entity(x=pos[0], y=pos[1], char=ch, color=color, name=name, blocks_movement=False))

    # Interactable furnishings
    int_min, int_max = dressing["interactable_count"]
    loot_chance = dressing["loot_chance"]
    hazard_chance = dressing["hazard_chance"]
    loot_pool = all_loot()
    hazard_pool = HAZARDS

    nav_placed = False
    for _ in range(rng.randint(int_min, int_max)):
        pos = _pick_floor_pos()
        if not pos:
            continue
        ch, color, name = rng.choice(dressing["interactables"])
        hazard = asdict(rng.choice(hazard_pool)) if rng.random() < hazard_chance else None
        if has_nav_unit and not nav_placed:
            loot = {"char": "\u2302", "color": [0, 255, 200], "name": "Navigation Unit", "type": "nav_unit", "value": 1}
            nav_placed = True
        else:
            loot = rng.choice(loot_pool) if rng.random() < loot_chance else None
        occupied.add(pos)
        game_map.entities.append(
            Entity(
                x=pos[0],
                y=pos[1],
                char=ch,
                color=color,
                name=name,
                blocks_movement=False,
                interactable={"kind": name.lower(), "hazard": hazard, "loot": loot},
            )
        )
