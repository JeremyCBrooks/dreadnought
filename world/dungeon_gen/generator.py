"""Public entry points: generate_dungeon, generate_player_ship, respawn_creatures."""

from __future__ import annotations

import random

import numpy as np

from world import tile_types
from world.dungeon_gen.basic_layouts import _generate_fallback, _generate_organic, _generate_standard
from world.dungeon_gen.cosmetics import _apply_ship_cosmetics
from world.dungeon_gen.doors import _place_doors
from world.dungeon_gen.hull import (
    _convert_hull_to_space,
    _enforce_airlock_walls,
    _place_airlocks,
    _place_asteroid_breaches,
    _place_hull_breaches,
    hull_breach_candidates,
)
from world.dungeon_gen.rooms import RectRoom, _resolve_tile
from world.dungeon_gen.ship_layout import _generate_ship
from world.dungeon_gen.spawning import MAX_ENEMIES_PER_LEVEL, _spawn_enemies, _spawn_interactables, _spawn_items
from world.dungeon_gen.village import _generate_village
from world.game_map import GameMap
from world.loc_profiles import LocationProfile, get_profile

_GENERATORS = {
    "ship": _generate_ship,
    "organic": _generate_organic,
    "standard": _generate_standard,
    "village": _generate_village,
}


def _rolls_hull_breach(profile: LocationProfile, rng: random.Random) -> bool:
    """Whether this hulled map gets breaches. Draws only when the chance is genuinely uncertain."""
    if profile.hull_breach_chance >= 1.0:
        return True
    return profile.hull_breach_chance > 0.0 and rng.random() < profile.hull_breach_chance


def generate_dungeon(
    width: int = 80,
    height: int = 45,
    max_rooms: int = 12,
    room_min: int = 4,
    room_max: int = 10,
    seed: int | None = None,
    max_enemies: int = 2,
    max_items: int = 1,
    loc_type: str = "derelict",
    max_total_enemies: int = MAX_ENEMIES_PER_LEVEL,
    has_nav_unit: bool = False,
    player_ship: bool = False,
    depth: int = 0,
    community: str | None = None,
) -> tuple[GameMap, list[RectRoom], tuple[int, int] | None]:
    """Returns (game_map, rooms, exit_pos).

    The place is home to one *community* of *loc_type* (picked from the seed
    when not given). Creatures draw from their own random stream, so the same
    seed always builds the same place whatever lives in it.
    """
    rng = random.Random(seed)
    creature_rng = _creature_rng(seed)
    profile = get_profile(loc_type)
    wall_tile = _resolve_tile(profile.wall_tile)
    floor_tile = _resolve_tile(profile.floor_tile)

    game_map = GameMap(width, height, fill_tile=wall_tile)
    game_map.fully_lit = profile.fully_lit
    game_map.fov_radius = profile.fov_radius
    from debug import VISIBLE_ALL

    game_map.debug_visible_all = VISIBLE_ALL
    gen_fn = _GENERATORS.get(profile.generator)
    if gen_fn:
        rooms = gen_fn(game_map, rng, profile, wall_tile, floor_tile, has_nav_unit=has_nav_unit)
    else:
        rooms = _generate_fallback(
            game_map,
            rng,
            max_rooms,
            room_min,
            room_max,
            floor_tile,
        )

    # Place doors at room entrances (skip organic/cave layouts)
    if rooms and profile.places_doors:
        _place_doors(game_map, rng, floor_tile, rooms)

    # Exit hatch at entrance so the player can always leave from where they entered.
    exit_pos: tuple[int, int] | None = None
    if rooms:
        exit_pos = rooms[0].center
        if game_map.in_bounds(exit_pos[0], exit_pos[1]):
            game_map.tiles[exit_pos[0], exit_pos[1]] = tile_types.exit_tile

    if not player_ship:
        for room in rooms[1:]:
            _spawn_items(room, game_map, rng, max_items, exit_pos=exit_pos)

    # 1–3 interactables in random rooms. Ship rooms already have themed
    # dressing, so ships only get these when the profile has a wall
    # interactable and there is a room besides the entrance. The guard must
    # stay ahead of the randint: skipping it must not consume a draw.
    wants_interactables = not profile.themed_dressing or (profile.wall_interactable and len(rooms) > 1)
    if rooms and wants_interactables:
        for _ in range(rng.randint(1, 3)):
            room = rng.choice(rooms[1:]) if len(rooms) > 1 else rooms[0]
            _spawn_interactables(
                room,
                game_map,
                rng,
                count=1,
                hazard_chance=0.2,
                wall_interactable_name=profile.wall_interactable,
                exit_pos=exit_pos,
            )

    # Place airlocks before hull conversion (need wall tiles to identify hull)
    if profile.has_hull:
        _place_airlocks(game_map, rng, rooms, wall_tile, floor_tile)

        # Convert outer hull walls to space tiles for ship/starbase maps
        _convert_hull_to_space(game_map, wall_tile)
        game_map.has_space = True
        # Ensure space beyond airlock exterior doors
        for al in game_map.airlocks:
            ex, ey = al["exterior_door"]
            dx, dy = al["direction"]
            bx, by = ex + dx, ey + dy
            if game_map.in_bounds(bx, by):
                game_map.tiles[bx, by] = tile_types.space
        # Re-enforce walls around airlock corridors (hull cleanup may
        # have converted them to space, creating diagonal gaps).
        _enforce_airlock_walls(game_map, wall_tile)
        # Hull breaches - starbases only have a 20% chance; player ship never has breaches
        if not player_ship and _rolls_hull_breach(profile, rng):
            _place_hull_breaches(game_map, rng, wall_tile)

    # Hull breaches for asteroid/organic maps
    if profile.rock_breaches:
        _place_asteroid_breaches(game_map, rng)

    # Cosmetic variation for ship and starbase maps
    if profile.has_hull:
        _apply_ship_cosmetics(game_map, rng, wall_tile, floor_tile)

    if player_ship:
        # Strip any loot items placed by room dressing (loot_chance dressing paths)
        game_map.entities = [e for e in game_map.entities if e.item is None]
    else:
        # Last, so the place is finished before anything moves in: what
        # lives here never changes how it is built.
        _populate_rooms(
            game_map, rooms[1:], creature_rng, max_enemies, max_total_enemies, exit_pos, loc_type, depth, community
        )

    game_map.invalidate_hazards()
    return game_map, rooms, exit_pos


