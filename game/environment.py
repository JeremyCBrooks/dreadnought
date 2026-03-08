"""Environment hazard system: per-turn resource drain and damage."""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

import numpy as np

from game.hazards import apply_hp_damage

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity
    from world.game_map import GameMap

# Environment types that modify gameplay but don't deal damage per tick.
NON_DAMAGING_HAZARDS = {"low_gravity"}

# Hazards that apply globally (not per-tile).
GLOBAL_HAZARDS = {"low_gravity"}

# Hazards that are purely spatial: they ONLY apply where an overlay marks
# affected tiles.  If the overlay doesn't exist (no active sources) the
# hazard has no effect — it never falls back to global application.
SPATIAL_HAZARDS = {"vacuum"}


def has_low_gravity(engine: Engine) -> bool:
    """Return True if the current environment has active low gravity."""
    env = getattr(engine, "environment", None)
    if not env:
        return False
    return env.get("low_gravity", 0) > 0


def _flood_fill_hazard(
    game_map: GameMap,
    sources: list[tuple[int, int]],
) -> np.ndarray:
    """BFS flood fill from *sources* through walkable tiles (4-cardinal).

    Returns a bool array (width, height) marking all reachable tiles.
    Blocked by non-walkable tiles (walls, closed doors).
    """
    result = np.full((game_map.width, game_map.height), fill_value=False, order="F")
    queue: deque[tuple[int, int]] = deque()

    for x, y in sources:
        if game_map.in_bounds(x, y):
            result[x, y] = True
            queue.append((x, y))

    while queue:
        cx, cy = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not game_map.in_bounds(nx, ny):
                continue
            if result[nx, ny]:
                continue
            if not game_map.tiles["walkable"][nx, ny]:
                continue
            result[nx, ny] = True
            queue.append((nx, ny))

    return result


# ---------------------------------------------------------------------------
# Explosive decompression
# ---------------------------------------------------------------------------

DECOMPRESSION_RANGE = 10
DECOMPRESSION_TILES_PER_STEP = 3


def _bfs_toward_breach(
    game_map: GameMap,
    sources: list[tuple[int, int]],
    max_distance: int | None = None,
) -> tuple[dict[tuple[int, int], tuple[int, int]], dict[tuple[int, int], int]]:
    """BFS from breach *sources*, returning pull-direction and distance for each
    reachable tile.

    Returns ``(pull_dirs, distances)`` where:
    - ``pull_dirs``: ``{(x, y): (dx, dy)}`` direction to move toward nearest
      breach source (following walkable corridors).
    - ``distances``: ``{(x, y): int}`` BFS distance from nearest breach source.
    """
    parent: dict[tuple[int, int], tuple[int, int] | None] = {}
    dist: dict[tuple[int, int], int] = {}
    queue: deque[tuple[int, int]] = deque()

    for sx, sy in sources:
        if game_map.in_bounds(sx, sy):
            parent[(sx, sy)] = None
            dist[(sx, sy)] = 0
            queue.append((sx, sy))

    while queue:
        cx, cy = queue.popleft()
        d = dist[(cx, cy)]
        if max_distance is not None and d >= max_distance:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not game_map.in_bounds(nx, ny):
                continue
            if (nx, ny) in dist:
                continue
            if not game_map.tiles["walkable"][nx, ny]:
                continue
            parent[(nx, ny)] = (cx, cy)
            dist[(nx, ny)] = d + 1
            queue.append((nx, ny))

    # Build pull-direction map: for each tile, trace parent chain back one step
    # to find the direction toward the breach.
    pull_dirs: dict[tuple[int, int], tuple[int, int]] = {}
    for pos in parent:
        if parent[pos] is None:
            # Source tile — pull direction doesn't matter (entity is at breach)
            pull_dirs[pos] = (0, 0)
            continue
        p = parent[pos]
        pull_dirs[pos] = (p[0] - pos[0], p[1] - pos[1])

    return pull_dirs, dist


def _find_pressure_boundary(
    game_map: GameMap,
    newly_exposed: np.ndarray,
    vacuum_overlay: np.ndarray | None,
) -> list[tuple[int, int]]:
    """Find tiles at the pressure boundary: newly-exposed tiles adjacent to
    old vacuum (the opening where air starts rushing through)."""
    if vacuum_overlay is None:
        return []

    old_vacuum = vacuum_overlay & ~newly_exposed
    boundary: list[tuple[int, int]] = []
    xs, ys = np.where(newly_exposed)
    for i in range(len(xs)):
        x, y = int(xs[i]), int(ys[i])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if game_map.in_bounds(nx, ny) and old_vacuum[nx, ny]:
                boundary.append((x, y))
                break
    return boundary


