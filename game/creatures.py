"""What creatures do beyond walking and biting: temperaments, disguises, death throes and chores.

Each behaviour reads the creature's ``ai_config`` (built from its data
definition and saved with it), so a creature is configured entirely in
``data.enemies``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import TYPE_CHECKING

from data.colors import NEUTRAL, WARNING
from data.enemies import TEMPERAMENTS, Temperament

if TYPE_CHECKING:
    from data.enemies import Community
    from data.interactables import InteractableDef
    from engine.game_state import Engine
    from game.entity import Entity

# ai_config key holding a disguised creature's real look until it is found out.
_TRUE_FORM = "true_form"
_AMBUSH = "The {furnishing} was a {creature}!"


# ---- Who lives where ----


def community_of(location) -> Community | None:
    """The community living at *location*: always the same one for the same place.

    The Dreadnought is never a peaceful place.
    """
    from data.enemies import pick_community

    return pick_community(
        location.loc_type, location.name, allow_peaceful=not getattr(location, "is_dreadnought", False)
    )


# ---- Temperament ----


def temperament_of(creature: Entity) -> Temperament:
    """How *creature* treats the player right now (it can change when provoked)."""
    return TEMPERAMENTS[(creature.ai_config or {}).get("temperament", "hostile")]


def is_companion(creature: Entity) -> bool:
    """True for a creature that tags along with the player and is never fought by bumping."""
    return creature.ai is not None and temperament_of(creature).on_sight == "follow"


def start_hunting(engine: Engine, creature: Entity) -> None:
    """Turn on the player, wherever they are."""
    creature.ai_state = "hunting"
    creature.ai_target = (engine.player.x, engine.player.y)
    creature.ai_turns_since_seen = 0
    creature.ai_stuck_turns = 0
    creature.ai_wander_goal = None


def provoke(engine: Engine, creature: Entity) -> None:
    """React to being hurt by the player: give itself away, turn on them, or bolt."""
    if creature.ai is None or creature.fighter is None or creature.fighter.hp <= 0:
        return
    reveal(engine, creature)
    became = temperament_of(creature).when_hurt
    if became is not None:
        creature.ai_config["temperament"] = became
    if temperament_of(creature).attacks:
        if creature.ai_state != "fleeing":
            start_hunting(engine, creature)
    else:
        creature.ai_state = "fleeing"
        creature.ai_wander_goal = None


# ---- Disguise ----


def is_disguised(entity: Entity) -> bool:
    """True while a creature is passing itself off as a furnishing."""
    return bool(entity.ai_config) and _TRUE_FORM in entity.ai_config


def is_target(entity: Entity) -> bool:
    """True for a living creature the player would know to aim at."""
    return entity.fighter is not None and entity.fighter.hp > 0 and not is_disguised(entity)


def disguise_as(creature: Entity, furnishing: InteractableDef) -> None:
    """Make *creature* look, read and search like *furnishing* until it is revealed."""
    creature.ai_config[_TRUE_FORM] = {
        "char": creature.char,
        "color": list(creature.color),
        "name": creature.name,
    }
    creature.char = furnishing.char
    creature.color = furnishing.color
    creature.name = furnishing.name
    creature.interactable = {"kind": furnishing.name.lower(), "hazard": None, "loot": None}


def reveal(engine: Engine, creature: Entity, template: str = _AMBUSH) -> None:
    """Drop a creature's disguise and say so (*template* gets ``furnishing`` and ``creature``)."""
    if not is_disguised(creature):
        return
    furnishing = creature.name
    true_form = creature.ai_config.pop(_TRUE_FORM)
    creature.char = true_form["char"]
    creature.color = tuple(true_form["color"])
    creature.name = true_form["name"]
    creature.interactable = None
    engine.message_log.add_message(template.format(furnishing=furnishing, creature=creature.name), WARNING)


def spring_ambush(engine: Engine, creature: Entity) -> None:
    """A disguised creature is touched or approached: it throws off its shell and strikes."""
    from game.actions import MeleeAction

    reveal(engine, creature)
    start_hunting(engine, creature)
    if engine.player.fighter and engine.player.fighter.hp > 0:
        MeleeAction(engine.player).perform(engine, creature)
    creature.ai_energy = 0


