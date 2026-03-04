"""Enemy AI behaviours."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity


class HostileAI:
    """Chase the player when visible, attack when adjacent, otherwise wander."""

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
                return

    def _wander(self, owner: Entity, engine: Engine) -> None:
        """Move to a random adjacent walkable tile."""
        game_map = engine.game_map
        directions = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        random.shuffle(directions)
        for dx, dy in directions:
            nx, ny = owner.x + dx, owner.y + dy
            if game_map.is_walkable(nx, ny) and not game_map.get_blocking_entity(nx, ny):
                owner.x = nx
                owner.y = ny
                return