def _bfs_decompression_reach(
    game_map: GameMap,
    boundary: list[tuple[int, int]],
    old_vacuum: np.ndarray,
    max_distance: int = DECOMPRESSION_RANGE,
) -> dict[tuple[int, int], int]:
    """BFS from pressure boundary into the pressurized side.

    Returns ``{(x, y): distance}`` for tiles within *max_distance* of the
    boundary, excluding tiles that were already vacuum.
    """
    dist: dict[tuple[int, int], int] = {}
    queue: deque[tuple[int, int]] = deque()
    for bx, by in boundary:
        if (bx, by) not in dist:
            dist[(bx, by)] = 0
            queue.append((bx, by))

    while queue:
        cx, cy = queue.popleft()
        d = dist[(cx, cy)]
        if d >= max_distance:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not game_map.in_bounds(nx, ny):
                continue
            if (nx, ny) in dist:
                continue
            if not game_map.tiles["walkable"][nx, ny]:
                continue
            # Don't expand into old vacuum (already depressurized)
            if old_vacuum[nx, ny]:
                continue
            dist[(nx, ny)] = d + 1
            queue.append((nx, ny))
    return dist


def trigger_decompression(
    engine: Engine,
    breach_sources: list[tuple[int, int]],
    newly_exposed: np.ndarray,
) -> dict[tuple[int, int], tuple[int, int]]:
    """Tag entities in decompression range for pull toward breach.

    Air flows from the pressurized side through the opening (pressure
    boundary) across the vacuum area and out the breach.  Range is measured
    from the **opening**, not the breach — an entity 3 tiles from a door is
    affected even if the breach is 20 tiles away on the far side.

    Returns the pull-direction map so callers can store it for subsequent
    ``process_decompression_step`` calls.
    """
    game_map = engine.game_map
    vacuum_overlay = game_map.hazard_overlays.get("vacuum")

    # Pull directions: unlimited BFS from breach through all walkable tiles
    pull_dirs, breach_dist = _bfs_toward_breach(game_map, breach_sources)

    # Range limiting: BFS from pressure boundary into pressurized side
    boundary = _find_pressure_boundary(game_map, newly_exposed, vacuum_overlay)
    old_vacuum = (vacuum_overlay & ~newly_exposed) if vacuum_overlay is not None else None
    if old_vacuum is not None and boundary:
        reach = _bfs_decompression_reach(game_map, boundary, old_vacuum)
    else:
        # No pressure boundary (direct opening to space, or first event).
        # Fall back to range from breach source.
        reach = {
            pos: d for pos, d in breach_dist.items()
            if d <= DECOMPRESSION_RANGE
        }

    tagged = 0
    for entity in list(game_map.entities):
        # Skip interactables (consoles, switches, etc.)
        if entity.interactable:
            continue
        # Must be a fighter or loose item
        if not entity.fighter and not entity.item:
            continue
        # Skip entities already in vacuum (no pressure differential)
        if (vacuum_overlay is not None
                and vacuum_overlay[entity.x, entity.y]
                and not newly_exposed[entity.x, entity.y]):
            continue
        pos = (entity.x, entity.y)
        # Must be within decompression range of the pressure boundary
        if pos not in reach:
            continue
        # Must have a valid pull direction toward breach
        if pos not in pull_dirs or pull_dirs[pos] == (0, 0):
            continue

        # Enough moves to reach breach + 1 to exit into space
        entity.decompression_moves = min(breach_dist.get(pos, 0) + 1, DECOMPRESSION_RANGE)
        entity.decompression_direction = pull_dirs[pos]
        tagged += 1

    if tagged:
        engine.message_log.add_message(
            "EXPLOSIVE DECOMPRESSION!", (255, 50, 50),
        )
    return pull_dirs


