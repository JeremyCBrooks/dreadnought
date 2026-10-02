"""Pirate wrecks: a boarding craft whose crew was killed stays in the system, dead in space.

The wreck is the ship that was fought on, as the player left it. Only what
the player changed is remembered; the rest regenerates from the ship's seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from data.colors import NEUTRAL
from data.names import WRECK_LOC_TYPE, WRECK_NAME_FORMAT

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity
    from game.interdiction import Interdiction
    from world.galaxy import Galaxy, Location
    from world.game_map import GameMap


@dataclass
class WreckRecord:
    """What a save must carry to rebuild a wreck: its seed and the player's changes to it."""

    ship_seed: int
    # (x, y, tile_id) in the wreck's own coordinates: opened doors, an extracted core.
    tile_changes: list[tuple[int, int, int]] = field(default_factory=list)
    # Indices of furnishings already searched; they regenerate in the same order.
    consumed_furnishings: list[int] = field(default_factory=list)
    # --- Transient: the freshly generated ship the live map is diffed against ---
    pristine_tile_ids: Any | None = field(default=None, repr=False, compare=False)
    pristine_furnishings: list[Entity] | None = field(default=None, repr=False, compare=False)

    def refresh(self, game_map: GameMap) -> None:
        """Re-read the player's changes from the live wreck map built from this record."""
        if self.pristine_tile_ids is None or self.pristine_furnishings is None:
            return
        from game.helpers import changed_tiles, missing_entity_indices

        self.tile_changes = changed_tiles(self.pristine_tile_ids, game_map)
        self.consumed_furnishings = missing_entity_indices(self.pristine_furnishings, game_map)


def build_wreck_map(record: WreckRecord) -> tuple[GameMap, list, tuple[int, int] | None]:
    """Return (game_map, rooms, exit_pos) for the wreck as the player left it.

    Changes that do not land on the ship's own hull are ignored, so a record
    made from a composite map cannot carry the player's ship across.
    """
    from game.helpers import remove_entities_at_indices
    from game.interdiction import apply_tile_changes
    from world import tile_types
    from world.boarding_ship import generate_pirate_ship

    game_map, rooms, exit_pos = generate_pirate_ship(record.ship_seed)
    pristine = game_map.tiles["tile_id"].copy()
    record.pristine_tile_ids = pristine
    record.pristine_furnishings = list(game_map.entities)

    space_id = int(tile_types.space["tile_id"])
    on_hull = [
        (x, y, tile_id)
        for x, y, tile_id in record.tile_changes
        if game_map.in_bounds(x, y) and int(pristine[x, y]) != space_id
    ]
    apply_tile_changes(game_map, on_hull)
    remove_entities_at_indices(record.pristine_furnishings, record.consumed_furnishings, game_map)
    return game_map, rooms, exit_pos


def _wreck_name(galaxy: Galaxy, ship_seed: int) -> str:
    """A name no other system or location holds, numbered from the ship's seed."""
    number = 100 + ship_seed % 900
    while not galaxy.claim_name(WRECK_NAME_FORMAT.format(number=number)):
        number += 1
    return WRECK_NAME_FORMAT.format(number=number)


def leave_wreck(engine: Engine, interdiction: Interdiction) -> Location | None:
    """Turn a cleared, still-docked boarding craft into a wreck location in the current system.

    Call before the composite map is torn down: it is the only record of what
    the player did aboard. Returns None when there is nothing to leave behind
    (the craft never docked, has already gone, or still has a living crew).
    """
    if not interdiction.started or interdiction.composite_map is None:
        return None
    if interdiction.pirate_ship_seed is None or interdiction.pirate_offset is None:
        return None
    if interdiction.alive_pirate_count() > 0:
        return None
    from world.galaxy import Location

    ox, oy = interdiction.pirate_offset
    record = WreckRecord(
        ship_seed=interdiction.pirate_ship_seed,
        tile_changes=[(x - ox, y - oy, tile_id) for x, y, tile_id in interdiction.tile_changes()],
        consumed_furnishings=interdiction.consumed_overlay_indices(),
    )
    # Building once keeps only the changes made to the pirate ship itself.
    game_map, _, _ = build_wreck_map(record)
    record.refresh(game_map)

    galaxy = engine.galaxy
    system = galaxy.systems[galaxy.current_system]
    location = Location(_wreck_name(galaxy, record.ship_seed), WRECK_LOC_TYPE, system_name=system.name)
    location.visited = True
    location.wreck = record
    system.locations.append(location)
    engine.message_log.add_message(f"{location.name} drifts free, dead in space.", NEUTRAL)
    return location
