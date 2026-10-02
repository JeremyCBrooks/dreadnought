"""One world tick after a player action: hazards, decompression, drift, enemies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.environment import (
    apply_environment_tick,
    apply_environment_tick_entity,
    process_decompression_step,
    trigger_decompression,
)
from game.hazards import apply_dot_effects

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity

_RED = (255, 0, 0)
_GREY = (200, 200, 200)
_VOID = (180, 100, 255)


def advance_turn(engine: Engine) -> str | None:
    """Advance the world one tick. Returns the cause if the player died during it, else None."""
    engine.turn_counter += 1
    game_map = engine.game_map
    game_map.invalidate_entity_index()
    game_map.clear_fov_cache()

    apply_environment_tick(engine)
    apply_dot_effects(engine)
    if engine.player.fighter.hp <= 0:
        return "Succumbed to the environment."

    _process_decompression(engine)
    if engine.player.fighter.hp <= 0:
        return "Crushed by explosive decompression."

    cause = _drift_player(engine)
    if cause is not None:
        return cause
    _drift_others(engine)

    game_map.invalidate_entity_index()
    _run_enemies(engine)

    if engine.player.fighter.hp <= 0:
        engine.message_log.add_message("You died.", _RED)
        return "Overwhelmed by hostiles."
    return None


def lose_to_space(engine: Engine, entity: Entity) -> None:
    """Kill and remove an entity that drifted off the map or into a hull.

    It must end up dead, not merely off the map: rosters that outlive the
    map (boarding pirates) decide who is still a threat by HP.
    """
    if entity.fighter is not None:
        entity.fighter.hp = 0
    if entity in engine.game_map.entities:
        engine.game_map.entities.remove(entity)


def _process_decompression(engine: Engine) -> None:
    """Start any pending decompression, pull tagged entities, and clear those it crushed."""
    game_map = engine.game_map
    pending = game_map._pending_decompression
    if pending:
        game_map._pull_directions = trigger_decompression(engine, pending["breach_sources"], pending["newly_exposed"])
        game_map._pending_decompression = None

    pull_dirs = game_map._pull_directions
    if pull_dirs:
        for entity in list(game_map.entities):
            if entity.decompression_moves > 0:
                process_decompression_step(game_map, entity, pull_dirs)
        if not any(e.decompression_moves > 0 for e in game_map.entities):
            game_map._pull_directions = None

    for entity in list(game_map.entities):
        if entity is engine.player:
            continue
        if entity.fighter and entity.fighter.hp <= 0:
            engine.message_log.add_message(f"The {entity.name} is crushed by the decompression!", _GREY)
            game_map.entities.remove(entity)


def _is_space(engine: Engine, x: int, y: int) -> bool:
    from world import tile_types

    return engine.game_map.tiles["tile_id"][x, y] == int(tile_types.space["tile_id"])


def _drift_player(engine: Engine) -> str | None:
    """Carry a drifting player one tile. Returns the death cause if the drift ends them."""
    player = engine.player
    if not player.drifting:
        return None
    dx, dy = player.drift_direction
    nx, ny = player.x + dx, player.y + dy
    if not engine.game_map.in_bounds(nx, ny):
        engine.message_log.add_message("You drift beyond reach... lost to the void.", _RED)
        player.fighter.hp = 0
        return "Lost to the void."
    # Only space tiles are passable while drifting
    if not _is_space(engine, nx, ny):
        engine.message_log.add_message("You slam into the hull. The impact is fatal.", _RED)
        player.fighter.hp = 0
        return "Slammed into the hull."
    player.x, player.y = nx, ny
    engine.message_log.add_message("You drift further into space...", _VOID)
    return None


def _drift_others(engine: Engine) -> None:
    for entity in list(engine.game_map.entities):
        if entity is engine.player or not entity.drifting:
            continue
        dx, dy = entity.drift_direction
        nx, ny = entity.x + dx, entity.y + dy
        if not engine.game_map.in_bounds(nx, ny):
            lose_to_space(engine, entity)
            continue
        if not _is_space(engine, nx, ny):
            lose_to_space(engine, entity)
            engine.message_log.add_message(f"The {entity.name} slams into the hull!", _GREY)
            continue
        entity.x, entity.y = nx, ny


def _run_enemies(engine: Engine) -> None:
    """Enemy AI turns, then per-tile hazard damage for whoever is still standing."""
    import debug

    if not debug.DISABLE_ENEMY_AI:
        for entity in list(engine.game_map.entities):
            if entity is engine.player:
                continue
            if entity.ai and entity.fighter and entity.fighter.hp > 0:
                entity.ai.perform(entity, engine)

    for entity in list(engine.game_map.entities):
        if entity is engine.player:
            continue
        if entity.fighter and entity.fighter.hp > 0:
            apply_environment_tick_entity(engine, entity)
