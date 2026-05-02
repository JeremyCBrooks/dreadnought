"""Action classes executed by entities each turn."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity

from ui.colors import (
    DARK_GRAY,
    DEATH_MSG,
    ENEMY_ATTACK,
    ENEMY_DEATH,
    ENEMY_RANGED,
    HAZARD_VOID,
    INTERACT_EMPTY,
    INTERACT_LOOT,
    INTERACT_SAFE,
    NEUTRAL,
    PICKUP,
    PLAYER_ATTACK,
    PLAYER_RANGED,
    SCAN_MSG,
    WARNING,
)


def _calc_damage(engine: Engine, attacker: Entity, target: Entity, base_power: int) -> int:
    """Calculate damage after defense, respecting debug flags."""
    import debug

    if debug.ONE_HIT_KILL and attacker is engine.player:
        damage = target.fighter.hp
    else:
        defense = target.fighter.defense
        if target is engine.player and getattr(engine, "suit", None):
            defense += engine.suit.defense_bonus
        damage = max(1, base_power - defense)
    if debug.GOD_MODE and target is engine.player:
        damage = 0
    return damage


def _apply_damage_and_death(engine: Engine, attacker: Entity, target: Entity, damage: int) -> None:
    """Apply damage to target and handle death/removal."""
    target.fighter.hp = max(0, target.fighter.hp - damage)
    if target.fighter.hp <= 0:
        if target is engine.player:
            engine.message_log.add_message("You die...", DEATH_MSG)
        else:
            engine.message_log.add_message(f"The {target.name} is destroyed!", ENEMY_DEATH)
            if target.inventory:
                from game.helpers import drop_all_inventory

                drop_all_inventory(target, engine.game_map)
            from game.gore import place_death_gore

            place_death_gore(engine.game_map, target)
            if target in engine.game_map.entities:
                engine.game_map.entities.remove(target)


def _attack_message(
    engine: Engine,
    entity: Entity,
    target: Entity,
    player_verb: str,
    enemy_verb: str,
    damage: int,
    player_color: tuple,
    enemy_color: tuple,
) -> None:
    if entity is engine.player:
        msg = f"You {player_verb} the {target.name} for {damage} damage."
        color = player_color
    else:
        msg = f"The {entity.name} {enemy_verb} you for {damage} damage."
        color = enemy_color
    engine.message_log.add_message(msg, color)


_STEAL_CHANCE = 0.2


def _try_steal(engine: Engine, thief: Entity, target: Entity) -> None:
    """Attempt to steal a random non-equipped item from target."""
    rng = engine.rng(f"steal:{thief.x},{thief.y}")

    if rng.random() >= _STEAL_CHANCE:
        return

    # Collect stealable items (not in loadout)
    loadout = getattr(target, "loadout", None)
    stealable = [item for item in target.inventory if not (loadout and loadout.has_item(item))]
    if not stealable:
        return

    stolen = rng.choice(stealable)
    target.inventory.remove(stolen)
    thief.inventory.append(stolen)
    thief.stolen_loot.append(stolen)

    # Recalc melee power if a melee weapon was stolen
    from game.helpers import recalc_melee_power_ai

    recalc_melee_power_ai(thief)

    engine.message_log.add_message(f"The {thief.name} snatches your {stolen.name}!", WARNING)


class Action:
    def perform(self, engine: Engine, entity: Entity) -> int:
        """Execute the action. Return number of ticks consumed (0 = no-op)."""
        raise NotImplementedError


class WaitAction(Action):
    def perform(self, engine: Engine, entity: Entity) -> int:
        return 1


class MovementAction(Action):
    def __init__(self, dx: int, dy: int) -> None:
        self.dx = dx
        self.dy = dy

    def perform(self, engine: Engine, entity: Entity) -> int:
        dest_x = entity.x + self.dx
        dest_y = entity.y + self.dy
        if not engine.game_map.is_walkable(dest_x, dest_y):
            return 0
        from game.helpers import is_diagonal_blocked

        if is_diagonal_blocked(engine.game_map, entity.x, entity.y, self.dx, self.dy):
            return 0
        if engine.game_map.get_blocking_entity(dest_x, dest_y):
            return 0
        if engine.game_map.get_interactable_at(dest_x, dest_y):
            return 0
        entity.x = dest_x
        entity.y = dest_y
        engine.game_map.invalidate_entity_index()
        from game.environment import has_low_gravity

        if has_low_gravity(engine):
            return 2
        return 1


class MeleeAction(Action):
    def __init__(self, target: Entity) -> None:
        self.target = target

    def perform(self, engine: Engine, entity: Entity) -> int:
        if not entity.fighter or not self.target.fighter:
            return 0
        damage = _calc_damage(engine, entity, self.target, entity.fighter.power)
        _attack_message(engine, entity, self.target, "hit", "hits", damage, PLAYER_ATTACK, ENEMY_ATTACK)

        _apply_damage_and_death(engine, entity, self.target, damage)

        # Pickpocketing: enemy with can_steal attempts to snatch a non-equipped item
        if (
            entity is not engine.player
            and self.target is engine.player
            and self.target.fighter.hp > 0
            and entity.ai_config.get("can_steal")
            and entity.can_carry()
        ):
            _try_steal(engine, entity, self.target)

        return 1


class BumpAction(Action):
    """Move or attack, depending on what occupies the destination."""

    def __init__(self, dx: int, dy: int) -> None:
        self.dx = dx
        self.dy = dy

    def perform(self, engine: Engine, entity: Entity) -> int:
        dest_x = entity.x + self.dx
        dest_y = entity.y + self.dy

        from game.helpers import is_diagonal_blocked

        if is_diagonal_blocked(engine.game_map, entity.x, entity.y, self.dx, self.dy):
            return 0

        target = engine.game_map.get_blocking_entity(dest_x, dest_y)
        if target and target.fighter:
            return MeleeAction(target).perform(engine, entity)

        # Check for airlock→space transition
        if engine.game_map.in_bounds(dest_x, dest_y):
            from world import tile_types

            dest_tid = int(engine.game_map.tiles["tile_id"][dest_x, dest_y])
            space_tid = int(tile_types.space["tile_id"])
            airlock_tid = int(tile_types.airlock_floor["tile_id"])
            ext_open_tid = int(tile_types.airlock_ext_open["tile_id"])
            hull_breach_tid = int(tile_types.hull_breach["tile_id"])
            cur_tid = int(engine.game_map.tiles["tile_id"][entity.x, entity.y])
            # Allow stepping into space from airlock floor, open exterior
            # airlock door, or hull breach
            on_airlock = cur_tid in (airlock_tid, ext_open_tid, hull_breach_tid)
            if dest_tid == space_tid and on_airlock:
                # Step into the void
                entity.x = dest_x
                entity.y = dest_y
                entity.drifting = True
                entity.drift_direction = (self.dx, self.dy)
                if entity is engine.player:
                    engine.message_log.add_message("You step into the void...", HAZARD_VOID)
                return 1

        return MovementAction(self.dx, self.dy).perform(engine, entity)


class PickupAction(Action):
    def perform(self, engine: Engine, entity: Entity) -> int:
        items = engine.game_map.get_items_at(entity.x, entity.y)
        if not items:
            engine.message_log.add_message("Nothing to pick up.", DARK_GRAY)
            return 0
        item = items[0]
        if not entity.can_carry():
            engine.message_log.add_message("Inventory full.", WARNING)
            return 0
        entity.inventory.append(item)
        engine.game_map.entities.remove(item)
        if entity is engine.player:
            engine.message_log.add_message(f"You pick up the {item.name}.", PICKUP)
        else:
            engine.message_log.add_message(f"The {entity.name} picks up the {item.name}.", PICKUP)
        return 1


class DropAction(Action):
    def __init__(self, item_index: int) -> None:
        self.item_index = item_index

    def _find_drop_tile(self, engine: Engine, entity: Entity) -> tuple | None:
        """Find a valid tile to drop an item: entity tile first, then adjacent."""
        from game.helpers import find_drop_tile

        return find_drop_tile(engine.game_map, entity.x, entity.y)

    def perform(self, engine: Engine, entity: Entity) -> int:
        if self.item_index < 0 or self.item_index >= len(entity.inventory):
            return 0
        tile = self._find_drop_tile(engine, entity)
        if tile is None:
            engine.message_log.add_message("No space to drop that.", WARNING)
            return 0
        item = entity.inventory.pop(self.item_index)
        # Unequip if equipped
        if entity.loadout and entity.loadout.has_item(item):
            entity.loadout.unequip(item)
            from game.loadout import recalc_melee_power

            if entity.fighter:
                recalc_melee_power(entity)
        item.x, item.y = tile
        engine.game_map.entities.append(item)
        engine.game_map.invalidate_entity_index()
        engine.message_log.add_message(f"You drop the {item.name}.", NEUTRAL)
        return 1


def _adjacent_interactable(engine: Engine, entity: Entity) -> Entity | None:
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

    def __init__(self, dx: int = 0, dy: int = 0) -> None:
        self.dx = dx
        self.dy = dy

    def perform(self, engine: Engine, entity: Entity) -> int:
        if self.dx or self.dy:
            target = engine.game_map.get_interactable_at(entity.x + self.dx, entity.y + self.dy)
        else:
            target = _adjacent_interactable(engine, entity)
        if not target or not target.interactable:
            engine.message_log.add_message("Nothing to interact with here.", DARK_GRAY)
            return 0

        ih = target.interactable
        name = target.name

        loot = ih.get("loot")
        has_loot = loot and isinstance(loot, dict) and all(k in loot for k in ("char", "color", "name"))

        # Block opening if inventory is full and there's loot to pick up
        if has_loot and not entity.can_carry():
            engine.message_log.add_message("Inventory full.", WARNING)
            return 0

        # Trigger hazard if present (and not scanned/safe)
        if ih.get("hazard") and not ih.get("scanned"):
            from game.hazards import trigger_hazard

            trigger_hazard(engine, ih["hazard"], name)
            # If the hazard killed the entity, skip loot and bail out
            if entity.fighter and entity.fighter.hp <= 0:
                if target in engine.game_map.entities:
                    engine.game_map.entities.remove(target)
                return 1
        elif ih.get("hazard") and ih.get("scanned"):
            engine.message_log.add_message(f"Your scan helps you bypass the hazard on the {name}.", INTERACT_SAFE)

        # Loot
        if has_loot:
            from data.items import build_item_data
            from game.entity import Entity as _Entity

            item_data = build_item_data(loot)
            item_ent = _Entity(
                x=entity.x,
                y=entity.y,
                char=loot["char"],
                color=loot["color"],
                name=loot["name"],
                blocks_movement=False,
                item=item_data,
            )
            entity.inventory.append(item_ent)
            engine.message_log.add_message(f"You search the {name}... Found {loot['name']}!", INTERACT_LOOT)
        else:
            engine.message_log.add_message(f"You search the {name}. Nothing useful.", INTERACT_EMPTY)

        # Remove interactable after use
        if target in engine.game_map.entities:
            engine.game_map.entities.remove(target)
        return 1


class ScanAction(Action):
    """Area scan using equipped scanner. Populates engine.scan_results. Costs 1 turn."""

    def __init__(self, scanner: Entity | None = None) -> None:
        self.scanner = scanner

    def perform(self, engine: Engine, entity: Entity) -> int:
        from game.scanner import perform_area_scan

        results = perform_area_scan(engine, entity, scanner=self.scanner)
        if results is None:
            return 0
        import time

        engine.scan_results = results
        engine.scan_glow = {
            "cx": entity.x,
            "cy": entity.y,
            "radius": results.scanner_range,
            "start_time": time.time(),
        }
        n = len(results.entries)
        if n:
            engine.message_log.add_message(
                f"Scan complete: {n} contact{'s' if n != 1 else ''}.",
                SCAN_MSG,
            )
        else:
            engine.message_log.add_message("Scan complete: all clear.", SCAN_MSG)
        return 1


class ToggleDoorAction(Action):
    """Open or close a door at a cardinal offset from the entity."""

    def __init__(self, dx: int, dy: int) -> None:
        self.dx = dx
        self.dy = dy

    def perform(self, engine: Engine, entity: Entity) -> int:
        from game.helpers import get_door_tile_ids
        from world import tile_types

        tx, ty = entity.x + self.dx, entity.y + self.dy
        if not engine.game_map.in_bounds(tx, ty):
            engine.message_log.add_message("No door there.", DARK_GRAY)
            return 0

        tile_id = int(engine.game_map.tiles["tile_id"][tx, ty])
        closed_id, open_id = get_door_tile_ids()
        ext_closed_id = int(tile_types.airlock_ext_closed["tile_id"])
        ext_open_id = int(tile_types.airlock_ext_open["tile_id"])

        if tile_id in (ext_closed_id, ext_open_id):
            engine.message_log.add_message("The exterior door is controlled by a switch.", WARNING)
            return 0
        elif tile_id == closed_id:
            engine.game_map.tiles[tx, ty] = tile_types.door_open
            engine.game_map.invalidate_hazards()
            engine.message_log.add_message("You open the door.", NEUTRAL)
            return 1
        elif tile_id == open_id:
            # Don't close if an entity is standing there
            if engine.game_map.get_blocking_entity(tx, ty):
                engine.message_log.add_message("Something is in the way.", WARNING)
                return 0
            if engine.game_map.get_items_at(tx, ty):
                engine.message_log.add_message("Something is in the way.", WARNING)
                return 0
            engine.game_map.tiles[tx, ty] = tile_types.door_closed
            engine.game_map.invalidate_hazards()
            engine.message_log.add_message("You close the door.", NEUTRAL)
            return 1
        else:
            engine.message_log.add_message("No door there.", DARK_GRAY)
            return 0


class RangedAction(Action):
    """Fire a ranged weapon at a target."""

    def __init__(self, target: Entity) -> None:
        self.target = target

    def perform(self, engine: Engine, entity: Entity) -> int:
        if not entity.fighter or not self.target.fighter:
            return 0

        from game.helpers import get_equipped_ranged_weapon, has_ranged_weapon

        weapon = get_equipped_ranged_weapon(entity)
        if not weapon:
            if has_ranged_weapon(entity):
                engine.message_log.add_message("Out of ammo!", WARNING)
            else:
                engine.message_log.add_message("No ranged weapon equipped.", WARNING)
            return 0

        # Check range
        from game.helpers import chebyshev

        distance = chebyshev(entity.x, entity.y, self.target.x, self.target.y)
        max_range = weapon.item.get("range", 5)
        if distance > max_range:
            engine.message_log.add_message("Target out of range.", WARNING)
            return 0

        # Check FOV
        if not engine.game_map.visible[self.target.x, self.target.y]:
            engine.message_log.add_message("Target not visible.", WARNING)
            return 0

        # Check line-of-sight (no non-walkable tiles in the way)
        from game.helpers import has_clear_shot

        if not has_clear_shot(engine.game_map, entity.x, entity.y, self.target.x, self.target.y):
            engine.message_log.add_message("No clear shot — path blocked.", WARNING)
            return 0

        # Consume ammo (guard against negative)
        if weapon.item.get("ammo", 0) <= 0:
            engine.message_log.add_message("Out of ammo!", WARNING)
            return 0
        weapon.item["ammo"] = max(0, weapon.item["ammo"] - 1)

        damage = _calc_damage(engine, entity, self.target, weapon.item["value"])
        _attack_message(engine, entity, self.target, "shoot", "shoots", damage, PLAYER_RANGED, ENEMY_RANGED)

        _apply_damage_and_death(engine, entity, self.target, damage)
        return 1


class TakeReactorCoreAction(Action):
    """Extract a reactor core from an adjacent tile."""

    def __init__(self, dx: int, dy: int) -> None:
        self.dx = dx
        self.dy = dy

    def perform(self, engine: Engine, entity: Entity) -> int:
        from world import tile_types

        tx, ty = entity.x + self.dx, entity.y + self.dy
        if not engine.game_map.in_bounds(tx, ty):
            return 0

        tile_id = int(engine.game_map.tiles["tile_id"][tx, ty])
        if tile_id != int(tile_types.reactor_core["tile_id"]):
            return 0

        if getattr(engine.current_state, "explore_ship", False):
            engine.message_log.add_message(
                "This is your ship's power core. You cannot remove it.",
                (200, 150, 100),
            )
            return 0

        if not entity.can_carry():
            engine.message_log.add_message("Inventory full.", WARNING)
            return 0

        # Replace tile with floor
        engine.game_map.tiles[tx, ty] = tile_types.floor

        # Remove light source at that position
        engine.game_map.light_sources = [ls for ls in engine.game_map.light_sources if (ls.x, ls.y) != (tx, ty)]
        engine.game_map.invalidate_hazards()

        # Create reactor core item — Dreadnought location yields special core
        from game.entity import Entity as _Entity

        loc = getattr(engine.current_state, "location", None)
        is_dreadnought = getattr(loc, "is_dreadnought", False)
        if is_dreadnought:
            name, color = "Dreadnought Core", (255, 50, 50)
            item_data = {"type": "dreadnought_core", "value": 99}
            msg = "You extract the Dreadnought's reactor core!"
        else:
            name, color = "Reactor Core", (180, 80, 255)
            item_data = {"type": "reactor_core", "value": 5}
            msg = "You extract the reactor core."
        core = _Entity(
            x=entity.x,
            y=entity.y,
            char="\xea",
            color=color,
            name=name,
            blocks_movement=False,
            item=item_data,
        )
        entity.inventory.append(core)
        engine.message_log.add_message(msg, color)
        return 1


class ToggleSwitchAction(Action):
    """Toggle an airlock switch, opening or closing the linked exterior door."""

    def __init__(self, dx: int, dy: int) -> None:
        self.dx = dx
        self.dy = dy

    def perform(self, engine: Engine, entity: Entity) -> int:
        from world import tile_types

        sx, sy = entity.x + self.dx, entity.y + self.dy
        if not engine.game_map.in_bounds(sx, sy):
            return 0

        tile_id = int(engine.game_map.tiles["tile_id"][sx, sy])
        off_id = int(tile_types.airlock_switch_off["tile_id"])
        on_id = int(tile_types.airlock_switch_on["tile_id"])

        if tile_id not in (off_id, on_id):
            engine.message_log.add_message("No switch there.", DARK_GRAY)
            return 0

        # Find linked airlock
        airlock = None
        for al in engine.game_map.airlocks:
            if al.get("switch") == (sx, sy):
                airlock = al
                break

        if airlock is None:
            engine.message_log.add_message("The switch doesn't seem connected.", INTERACT_EMPTY)
            return 0

        ex, ey = airlock["exterior_door"]

        if tile_id == off_id:
            # Turn on: open exterior door
            engine.game_map.tiles[sx, sy] = tile_types.airlock_switch_on
            engine.game_map.tiles[ex, ey] = tile_types.airlock_ext_open
            engine.game_map.invalidate_hazards()
            engine.message_log.add_message("You flip the switch. The exterior door grinds open.", WARNING)
        else:
            # Turn off: close exterior door
            if engine.game_map.get_blocking_entity(ex, ey):
                engine.message_log.add_message("Something is blocking the exterior door.", WARNING)
                return 0
            engine.game_map.tiles[sx, sy] = tile_types.airlock_switch_off
            engine.game_map.tiles[ex, ey] = tile_types.airlock_ext_closed
            engine.game_map.invalidate_hazards()
            engine.message_log.add_message("You flip the switch. The exterior door seals shut.", NEUTRAL)
            # Warn if vacuum persists due to other sources (hull breaches)
            engine.game_map.recalculate_hazards()
            overlay = engine.game_map.hazard_overlays.get("vacuum")
            if overlay is not None and entity is engine.player and overlay[entity.x, entity.y]:
                engine.message_log.add_message(
                    "Atmosphere not restored. Hull breaches detected nearby.",
                    WARNING,
                )
        return 1