def process_decompression_step(
    game_map: GameMap,
    entity: Entity,
    pull_directions: dict[tuple[int, int], tuple[int, int]],
) -> None:
    """Move *entity* up to DECOMPRESSION_TILES_PER_STEP tiles toward breach."""
    from world import tile_types

    space_tid = int(tile_types.space["tile_id"])

    for _ in range(DECOMPRESSION_TILES_PER_STEP):
        if entity.decompression_moves <= 0:
            break

        pos = (entity.x, entity.y)
        direction = pull_directions.get(pos, entity.decompression_direction)
        if direction == (0, 0):
            # At breach source — find adjacent space tile to blow entity out
            for adx, ady in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ax, ay = entity.x + adx, entity.y + ady
                if (game_map.in_bounds(ax, ay)
                        and game_map.tiles["tile_id"][ax, ay] == space_tid):
                    direction = (adx, ady)
                    break
            else:
                direction = entity.decompression_direction
        if direction == (0, 0):
            entity.decompression_moves = 0
            break

        dx, dy = direction
        nx, ny = entity.x + dx, entity.y + dy

        # Check bounds first
        if not game_map.in_bounds(nx, ny):
            # Impact: 1 HP per remaining move
            if entity.fighter:
                apply_hp_damage(entity.fighter, entity.decompression_moves)
            entity.decompression_moves = 0
            continue

        # Allow decompression to blow entity into space
        if game_map.tiles["tile_id"][nx, ny] == space_tid:
            entity.x = nx
            entity.y = ny
            entity.drifting = True
            entity.drift_direction = direction
            entity.decompression_moves = 0
            game_map.invalidate_entity_index()
            break

        if not game_map.tiles["walkable"][nx, ny]:
            # Try perpendicular slide
            slid = False
            for sdx, sdy in ((dy, dx), (-dy, -dx)):
                snx, sny = entity.x + sdx, entity.y + sdy
                if (game_map.in_bounds(snx, sny)
                        and game_map.tiles["walkable"][snx, sny]
                        and not game_map.get_blocking_entity(snx, sny)):
                    entity.x = snx
                    entity.y = sny
                    entity.decompression_moves -= 1
                    game_map.invalidate_entity_index()
                    slid = True
                    break
            if not slid:
                # Impact: 1 HP per remaining move
                if entity.fighter:
                    apply_hp_damage(entity.fighter, entity.decompression_moves)
                entity.decompression_moves = 0
            continue

        # Check for blocking entity
        blocker = game_map.get_blocking_entity(nx, ny)
        if blocker and blocker is not entity:
            if entity.fighter:
                apply_hp_damage(entity.fighter, entity.decompression_moves)
            entity.decompression_moves = 0
            break

        # Move
        entity.x = nx
        entity.y = ny
        entity.decompression_moves -= 1
        game_map.invalidate_entity_index()


def apply_environment_tick(engine: Engine) -> None:
    """Apply one turn of environment effects to the player.

    Per-tile hazards (e.g. vacuum) only affect the player if the overlay
    marks their position.  Global hazards (e.g. low_gravity) always apply.
    """
    if not engine.player or not engine.player.fighter:
        return
    env = engine.environment
    suit = engine.suit
    if not env or not suit:
        return

    # Ensure overlays are up-to-date
    engine.game_map.recalculate_hazards()

    px, py = engine.player.x, engine.player.y

    import debug

    for hazard_type, severity in env.items():
        if hazard_type in NON_DAMAGING_HAZARDS:
            continue
        if severity <= 0:
            continue

        # Per-tile check: skip if player not on affected tile
        if hazard_type not in GLOBAL_HAZARDS:
            overlay = engine.game_map.hazard_overlays.get(hazard_type)
            if overlay is not None and not overlay[px, py]:
                continue
            # Spatial hazards require an overlay; no overlay = no effect.
            if overlay is None and hazard_type in SPATIAL_HAZARDS:
                continue

        max_turns = suit.resistances.get(hazard_type, 0)
        current = suit.current_pools.get(hazard_type, 0)

        if max_turns > 0 and current > 0:
            if not debug.DISABLE_OXYGEN:
                ticks = suit._drain_ticks.get(hazard_type, 0) + 1
                if ticks >= suit.DRAIN_INTERVAL:
                    suit.current_pools[hazard_type] = current - 1
                    ticks = 0
                suit._drain_ticks[hazard_type] = ticks
            continue
        # No resistance or pool depleted: deal 1 HP per turn
        if debug.GOD_MODE:
            continue
        apply_hp_damage(engine.player.fighter, 1)
        engine.message_log.add_message(
            f"WARNING: {hazard_type.replace('_', ' ').title()}! Taking damage!",
            (255, 100, 100),
        )


def apply_environment_tick_entity(engine: Engine, entity: Entity) -> None:
    """Apply per-tile hazard damage to a non-player entity (enemies have no suit).

    Non-organic entities (bots, drones) are immune to vacuum.
    """
    if not entity.fighter or entity.fighter.hp <= 0:
        return
    if entity is engine.player:
        return

    env = engine.environment
    if not env:
        return

    engine.game_map.recalculate_hazards()
    ex, ey = entity.x, entity.y

    for hazard_type, severity in env.items():
        if hazard_type in NON_DAMAGING_HAZARDS:
            continue
        if severity <= 0:
            continue

        # Non-organic entities are immune to vacuum
        if hazard_type == "vacuum" and not entity.organic:
            continue

        # Per-tile check
        if hazard_type not in GLOBAL_HAZARDS:
            overlay = engine.game_map.hazard_overlays.get(hazard_type)
            if overlay is not None and not overlay[ex, ey]:
                continue
            if overlay is None and hazard_type in SPATIAL_HAZARDS:
                continue

        apply_hp_damage(entity.fighter, 1)

    if entity.fighter.hp <= 0:
        engine.message_log.add_message(
            f"The {entity.name} succumbs to the environment!", (200, 200, 200)
        )
        if entity in engine.game_map.entities:
            engine.game_map.entities.remove(entity)