# ---- Death throes ----


def release_death_effect(engine: Engine, creature: Entity) -> None:
    """Let a dying creature's death effect hit everything standing next to it."""
    effect = (creature.ai_config or {}).get("death_effect")
    if not effect:
        return
    from data.hazards import HAZARD_BY_TYPE
    from game.actions import _apply_damage_and_death
    from game.hazards import trigger_hazard
    from game.helpers import chebyshev

    hazard = asdict(HAZARD_BY_TYPE[effect["hazard"]])
    engine.message_log.add_message(effect["message"].format(name=creature.name), WARNING)
    for other in list(engine.game_map.entities):
        if other is creature or other.fighter is None or other.fighter.hp <= 0:
            continue
        if chebyshev(creature.x, creature.y, other.x, other.y) > 1:
            continue
        if other is engine.player:
            trigger_hazard(engine, hazard, creature.name)
        elif hazard["type"] not in (other.ai_config or {}).get("hazard_immunities", ()):
            _apply_damage_and_death(engine, creature, other, hazard["damage"])


def is_immune(creature: Entity, hazard_type: str) -> bool:
    """True if *creature* shrugs off *hazard_type* (machines never need air)."""
    if hazard_type == "vacuum" and not creature.organic:
        return True
    return hazard_type in (creature.ai_config or {}).get("hazard_immunities", ())


# ---- Chores ----


def perform_chores(engine: Engine, creature: Entity) -> bool:
    """Do the first chore within reach. Returns True if the creature spent its turn on one."""
    return any(_CHORES[chore](engine, creature) for chore in (creature.ai_config or {}).get("chores", ()))


def _neighbours(x: int, y: int) -> list[tuple[int, int]]:
    return [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]


def _announce(engine: Engine, x: int, y: int, text: str) -> None:
    if engine.game_map.visible[x, y]:
        engine.message_log.add_message(text, NEUTRAL)


def _hull_tile_beside(engine: Engine, x: int, y: int):
    """The wall a breach should be patched with: whatever hull surrounds it."""
    from world import tile_types
    from world.dungeon_gen import player_ship_hull_tile

    game_map = engine.game_map
    unusable = {int(tile_types.space["tile_id"]), int(tile_types.hull_breach["tile_id"])}
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if not game_map.in_bounds(nx, ny) or game_map.tiles["walkable"][nx, ny]:
            continue
        if int(game_map.tiles["tile_id"][nx, ny]) not in unusable:
            return game_map.tiles[nx, ny].copy()
    return player_ship_hull_tile()


def _seal_breaches(engine: Engine, creature: Entity) -> bool:
    game_map = engine.game_map
    reach = set(_neighbours(creature.x, creature.y))
    breach = next((b for b in game_map.hull_breaches if b in reach), None)
    if breach is None:
        return False
    game_map.seal_hull_breach(*breach, _hull_tile_beside(engine, *breach))
    _announce(engine, *breach, f"The {creature.name} welds a hull breach shut.")
    return True


def _close_doors(engine: Engine, creature: Entity) -> bool:
    from world import tile_types

    game_map = engine.game_map
    open_id = int(tile_types.door_open["tile_id"])
    for x, y in _neighbours(creature.x, creature.y):
        if not game_map.in_bounds(x, y) or int(game_map.tiles["tile_id"][x, y]) != open_id:
            continue
        if game_map.get_blocking_entity(x, y) or game_map.get_non_blocking_entity_at(x, y):
            continue
        game_map.tiles[x, y] = tile_types.door_closed
        game_map.invalidate_hazards()
        game_map.clear_fov_cache()
        _announce(engine, x, y, f"The {creature.name} closes a door.")
        return True
    return False


_CHORES: dict[str, Callable[[Engine, Entity], bool]] = {
    "seal_breaches": _seal_breaches,
    "close_doors": _close_doors,
}
