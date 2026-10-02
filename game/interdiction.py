"""Ship interdiction: pirate boarding ship attaches to player ship on system arrival.

When triggered, a full-size procgen pirate ship docks at one of the player
ship's airlocks via an airtight corridor. Both ships live in a *composite*
GameMap that replaces ``engine.ship.game_map`` for the duration of the
encounter. The original player ship map is preserved on the ``Interdiction``
and restored after the encounter resolves (deferred to the player's next
ship-exit/entry to avoid stranding them on a removed tile).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from game.entity import Entity


# Probability of triggering on a non-home, non-empty-cargo system arrival.
# Tunable; revisit during playtest.
INTERDICTION_CHANCE: float = 1.0

MIN_PIRATES = 1
MAX_PIRATES = 4


@dataclass
class Interdiction:
    """State of a single interdiction event in a star system.

    Lifecycle:
      * Queued (created by ``arrive_at``): ``started=False``, ``resolved=False``.
      * Started (player entered ship; composite map active, pirates spawned):
        ``started=True``, ``resolved=False``.
      * Resolved (all pirates dead OR drift escape): ``resolved=True``.
        Map restoration is deferred until the player next enters/exits the ship.
    """

    started: bool = False
    resolved: bool = False
    pirate_entities: list[Entity] = field(default_factory=list)
    # --- Composite layout ---
    pirate_ship_seed: int | None = None
    player_offset: tuple[int, int] | None = None
    pirate_offset: tuple[int, int] | None = None
    # interior_door positions of the two airlocks used (composite coords).
    # Persisted so we can rebuild the same composite on save/load.
    player_airlock_interior: tuple[int, int] | None = None
    pirate_airlock_interior: tuple[int, int] | None = None
    # --- Convenience refs (not strictly needed for save/load) ---
    craft_room: Any | None = None  # spawn room (RectRoom in composite coords)
    connector_tiles: list[tuple[int, int]] = field(default_factory=list)
    attach_pos: tuple[int, int] | None = None  # player exterior_door in composite
    attach_direction: tuple[int, int] | None = None  # outward direction
    # --- Restoration ---
    original_ship_map: Any | None = None  # GameMap; restored after resolve
    original_exit_pos: tuple[int, int] | None = None
    original_rooms: list | None = None  # ship.rooms in native coords
    composite_map: Any | None = None  # GameMap; transient (active engine.ship.game_map)
    # --- Tile persistence ---
    # tile_ids of the freshly composed map; diffed against the live composite
    # to find tiles the player changed (extracted cores, opened doors).
    pristine_tile_ids: Any | None = None
    # (x, y, tile_id) changes loaded from a save, awaiting rebuild_composite.
    saved_tile_changes: list[tuple[int, int, int]] = field(default_factory=list)
    # Indices into pirate_entities_overlay of furnishings the player already
    # searched, loaded from a save and awaiting rebuild_composite.
    saved_consumed_overlay: list[int] = field(default_factory=list)
    # Pirate-side entities and light_sources that were appended to the shared
    # player_map lists in compose_ships; removed from those lists on resolve.
    pirate_entities_overlay: list[Any] = field(default_factory=list)
    pirate_light_sources_overlay: list[Any] = field(default_factory=list)

    def alive_pirate_count(self) -> int:
        """Count pirate entities whose Fighter still has HP > 0."""
        return sum(1 for p in self.pirate_entities if p.fighter is not None and p.fighter.hp > 0)

    def tile_changes(self) -> list[tuple[int, int, int]]:
        """Composite tiles that differ from the freshly composed map, as (x, y, tile_id).

        The composite itself is never serialized; these changes are what a
        save must carry so a rebuilt composite doesn't undo the player's work.
        """
        if self.composite_map is None or self.pristine_tile_ids is None:
            return list(self.saved_tile_changes)
        current = self.composite_map.tiles["tile_id"]
        xs, ys = (current != self.pristine_tile_ids).nonzero()
        return [(x, y, int(current[x, y])) for x, y in zip(xs.tolist(), ys.tolist(), strict=True)]

    def consumed_overlay_indices(self) -> list[int]:
        """Indices of pirate-ship furnishings that are no longer on the composite.

        Furnishings regenerate in the same order from ``pirate_ship_seed``, so
        the index identifies one across a save/load rebuild.
        """
        if self.composite_map is None:
            return list(self.saved_consumed_overlay)
        from game.helpers import missing_entity_indices

        return missing_entity_indices(self.pirate_entities_overlay, self.composite_map)

    def resolve(self) -> None:
        """Mark resolved. The actual ship-map restoration is deferred to the
        player's next ship-entry/exit so they don't get teleported off a tile
        that's about to vanish.
        """
        self.resolved = True


def should_attempt_interdiction(system, ship, galaxy, rng) -> bool:
    """Return True if a fresh interdiction should be queued on *system*.

    Skip when:
      * the system is the home system,
      * the player ship's cargo is empty (no incentive for pirates),
      * the system already has any interdiction (queued, active, or resolved).

    Otherwise roll against ``INTERDICTION_CHANCE``.
    """
    if system.interdiction is not None:
        return False
    if not ship.cargo:
        return False
    if system.name == galaxy.home_system:
        return False
    return rng.random() < INTERDICTION_CHANCE


# ---------------------------------------------------------------------------
# Pirate spawning
# ---------------------------------------------------------------------------


def _pirate_definitions() -> list:
    """All enemy defs eligible to crew a boarding ship (any pirate variant)."""
    from data.enemies import ENEMIES

    return [d for d in ENEMIES if getattr(d, "can_steal", False)]


def _spawn_pirates_in_room(craft_room, game_map, rng, count) -> list:
    """Build *count* pirate Entities placed at distinct walkable tiles inside *craft_room*."""
    from data.enemies import build_enemy_inventory
    from game.ai import CreatureAI
    from game.entity import Entity, Fighter
    from game.helpers import recalc_melee_power_ai

    defns = _pirate_definitions()
    if not defns:
        return []

    interior_tiles = [
        (x, y)
        for x in range(craft_room.x1 + 1, craft_room.x2)
        for y in range(craft_room.y1 + 1, craft_room.y2)
        if game_map.in_bounds(x, y) and bool(game_map.tiles["walkable"][x, y])
    ]
    if not interior_tiles:
        return []

    count = min(count, len(interior_tiles))
    positions = rng.sample(interior_tiles, count)

    pirates: list[Entity] = []
    for x, y in positions:
        defn = rng.choice(defns)
        entity = Entity(
            x=x,
            y=y,
            char=defn.char,
            color=defn.color,
            name=defn.name,
            blocks_movement=True,
            fighter=Fighter(hp=defn.hp, max_hp=defn.hp, defense=defn.defense, power=defn.power),
            ai=CreatureAI(),
            organic=defn.organic,
            gore_color=defn.gore_color,
        )
        entity.ai_config = defn.to_ai_config()
        entity.ai_state = entity.ai_config.get("ai_initial_state", "wandering")
        entity.inventory = build_enemy_inventory(defn, rng)
        entity.max_inventory = defn.max_inventory
        recalc_melee_power_ai(entity)
        pirates.append(entity)
    return pirates


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def _apply_layout(interdiction: Interdiction, layout, ship) -> None:
    """Save a CompositeLayout onto the interdiction + swap engine.ship.game_map."""
    interdiction.original_ship_map = ship.game_map
    interdiction.original_exit_pos = ship.exit_pos
    interdiction.original_rooms = ship.rooms
    interdiction.composite_map = layout.composite_map
    interdiction.pristine_tile_ids = layout.composite_map.tiles["tile_id"].copy()
    interdiction.player_offset = layout.player_offset
    interdiction.pirate_offset = layout.pirate_offset
    interdiction.craft_room = layout.spawn_room
    interdiction.connector_tiles = list(layout.corridor_tiles)
    interdiction.attach_pos = layout.player_airlock_pos
    interdiction.attach_direction = layout.direction

    # Track pirate-side entities/light_sources that were appended to the shared
    # player_map lists, so we can remove them on resolve.
    interdiction.pirate_entities_overlay = list(layout.pirate_entities_overlay or [])
    interdiction.pirate_light_sources_overlay = list(layout.pirate_light_sources_overlay or [])

    # Swap engine.ship.game_map to the composite. Translate exit_pos and rooms
    # by the player_offset so the docking hatch and cargo hold still resolve
    # correctly.
    ship.game_map = layout.composite_map
    if ship.rooms:
        ship.rooms = [room.translated(*layout.player_offset) for room in ship.rooms]
    if ship.exit_pos is not None:
        ship.exit_pos = (
            ship.exit_pos[0] + layout.player_offset[0],
            ship.exit_pos[1] + layout.player_offset[1],
        )


def _airlock_with_interior(airlocks: list[dict], interior_pos: tuple[int, int]) -> dict | None:
    for a in airlocks:
        if tuple(a.get("interior_door")) == tuple(interior_pos):
            return a
    return None


def start_interdiction(interdiction: Interdiction, ship, rng) -> None:
    """Generate a pirate ship, compose with the player ship, spawn pirates.

    Mutates *interdiction* in place. Replaces ``ship.game_map`` with the
    composite map (the original is preserved on ``interdiction.original_ship_map``).

    If no facing-airlock pair exists between the two ships, marks the
    interdiction silently resolved (no encounter).
    """
    from world.boarding_craft import compose_ships, find_compatible_airlock_pair
    from world.boarding_ship import generate_pirate_ship

    # Try several pirate-ship seeds until we find one whose airlocks face the
    # player's AND whose layout admits an airtight corridor through space.
    pirate_seed = None
    p_airlock = None
    r_airlock = None
    layout = None
    for _attempt in range(16):
        candidate_seed = rng.randint(0, 2**32 - 1)
        candidate_map, candidate_rooms, _ = generate_pirate_ship(candidate_seed)
        candidate_pair = find_compatible_airlock_pair(
            ship.game_map.airlocks, candidate_map.airlocks, ship.exit_pos, rng
        )
        if candidate_pair is None:
            continue
        candidate_layout = compose_ships(
            ship.game_map, candidate_map, candidate_rooms, candidate_pair[0], candidate_pair[1]
        )
        if candidate_layout is None:
            continue  # corridor couldn't route through space; try another seed
        pirate_seed = candidate_seed
        p_airlock, r_airlock = candidate_pair
        layout = candidate_layout
        break
    if layout is None:
        interdiction.resolved = True
        return
    _apply_layout(interdiction, layout, ship)
    interdiction.pirate_ship_seed = pirate_seed
    interdiction.player_airlock_interior = (
        layout.player_offset[0] + p_airlock["interior_door"][0],
        layout.player_offset[1] + p_airlock["interior_door"][1],
    )
    interdiction.pirate_airlock_interior = (
        layout.pirate_offset[0] + r_airlock["interior_door"][0],
        layout.pirate_offset[1] + r_airlock["interior_door"][1],
    )

    count = rng.randint(MIN_PIRATES, MAX_PIRATES)
    interdiction.pirate_entities = _spawn_pirates_in_room(layout.spawn_room, layout.composite_map, rng, count)
    interdiction.started = True


def rebuild_composite(interdiction: Interdiction, ship) -> bool:
    """Recreate the composite map from saved seed + airlock positions.

    Used at save-load time: ``ship.game_map`` has been regenerated from the
    galaxy seed (= original player ship), and we need to re-apply the
    boarding-ship overlay without re-spawning pirates.

    Returns True on success; False if the layout could not be recreated
    (treated as a silent resolution).
    """
    from world.boarding_craft import compose_ships
    from world.boarding_ship import generate_pirate_ship

    if interdiction.pirate_ship_seed is None:
        return False
    pirate_map, pirate_rooms, _ = generate_pirate_ship(interdiction.pirate_ship_seed)

    # Translate saved interior-door positions back to native (un-offset) coords.
    if interdiction.player_offset is None or interdiction.pirate_offset is None:
        return False
    native_player_int = (
        interdiction.player_airlock_interior[0] - interdiction.player_offset[0],
        interdiction.player_airlock_interior[1] - interdiction.player_offset[1],
    )
    native_pirate_int = (
        interdiction.pirate_airlock_interior[0] - interdiction.pirate_offset[0],
        interdiction.pirate_airlock_interior[1] - interdiction.pirate_offset[1],
    )
    p_airlock = _airlock_with_interior(ship.game_map.airlocks, native_player_int)
    r_airlock = _airlock_with_interior(pirate_map.airlocks, native_pirate_int)
    if p_airlock is None or r_airlock is None:
        return False

    layout = compose_ships(ship.game_map, pirate_map, pirate_rooms, p_airlock, r_airlock)
    if layout is None:
        return False
    _apply_layout(interdiction, layout, ship)
    _reapply_tile_changes(interdiction)
    _reapply_consumed_overlay(interdiction)
    return True


def _reapply_consumed_overlay(interdiction: Interdiction) -> None:
    """Take already-searched pirate furnishings back off a freshly rebuilt composite."""
    from game.helpers import remove_entities_at_indices

    remove_entities_at_indices(
        interdiction.pirate_entities_overlay, interdiction.saved_consumed_overlay, interdiction.composite_map
    )
    interdiction.saved_consumed_overlay = []


def _reapply_tile_changes(interdiction: Interdiction) -> None:
    """Replay saved tile changes onto a freshly rebuilt composite."""
    from world import tile_types

    composite = interdiction.composite_map
    core_tid = int(tile_types.reactor_core["tile_id"])
    extracted_cores: set[tuple[int, int]] = set()
    for x, y, tile_id in interdiction.saved_tile_changes:
        if not composite.in_bounds(x, y):
            continue
        if int(composite.tiles["tile_id"][x, y]) == core_tid:
            extracted_cores.add((x, y))
        composite.tiles[x, y] = tile_types.tile_by_id(tile_id)
    interdiction.saved_tile_changes = []
    # An extracted core takes its glow with it (see TakeReactorCoreAction).
    # Mutate in place: the list is shared with the original player map.
    if extracted_cores:
        composite.light_sources[:] = [ls for ls in composite.light_sources if (ls.x, ls.y) not in extracted_cores]
    composite.invalidate_hazards()


def tile_in_player_ship_region(tile_x: int, tile_y: int, engine) -> bool:
    """Return True if the composite tile maps to a non-space tile in the
    player's original ship_map (or always True when no interdiction is active).

    Used by gates like 'you can't extract YOUR ship's reactor core' so they
    only apply to the player side of the composite during an interdiction.
    Checks the original_ship_map tiles directly: a composite tile is "in the
    player ship" iff it corresponds to a non-space tile in player_map.
    """
    interdiction = current_interdiction(engine)
    # Keyed off the composite being the active map, NOT off ``resolved``:
    # restoration is deferred to ship exit, so the pirate ship is still
    # there (and its core still lootable) after the last pirate dies.
    if interdiction is None or interdiction.player_offset is None or interdiction.original_ship_map is None:
        return True
    from world import tile_types

    pox, poy = interdiction.player_offset
    nx, ny = tile_x - pox, tile_y - poy
    pmap = interdiction.original_ship_map
    if not (0 <= nx < pmap.width and 0 <= ny < pmap.height):
        return False
    return int(pmap.tiles["tile_id"][nx, ny]) != int(tile_types.space["tile_id"])


def restore_original_ship_map(interdiction: Interdiction, ship) -> None:
    """Swap ``ship.game_map`` back to the original (pre-interdiction) map.

    Removes pirate-side entities/light_sources from the shared player_map
    lists and reverts player entity/light positions from composite back to
    native coords. Idempotent. Only meaningful when
    ``interdiction.original_ship_map`` is set.
    """
    if interdiction.original_ship_map is None:
        return
    pmap = interdiction.original_ship_map
    # 1. Remove pirate-side overlay entities/lights from the shared lists.
    for ref in interdiction.pirate_entities_overlay:
        try:
            pmap.entities.remove(ref)
        except ValueError:
            pass
    for ref in interdiction.pirate_light_sources_overlay:
        try:
            pmap.light_sources.remove(ref)
        except ValueError:
            pass
    interdiction.pirate_entities_overlay = []
    interdiction.pirate_light_sources_overlay = []
    # 2. Untranslate remaining (player-origin) entities + lights back to native.
    if interdiction.player_offset is not None:
        pox, poy = interdiction.player_offset
        for e in pmap.entities:
            e.x -= pox
            e.y -= poy
        for ls in pmap.light_sources:
            ls.x -= pox
            ls.y -= poy
    # 3. Swap the ship game_map back.
    ship.game_map = pmap
    if interdiction.original_exit_pos is not None:
        ship.exit_pos = interdiction.original_exit_pos
    if interdiction.original_rooms is not None:
        ship.rooms = interdiction.original_rooms
    interdiction.original_ship_map = None
    interdiction.original_exit_pos = None
    interdiction.original_rooms = None
    interdiction.composite_map = None
    interdiction.pristine_tile_ids = None
    pmap.invalidate_entity_index()
    pmap.invalidate_hazards()


# ---------------------------------------------------------------------------
# Session lifecycle (driven by whichever state puts the player aboard)
# ---------------------------------------------------------------------------

_DIRECTION_NAMES: dict[tuple[int, int], str] = {
    (0, -1): "north",
    (0, 1): "south",
    (-1, 0): "west",
    (1, 0): "east",
}


def _direction_name(direction: tuple[int, int] | None) -> str:
    if direction is None:
        return "outer"
    return _DIRECTION_NAMES.get(tuple(direction), "outer")


def current_interdiction(engine) -> Interdiction | None:
    """The current system's Interdiction, or None."""
    galaxy = getattr(engine, "galaxy", None)
    if galaxy is None:
        return None
    system = galaxy.systems.get(galaxy.current_system)
    return system.interdiction if system is not None else None


