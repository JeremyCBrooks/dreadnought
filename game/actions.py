"""Action classes executed by entities each turn."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity


class Action:
    def perform(self, engine: Engine, entity: Entity) -> int:
        """Execute the action. Return number of ticks consumed (0 = no-op)."""
        raise NotImplementedError


class WaitAction(Action):
    def perform(self, engine: Engine, entity: Entity) -> bool:
        return True


class MovementAction(Action):
    def __init__(self, dx: int, dy: int) -> None:
        self.dx = dx
        self.dy = dy

    def perform(self, engine: Engine, entity: Entity) -> int:
        dest_x = entity.x + self.dx
        dest_y = entity.y + self.dy
        if not engine.game_map.is_walkable(dest_x, dest_y):
            return False
        if engine.game_map.get_blocking_entity(dest_x, dest_y):
            return False
        if engine.game_map.get_interactable_at(dest_x, dest_y):
            return False
        entity.x = dest_x
        entity.y = dest_y
        from game.environment import has_low_gravity
        if has_low_gravity(engine):
            return 2
        return True


class MeleeAction(Action):
    def __init__(self, target: Entity) -> None:
        self.target = target

    def perform(self, engine: Engine, entity: Entity) -> bool:
        if not entity.fighter or not self.target.fighter:
            return False
        import debug
        if debug.ONE_HIT_KILL and entity is engine.player:
            damage = self.target.fighter.hp
        else:
            defense = self.target.fighter.defense
            if self.target is engine.player and getattr(engine, "suit", None):
                defense += engine.suit.defense_bonus
            damage = max(1, entity.fighter.power - defense)
        if debug.GOD_MODE and self.target is engine.player:
            damage = 0
        self.target.fighter.hp = max(0, self.target.fighter.hp - damage)

        if entity is engine.player:
            msg = f"You hit the {self.target.name} for {damage} damage."
            color = (255, 255, 255)
        else:
            msg = f"The {entity.name} hits you for {damage} damage."
            color = (255, 200, 200)
        engine.message_log.add_message(msg, color)

        if self.target.fighter.hp <= 0:
            if self.target is engine.player:
                engine.message_log.add_message("You die...", (255, 0, 0))
            else:
                engine.message_log.add_message(
                    f"The {self.target.name} is destroyed!", (200, 200, 200)
                )
                if self.target in engine.game_map.entities:
                    engine.game_map.entities.remove(self.target)
        return True


class BumpAction(Action):
    """Move or attack, depending on what occupies the destination."""

    def __init__(self, dx: int, dy: int) -> None:
        self.dx = dx
        self.dy = dy

    def perform(self, engine: Engine, entity: Entity) -> bool:
        dest_x = entity.x + self.dx
        dest_y = entity.y + self.dy
        target = engine.game_map.get_blocking_entity(dest_x, dest_y)
        if target and target.fighter:
            return MeleeAction(target).perform(engine, entity)
        return MovementAction(self.dx, self.dy).perform(engine, entity)


class PickupAction(Action):
    def perform(self, engine: Engine, entity: Entity) -> bool:
        items = engine.game_map.get_items_at(entity.x, entity.y)
        if not items:
            engine.message_log.add_message("Nothing to pick up.", (100, 100, 100))
            return False
        item = items[0]
        # Player picks up into collection tank (not usable until return to ship)
        if entity is engine.player:
            entity.collection_tank.append(item)
        else:
            entity.inventory.append(item)
        engine.game_map.entities.remove(item)
        engine.message_log.add_message(
            f"You pick up the {item.name}.", (200, 200, 255)
        )
        return True


class DropAction(Action):
    def __init__(self, item_index: int) -> None:
        self.item_index = item_index

    def perform(self, engine: Engine, entity: Entity) -> bool:
        if self.item_index < 0 or self.item_index >= len(entity.inventory):
            return False
        item = entity.inventory.pop(self.item_index)
        item.x = entity.x
        item.y = entity.y
        engine.game_map.entities.append(item)
        engine.message_log.add_message(f"You drop the {item.name}.", (200, 200, 200))
        return True


def _adjacent_interactable(engine: Engine, entity: Entity):
    """Return first interactable entity adjacent to entity, or None."""
    gm = engine.game_map
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = entity.x + dx, entity.y + dy
            target = gm.get_interactable_at(nx, ny)
            if target:
                return target
    return None


class InteractAction(Action):
    """Interact with an adjacent object (console, crate, etc.); may trigger hazards."""

    def perform(self, engine: Engine, entity: Entity) -> bool:
        target = _adjacent_interactable(engine, entity)
        if not target or not target.interactable:
            engine.message_log.add_message("Nothing to interact with here.", (100, 100, 100))
            return False

        ih = target.interactable
        name = target.name

        # Trigger hazard if present (and not scanned/safe)
        if ih.get("hazard") and not ih.get("scanned"):
            from game.hazards import trigger_hazard
            trigger_hazard(engine, ih["hazard"], name)
        elif ih.get("hazard") and ih.get("scanned"):
            engine.message_log.add_message(
                f"Your scan helps you bypass the hazard on the {name}.", (100, 255, 200)
            )

        # Loot
        loot = ih.get("loot")
        if loot and isinstance(loot, dict):
            from game.entity import Entity as E
            from data import db
            item_data = db.build_item_data(loot)
            item_ent = E(
                x=entity.x, y=entity.y,
                char=loot["char"], color=loot["color"], name=loot["name"],
                blocks_movement=False,
                item=item_data,
            )
            # Player loot goes to collection tank
            if entity is engine.player:
                entity.collection_tank.append(item_ent)
            else:
                entity.inventory.append(item_ent)
            engine.message_log.add_message(
                f"You search the {name}... Found {loot['name']}!", (200, 255, 200)
            )
        else:
            engine.message_log.add_message(
                f"You search the {name}. Nothing useful.", (150, 150, 150)
            )

        # Remove interactable after use
        if target in engine.game_map.entities:
            engine.game_map.entities.remove(target)
        return True


class ScanAction(Action):
    """Use scanner tool on an adjacent interactable; tiered reveal of hazards. Costs 1 turn."""

    def perform(self, engine: Engine, entity: Entity) -> bool:
        # Check loadout tool slot first (player), fallback to inventory (enemies)
        scanner = None
        if getattr(entity, "loadout", None):
            scanner = entity.loadout.get_scanner()
        if not scanner:
            for e in entity.inventory:
                if e.item and e.item.get("type") == "scanner":
                    scanner = e
                    break
        if not scanner:
            engine.message_log.add_message("You need a scanner to scan.", (150, 150, 150))
            return False

        target = _adjacent_interactable(engine, entity)
        if not target or not target.interactable:
            engine.message_log.add_message("Nothing to scan here.", (100, 100, 100))
            return False

        tier = scanner.item.get("scanner_tier", 1)
        hazard = target.interactable.get("hazard")
        target.interactable["scanned"] = True

        if not hazard:
            engine.message_log.add_message("Scan clear. Safe to interact.", (0, 255, 100))
            return True

        if tier == 1:
            engine.message_log.add_message("WARNING: Hazard detected.", (255, 200, 0))
        elif tier == 2:
            htype = hazard.get("type", "unknown")
            sev = hazard.get("severity", "moderate")
            engine.message_log.add_message(
                f"WARNING: {htype.title()} hazard ({sev}).", (255, 220, 0)
            )
        else:
            htype = hazard.get("type", "unknown")
            sev = hazard.get("severity", "moderate")
            engine.message_log.add_message(
                f"{htype.title()} hazard ({sev}). Proceed with caution.", (255, 255, 150)
            )
        return True


def _get_equipped_ranged_weapon(entity: Entity):
    """Return the ranged weapon from loadout if available, else fallback to inventory (enemies)."""
    # Check loadout weapon slot first (player)
    if getattr(entity, "loadout", None):
        wpn = entity.loadout.get_ranged_weapon()
        if wpn:
            return wpn
    # Fallback to inventory (for enemies without loadout)
    for e in entity.inventory:
        if (
            e.item
            and e.item.get("type") == "weapon"
            and e.item.get("weapon_class") == "ranged"
            and e.item.get("ammo", 0) > 0
        ):
            return e
    return None


class RangedAction(Action):
    """Fire a ranged weapon at a target."""

    def __init__(self, target: Entity) -> None:
        self.target = target

    def perform(self, engine: Engine, entity: Entity) -> bool:
        if not entity.fighter or not self.target.fighter:
            return False

        weapon = _get_equipped_ranged_weapon(entity)
        if not weapon:
            engine.message_log.add_message("No ranged weapon with ammo.", (255, 100, 100))
            return False

        # Check range
        dx = abs(entity.x - self.target.x)
        dy = abs(entity.y - self.target.y)
        distance = max(dx, dy)
        max_range = weapon.item.get("range", 5)
        if distance > max_range:
            engine.message_log.add_message("Target out of range.", (255, 100, 100))
            return False

        # Check FOV
        if not engine.game_map.visible[self.target.x, self.target.y]:
            engine.message_log.add_message("Target not visible.", (255, 100, 100))
            return False

        # Consume ammo
        weapon.item["ammo"] -= 1

        # Damage
        import debug
        if debug.ONE_HIT_KILL and entity is engine.player:
            damage = self.target.fighter.hp
        else:
            defense = self.target.fighter.defense
            if self.target is engine.player and getattr(engine, "suit", None):
                defense += engine.suit.defense_bonus
            damage = max(1, weapon.item["value"] - defense)
        if debug.GOD_MODE and self.target is engine.player:
            damage = 0

        self.target.fighter.hp = max(0, self.target.fighter.hp - damage)

        if entity is engine.player:
            msg = f"You shoot the {self.target.name} for {damage} damage."
            color = (255, 200, 100)
        else:
            msg = f"The {entity.name} shoots you for {damage} damage."
            color = (255, 150, 150)
        engine.message_log.add_message(msg, color)

        if self.target.fighter.hp <= 0:
            if self.target is engine.player:
                engine.message_log.add_message("You die...", (255, 0, 0))
            else:
                engine.message_log.add_message(
                    f"The {self.target.name} is destroyed!", (200, 200, 200)
                )
                if self.target in engine.game_map.entities:
                    engine.game_map.entities.remove(self.target)
        return True
