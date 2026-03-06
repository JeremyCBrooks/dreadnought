"""Trigger hazard effects on the player (from interactable objects)."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ui.colors import (
    HAZARD_ELECTRIC, HAZARD_RADIATION, HAZARD_EXPLOSIVE, HAZARD_GAS,
    HAZARD_STRUCTURAL,
)

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity, Fighter

GAS_O2_DRAIN = 5

# Maps hazard type -> (message template, color).
# Template receives {source_name} and {damage} via str.format_map().
_HAZARD_MESSAGES = {
    "electric":   ("Electric discharge from {source_name}! You take {damage} damage.", HAZARD_ELECTRIC),
    "radiation":  ("Radiation leak from {source_name}! You take {damage} damage. You feel sick.", HAZARD_RADIATION),
    "explosive":  ("Explosion at {source_name}! You take {damage} damage.", HAZARD_EXPLOSIVE),
    "gas":        ("Toxic gas from {source_name}! You take {damage} damage.", HAZARD_GAS),
}


def _apply_hp_damage(fighter: Fighter, amount: int) -> None:
    """Reduce HP by *amount*, clamped to 0."""
    fighter.hp = max(0, fighter.hp - amount)


def _apply_equipment_damage(engine: Engine, player: Entity) -> None:
    """50% chance to damage a random loadout/inventory item with durability."""
    if random.random() >= 0.5:
        return
    if getattr(player, "loadout", None):
        candidates = player.loadout.items_with_durability()
    else:
        candidates = [
            e for e in player.inventory
            if e.item and e.item.get("durability") is not None and e.item.get("durability", 0) > 0
        ]
    if not candidates:
        return
    victim = random.choice(candidates)
    victim.item["durability"] = max(0, victim.item.get("durability", 1) - 1)
    if victim.item["durability"] <= 0:
        if getattr(player, "loadout", None):
            player.loadout.remove_item(victim)
        else:
            player.inventory.remove(victim)
        engine.message_log.add_message(
            f"Your {victim.name} is destroyed!", HAZARD_EXPLOSIVE
        )
    else:
        engine.message_log.add_message(
            f"Your {victim.name} is damaged!", HAZARD_ELECTRIC
        )


def trigger_hazard(engine: Engine, hazard: dict, source_name: str) -> None:
    """Apply hazard effect to the player. hazard has type, severity, damage, equipment_damage."""
    import debug
    if debug.DISABLE_HAZARDS:
        return
    if not engine.player or not engine.player.fighter:
        return
    htype = hazard.get("type", "electric")
    damage = hazard.get("damage", 1)
    player = engine.player

    _apply_hp_damage(player.fighter, damage)

    # Type-specific side effects
    if htype == "electric" and hazard.get("equipment_damage", False):
        _apply_equipment_damage(engine, player)

    if htype == "gas":
        drained = False
        if engine.suit and "vacuum" in engine.suit.current_pools:
            engine.suit.current_pools["vacuum"] = max(
                0, engine.suit.current_pools["vacuum"] - GAS_O2_DRAIN
            )
            drained = True
        suffix = " Suit O2 contaminated!" if drained else ""
        engine.message_log.add_message(
            f"Toxic gas from {source_name}! You take {damage} damage.{suffix}",
            HAZARD_GAS,
        )
    elif htype in _HAZARD_MESSAGES:
        template, color = _HAZARD_MESSAGES[htype]
        engine.message_log.add_message(
            template.format(source_name=source_name, damage=damage), color
        )
    else:
        engine.message_log.add_message(
            f"Structural collapse at {source_name}! You take {damage} damage.",
            HAZARD_STRUCTURAL,
        )

    # Data-driven DoT: if hazard defines dot > 0, add an active effect
    dot = hazard.get("dot", 0)
    duration = hazard.get("duration", 0)
    if dot > 0 and duration != 0:
        engine.active_effects.append(
            {"type": htype, "dot": dot, "remaining": duration}
        )


def apply_dot_effects(engine: Engine) -> None:
    """Call each turn: apply all active DoT effects, decrement remaining, remove expired."""
    if not engine.active_effects or not engine.player:
        return
    import debug
    surviving: list[dict] = []
    for effect in engine.active_effects:
        if not debug.GOD_MODE:
            _apply_hp_damage(engine.player.fighter, effect["dot"])
        engine.message_log.add_message(
            f"{effect['type'].title()} damage!", HAZARD_RADIATION
        )
        if effect["remaining"] == -1:
            surviving.append(effect)
        else:
            effect["remaining"] -= 1
            if effect["remaining"] > 0:
                surviving.append(effect)
    engine.active_effects = surviving