def prepare_ship_entry(engine) -> None:
    """Bring the interdiction up to date as the player boards their ship.

    * Resolved with a stale composite -> restore the original ship map.
    * Queued -> start it (may swap ``engine.ship.game_map`` to the composite).
    * Started but composite missing (post-load) -> rebuild it.
    * Always: reveal the breach and re-attach live pirates to the active map.
    """
    interdiction = current_interdiction(engine)
    if interdiction is None:
        return

    if interdiction.resolved:
        restore_original_ship_map(interdiction, engine.ship)
        return

    if not interdiction.started:
        rng = engine.rng(f"start_interdiction:{engine.galaxy.current_system}")
        start_interdiction(interdiction, engine.ship, rng)
        if interdiction.started:
            heading = _direction_name(interdiction.attach_direction)
            engine.message_log.add_message(
                f"A pirate boarding craft has clamped onto the {heading} airlock!",
                (255, 200, 100),
            )
        elif interdiction.resolved:
            # No facing-airlock pair was available — boarding attempt failed.
            engine.message_log.add_message(
                "The pirate craft couldn't find a docking point and broke off.",
                (200, 200, 200),
            )
            return
    elif interdiction.composite_map is None:
        # Started, but the composite was wiped (e.g. by a save/load cycle).
        if not rebuild_composite(interdiction, engine.ship):
            interdiction.resolve()
            return

    game_map = engine.ship.game_map
    # Reveal the corridor + spawn-room tiles so the breach is visible
    # on the map even before the player walks into FOV range.
    for tx, ty in interdiction.connector_tiles:
        if game_map.in_bounds(tx, ty):
            game_map.explored[tx, ty] = True
    if interdiction.craft_room is not None:
        room = interdiction.craft_room
        for tx in range(room.x1, room.x2 + 1):
            for ty in range(room.y1, room.y2 + 1):
                if game_map.in_bounds(tx, ty):
                    game_map.explored[tx, ty] = True
    # Drop dead pirates from the roster, then re-attach the live ones.
    interdiction.pirate_entities = [p for p in interdiction.pirate_entities if p.fighter and p.fighter.hp > 0]
    for pirate in interdiction.pirate_entities:
        if pirate not in game_map.entities:
            game_map.entities.append(pirate)
    game_map.invalidate_entity_index()


def detach_pirates(engine) -> None:
    """Strip pirates from the active map; the roster on the Interdiction keeps the living ones."""
    interdiction = current_interdiction(engine)
    if interdiction is None or not interdiction.started:
        return
    for pirate in list(interdiction.pirate_entities):
        if pirate in engine.game_map.entities:
            engine.game_map.entities.remove(pirate)
    interdiction.pirate_entities = [p for p in interdiction.pirate_entities if p.fighter and p.fighter.hp > 0]
    engine.game_map.invalidate_entity_index()


def resolve_if_cleared(engine) -> bool:
    """Resolve the interdiction once every pirate is dead. Returns True if it resolved just now.

    Map restoration stays deferred to the next ship exit so the player is
    never left standing on a tile that is about to vanish.
    """
    interdiction = current_interdiction(engine)
    if interdiction is None or not interdiction.started or interdiction.resolved:
        return False
    if interdiction.alive_pirate_count() > 0:
        return False
    interdiction.resolve()
    engine.message_log.add_message("Interdiction repelled — system clear.", (100, 255, 100))
    return True