# The derelict profile uses the "ship" generator - correct layout for a vessel.
_PLAYER_SHIP_LOC_TYPE = "derelict"


def generate_player_ship(
    seed: int,
    width: int = 80,
    height: int = 45,
) -> tuple[GameMap, list[RectRoom], tuple[int, int] | None]:
    """Generate the player's ship interior once at world creation.

    No enemies, no free-standing item pickups, no hull breaches. Interactable
    furnishings (lockers, consoles) are preserved. The reactor core tile is
    present in the engine_room - it is the ship's own power core and
    TacticalState blocks extracting it in explore_ship mode.
    """
    return generate_dungeon(
        width=width,
        height=height,
        max_enemies=0,
        max_items=0,
        seed=seed,
        loc_type=_PLAYER_SHIP_LOC_TYPE,
        player_ship=True,
    )


def player_ship_hull_tile() -> np.ndarray:
    """The tile the player ship's hull is built from (and patched with)."""
    return _resolve_tile(get_profile(_PLAYER_SHIP_LOC_TYPE).wall_tile)


def player_ship_breach_candidates(game_map: GameMap) -> list[tuple[int, int]]:
    """Outer-hull tiles of a player ship where damage could open a breach.

    Airlock chambers are spared: a holed chamber would vent the docking
    corridor of the next boarding instead of the ship.
    """
    return hull_breach_candidates(game_map, player_ship_hull_tile(), airlock_chambers=False)


def _creature_rng(seed: int | None) -> random.Random:
    """The random stream creatures are drawn from, kept apart from the layout's."""
    return random.Random(f"creatures:{seed}" if seed is not None else None)


def respawn_creatures(
    game_map: GameMap,
    rooms: list[RectRoom],
    max_enemies: int = 2,
    seed: int | None = None,
    max_total_enemies: int = MAX_ENEMIES_PER_LEVEL,
    loc_type: str = "derelict",
    depth: int = 0,
    community: str | None = None,
) -> None:
    """Remove all entities with AI (creatures) and spawn new ones in rooms[1:].
    Does not touch items or the map. Uses seed for deterministic placement if given.
    """
    game_map.entities[:] = [e for e in game_map.entities if not e.ai]
    _populate_rooms(
        game_map, rooms[1:], random.Random(seed), max_enemies, max_total_enemies, None, loc_type, depth, community
    )


def _populate_rooms(
    game_map: GameMap,
    rooms: list[RectRoom],
    rng: random.Random,
    max_enemies: int,
    max_total_enemies: int,
    exit_pos: tuple[int, int] | None,
    loc_type: str,
    depth: int,
    community: str | None = None,
) -> None:
    """Fill *rooms* with one community of *loc_type* at *depth*, up to the level cap.

    Every creature in a place comes from the same community, so they make
    sense together; *community* names it, otherwise one is drawn from *rng*.
    """
    from data.enemies import community_named, pick_community

    chosen = community_named(community) if community else pick_community(loc_type, rng)
    pool = chosen.creatures(depth) if chosen else []
    total_spawned = 0
    for room in rooms:
        remaining = max_total_enemies - total_spawned
        if remaining <= 0:
            break
        total_spawned += _spawn_enemies(
            room,
            game_map,
            rng,
            max_enemies,
            exit_pos=exit_pos,
            remaining=remaining,
            pool=pool,
        )
