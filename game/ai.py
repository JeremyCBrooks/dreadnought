"""Enemy AI behaviours."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity


class HostileAI:
    """Chase the player when visible, attack when adjacent, otherwise wander."""

    def _has_move_cooldown(self, owner: Entity, engine: Engine) -> bool:
        """Check low-gravity movement cooldown for organic entities.

        Returns True if the entity must skip movement this turn.
        """
        from game.environment import has_low_gravity
        if not owner.organic or not has_low_gravity(engine):
            owner.move_cooldown = 0
            return False
        if owner.move_cooldown > 0:
            owner.move_cooldown -= 1
            return True
        return False

    def _apply_move_cooldown(self, owner: Entity, engine: Engine) -> None:
        """Set movement cooldown after a successful move in low gravity."""
        from game.environment import has_low_gravity
        if owner.organic and has_low_gravity(engine):
            owner.move_cooldown = 1

    def perform(self, owner: Entity, engine: Engine) -> None:
        game_map = engine.game_map
        target = engine.player

        if not game_map.visible[owner.x, owner.y]:
            self._wander(owner, engine)
            return

        dx = target.x - owner.x
        dy = target.y - owner.y
        distance = max(abs(dx), abs(dy))

        # Adjacent: melee attack
        if distance <= 1:
            from game.actions import MeleeAction
            MeleeAction(target).perform(engine, owner)
            return

        # Check for ranged weapon
        from game.actions import _get_equipped_ranged_weapon
        weapon = _get_equipped_ranged_weapon(owner)
        if weapon:
            max_range = weapon.item.get("range", 5)
            if distance <= max_range:
                from game.actions import RangedAction
                RangedAction(target).perform(engine, owner)
                return

        # Movement cooldown: organic entities in low gravity skip every other move
        if self._has_move_cooldown(owner, engine):
            return

        # Chase
        step_x = (1 if dx > 0 else -1) if dx != 0 else 0
        step_y = (1 if dy > 0 else -1) if dy != 0 else 0

        for sx, sy in [(step_x, step_y), (step_x, 0), (0, step_y)]:
            if sx == 0 and sy == 0:
                continue
            nx, ny = owner.x + sx, owner.y + sy
            if game_map.is_walkable(nx, ny) and not game_map.get_blocking_entity(nx, ny):
                owner.x = nx
                owner.y = ny
                self._apply_move_cooldown(owner, engine)
                return

    def _wander(self, owner: Entity, engine: Engine) -> None:
        """Move to a random adjacent walkable tile."""
        if self._has_move_cooldown(owner, engine):
            return
        game_map = engine.game_map
        directions = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        random.shuffle(directions)
        for dx, dy in directions:
            nx, ny = owner.x + dx, owner.y + dy
            if game_map.is_walkable(nx, ny) and not game_map.get_blocking_entity(nx, ny):
                owner.x = nx
                owner.y = ny
                self._apply_move_cooldown(owner, engine)
                return
