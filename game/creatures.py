"""What creatures do beyond walking and biting: temperaments, disguises, death throes, chores and glow.

Each behaviour reads the creature's ``ai_config`` (built from its data
definition and saved with it), so a creature is configured entirely in
``data.enemies``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from data.colors import WARNING

if TYPE_CHECKING:
    from data.interactables import InteractableDef
    from engine.game_state import Engine
    from game.entity import Entity

# ai_config key holding a disguised creature's real look until it is found out.
_TRUE_FORM = "true_form"


def is_disguised(entity: Entity) -> bool:
    """True while a creature is passing itself off as a furnishing."""
    return bool(entity.ai_config) and _TRUE_FORM in entity.ai_config


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


def reveal(engine: Engine, creature: Entity, message: str | None = None) -> None:
    """Drop a creature's disguise, announcing it with *message* (or the default ambush line)."""
    if not is_disguised(creature):
        return
    furnishing = creature.name
    true_form = creature.ai_config.pop(_TRUE_FORM)
    creature.char = true_form["char"]
    creature.color = tuple(true_form["color"])
    creature.name = true_form["name"]
    creature.interactable = None
    engine.message_log.add_message(message or f"The {furnishing} was a {creature.name}!", WARNING)
