"""Trigger hazard effects on the player (from interactable objects)."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Engine


def trigger_hazard(engine: Engine, hazard: dict, source_name: str) -> None:
    """
    Apply hazard effect to the player. hazard has type, severity, damage, equipment_damage.
    """
    import debug
    if debug.DISABLE_HAZARDS:
        return
    if not engine.player or not engine.player.fighter:
        return
    htype = hazard.get("type", "electric")
    damage = hazard.get("damage", 1)
    equipment_damage = hazard.get("equipment_damage", False)
    player = engine.player

    if htype == "electric":
        player.fighter.hp = max(0, player.fighter.hp - damage)
        engine.message_log.add_message(
            f"Electric discharge from {source_name}! You take {damage} damage.",
            (255, 200, 0),
        )
        if equipment_damage and random.random() < 0.5:
            # Target loadout items first, fallback to inventory (enemies)
            if getattr(player, "loadout", None):
                candidates = player.loadout.items_with_durability()
            else:
                candidates = [
                    e for e in player.inventory
                    if e.item and e.item.get("durability") is not None and e.item.get("durability", 0) > 0
                ]
            if candidates:
                victim = random.choice(candidates)
                victim.item["durability"] = max(0, victim.item.get("durability", 1) - 1)
                if victim.item["durability"] <= 0:
                    if getattr(player, "loadout", None):
                        player.loadout.remove_item(victim)
                    else:
                        player.inventory.remove(victim)
                    engine.message_log.add_message(
                        f"Your {victim.name} is destroyed!", (255, 100, 0)
                    )
                else:
                    engine.message_log.add_message(
                        f"Your {victim.name} is damaged!", (255, 150, 0)
                    )

    elif htype == "radiation":
        player.fighter.hp = max(0, player.fighter.hp - damage)
        engine.message_log.add_message(
            f"Radiation leak from {source_name}! You take {damage} damage. You feel sick.",
            (200, 255, 100),
        )

    elif htype == "explosive":
        player.fighter.hp = max(0, player.fighter.hp - damage)
        engine.message_log.add_message(
            f"Explosion at {source_name}! You take {damage} damage.",
            (255, 100, 0),
        )
        # Alert enemies: set them to chase (they already chase when visible; ensure they're "alerted")
        for e in engine.game_map.entities:
            if e.ai and e.fighter and e.fighter.hp > 0:
                pass  # HostileAI already chases when player in FOV; consider adding "alerted" later

    elif htype == "gas":
        # Drain suit atmosphere: gas contaminates the O2 (vacuum) pool
        drained = False
        if engine.suit and "vacuum" in engine.suit.current_pools:
            drain = 5
            engine.suit.current_pools["vacuum"] = max(
                0, engine.suit.current_pools["vacuum"] - drain
            )
            drained = True
        player.fighter.hp = max(0, player.fighter.hp - damage)
        suffix = " Suit O2 contaminated!" if drained else ""
        engine.message_log.add_message(
            f"Toxic gas from {source_name}! You take {damage} damage.{suffix}",
            (100, 255, 100),
        )

    else:  # structural / unknown
        player.fighter.hp = max(0, player.fighter.hp - damage)
        engine.message_log.add_message(
            f"Structural collapse at {source_name}! You take {damage} damage.",
            (180, 180, 180),
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
    surviving: list[dict] = []
    for effect in engine.active_effects:
        import debug
        if not debug.GOD_MODE:
            engine.player.fighter.hp = max(0, engine.player.fighter.hp - effect["dot"])
        engine.message_log.add_message(
            f"{effect['type'].title()} damage!", (200, 255, 100)
        )
        if effect["remaining"] == -1:
            surviving.append(effect)
        else:
            effect["remaining"] -= 1
            if effect["remaining"] > 0:
                surviving.append(effect)
    engine.active_effects = surviving
