"""Enemy AI behaviours — 4-state creature AI with pathfinding."""
from __future__ import annotations

import random
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity

# AI config field defaults (used when ai_config is empty/missing fields)
_DEFAULTS = {
    "ai_initial_state": "wandering",
    "aggro_distance": 8,
    "sleep_aggro_distance": 3,
    "can_open_doors": False,
    "flee_threshold": 0.0,
    "memory_turns": 15,
    "vision_radius": 8,
    "move_speed": 4,
}

ACTION_COST = 4  # energy needed per movement action


class CreatureAI:
    """4-state AI: sleeping, wandering, hunting, fleeing."""

    def __init__(self) -> None:
        self._cached_cost: "np.ndarray | None" = None

    # ---- energy-based movement speed ----

    def _accumulate_energy(self, owner: Entity, engine: Engine) -> None:
        """Grant energy for this turn based on move_speed and environment."""
        from game.environment import has_low_gravity
        speed = self._cfg(owner, "move_speed")
        if owner.organic and has_low_gravity(engine):
            speed = speed // 2
        owner.ai_energy = min(owner.ai_energy + speed, ACTION_COST * 2)

    def _can_spend_move(self, owner: Entity, engine: Engine) -> bool:
        """Check if the creature has enough energy to move. Spend it if so."""
        if owner.ai_energy >= ACTION_COST:
            owner.ai_energy -= ACTION_COST
            return True
        return False

    # ---- config helper ----

    def _cfg(self, owner: Entity, key: str):
        return owner.ai_config.get(key, _DEFAULTS[key])

    # ---- vision ----

    def _can_see_player(self, owner: Entity, engine: Engine) -> bool:
        import tcod.map
        from game.helpers import chebyshev
        target = engine.player
        vision_radius = self._cfg(owner, "vision_radius")
        if chebyshev(owner.x, owner.y, target.x, target.y) > vision_radius:
            return False
        cache_key = (owner.x, owner.y, vision_radius)
        fov_cache = engine.game_map._fov_cache
        fov = fov_cache.get(cache_key)
        if fov is None:
            fov = tcod.map.compute_fov(
                engine.game_map.tiles["transparent"],
                (owner.x, owner.y),
                radius=vision_radius,
            )
            fov_cache[cache_key] = fov
        return bool(fov[target.x, target.y])

    # ---- pathfinding ----

    def _compute_path(
        self, owner: Entity, engine: Engine, goal: Tuple[int, int],
    ) -> List[Tuple[int, int]]:
        import tcod.path
        from game.helpers import is_diagonal_blocked

        cost = self._build_cost(owner, engine)
        # Ensure goal tile is passable in the cost array
        cost[goal[0], goal[1]] = max(cost[goal[0], goal[1]], 1)

        graph = tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=3)
        pf = tcod.path.Pathfinder(graph)
        pf.add_root((owner.x, owner.y))
        path = pf.path_to(goal).tolist()
        # Remove the starting position
        if path and tuple(path[0]) == (owner.x, owner.y):
            path = path[1:]
        result = [tuple(p) for p in path]

        # Detect bogus paths: if first step is not adjacent, goal is unreachable
        if result and (abs(result[0][0] - owner.x) > 1 or abs(result[0][1] - owner.y) > 1):
            return []

        # If first step is a door-blocked diagonal, recompute cardinal-only
        if result:
            nx, ny = result[0]
            dx, dy = nx - owner.x, ny - owner.y
            if is_diagonal_blocked(engine.game_map, owner.x, owner.y, dx, dy):
                graph2 = tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=0)
                pf2 = tcod.path.Pathfinder(graph2)
                pf2.add_root((owner.x, owner.y))
                path2 = pf2.path_to(goal).tolist()
                if path2 and tuple(path2[0]) == (owner.x, owner.y):
                    path2 = path2[1:]
                result = [tuple(p) for p in path2]

        return result

    def _move_along_path(
        self, owner: Entity, engine: Engine, path: List[Tuple[int, int]],
    ) -> bool:
        if not path:
            return False
        nx, ny = path[0]
        # Sanity check: step must be adjacent (1 tile max)
        if abs(nx - owner.x) > 1 or abs(ny - owner.y) > 1:
            return False
        gm = engine.game_map

        # Check for closed door
        from game.helpers import is_door_closed
        from world import tile_types
        if is_door_closed(gm, nx, ny):
            if self._cfg(owner, "can_open_doors"):
                gm.tiles[nx, ny] = tile_types.door_open
                gm._hazards_dirty = True
                gm._fov_cache.clear()
                engine.message_log.add_message(
                    f"The {owner.name} opens a door.", (200, 200, 200)
                )
                return True  # consumed turn opening door
            return False  # can't open

        from game.helpers import is_diagonal_blocked
        if is_diagonal_blocked(gm, owner.x, owner.y, nx - owner.x, ny - owner.y):
            return False

        if gm.is_walkable(nx, ny) and not gm.get_blocking_entity(nx, ny):
            owner.x = nx
            owner.y = ny
            gm.invalidate_entity_index()
            return True
        return False

    # ---- cost array (shared between hunting and fleeing) ----

    def _build_cost(self, owner: Entity, engine: Engine) -> "np.ndarray":
        if self._cached_cost is not None:
            return self._cached_cost.copy()
        import numpy as np
        gm = engine.game_map
        cost = np.array(gm.tiles["walkable"], dtype=np.int8)
        if self._cfg(owner, "can_open_doors"):
            from game.helpers import get_door_tile_ids
            closed_id, _ = get_door_tile_ids()
            door_mask = gm.tiles["tile_id"] == closed_id
            cost[door_mask] = 2
        for e in gm.entities:
            if e is owner or e is engine.player:
                continue
            if e.blocks_movement:
                cost[e.x, e.y] = 0
        self._cached_cost = cost
        return cost.copy()

    # ---- fleeing movement ----

    def _compute_flee_goal(
        self, owner: Entity, engine: Engine,
    ) -> Optional[Tuple[int, int]]:
        """Pick the best reachable tile that maximises pathfinding distance from player."""
        import tcod.path
        import numpy as np

        cost = self._build_cost(owner, engine)
        gm = engine.game_map
        player = engine.player

        # Dijkstra from player — dist[x,y] = travel cost from player to (x,y)
        graph = tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=3)
        pf = tcod.path.Pathfinder(graph)
        pf.add_root((player.x, player.y))
        pf.resolve()
        dist = pf.distance

        # Search within a radius around the creature for the farthest reachable tile
        search_radius = max(10, self._cfg(owner, "aggro_distance") * 2)
        best_cost = dist[owner.x, owner.y]
        best_tiles: List[Tuple[int, int]] = []

        x_lo = max(1, owner.x - search_radius)
        x_hi = min(gm.width - 1, owner.x + search_radius + 1)
        y_lo = max(1, owner.y - search_radius)
        y_hi = min(gm.height - 1, owner.y + search_radius + 1)

        for x in range(x_lo, x_hi):
            for y in range(y_lo, y_hi):
                d = dist[x, y]
                # Skip unreachable tiles (max int = unreachable in tcod)
                if d >= 0x7FFF_FFFF:
                    continue
                if d > best_cost:
                    best_cost = d
                    best_tiles = [(x, y)]
                elif d == best_cost and (x, y) != (owner.x, owner.y):
                    best_tiles.append((x, y))

        if best_tiles:
            return random.choice(best_tiles)
        return None

    def _flee_pathfind(self, owner: Entity, engine: Engine) -> bool:
        """Pathfind toward the flee goal. Returns True if an action was taken."""
        goal = self._compute_flee_goal(owner, engine)
        if goal is None:
            return False
        path = self._compute_path(owner, engine, goal)
        return self._move_along_path(owner, engine, path)

    # ---- wander (patrol) ----

    def _pick_wander_goal(
        self, owner: Entity, engine: Engine,
    ) -> Optional[Tuple[int, int]]:
        """Pick a random walkable, reachable tile as a patrol goal.

        Prefers hazard-free tiles, but falls back to hazardous tiles so
        that enemies in fully-hazardous areas don't freeze.
        """
        import numpy as np
        import tcod.path

        cost = self._build_cost(owner, engine)
        graph = tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=3)
        pf = tcod.path.Pathfinder(graph)
        pf.add_root((owner.x, owner.y))
        pf.resolve()
        dist = pf.distance

        # Reachable tiles: finite distance
        reachable = dist < 0x7FFF_FFFF
        reachable[owner.x, owner.y] = False

        # Prefer non-hazardous tiles
        gm = engine.game_map
        safe = reachable.copy()
        for overlay in gm.hazard_overlays.values():
            safe &= ~overlay

        candidates = np.argwhere(safe)
        if len(candidates) == 0:
            # Fall back to any reachable tile (including hazardous)
            candidates = np.argwhere(reachable)
        if len(candidates) == 0:
            return None
        chosen = candidates[random.randint(0, len(candidates) - 1)]
        return (int(chosen[0]), int(chosen[1]))

    def _wander(self, owner: Entity, engine: Engine) -> None:
        if not self._can_spend_move(owner, engine):
            return
        from game.helpers import chebyshev
        # Pick a patrol goal if we don't have one
        if owner.ai_wander_goal is None:
            owner.ai_wander_goal = self._pick_wander_goal(owner, engine)
        if owner.ai_wander_goal is None:
            return  # no reachable goal found
        # Already at goal — pick a new one
        if (owner.x, owner.y) == owner.ai_wander_goal:
            owner.ai_wander_goal = self._pick_wander_goal(owner, engine)
            if owner.ai_wander_goal is None:
                return
        # Pathfind toward the goal
        path = self._compute_path(owner, engine, owner.ai_wander_goal)
        if not path or not self._move_along_path(owner, engine, path):
            # Stuck — pick a new goal next turn
            owner.ai_wander_goal = None

    # ---- attack ----

    def _attack(self, owner: Entity, engine: Engine) -> None:
        from game.helpers import chebyshev
        target = engine.player
        distance = chebyshev(owner.x, owner.y, target.x, target.y)

        if distance <= 1:
            from game.actions import MeleeAction
            MeleeAction(target).perform(engine, owner)
            owner.ai_energy = 0
            return

        from game.helpers import get_equipped_ranged_weapon
        weapon = get_equipped_ranged_weapon(owner)
        if weapon:
            max_range = weapon.item.get("range", 5)
            if distance <= max_range:
                from game.actions import RangedAction
                RangedAction(target).perform(engine, owner)
                owner.ai_energy = 0
                return

    # ---- main perform ----

    def perform(self, owner: Entity, engine: Engine) -> None:
        self._accumulate_energy(owner, engine)
        self._cached_cost = None  # clear per-turn cost cache

        state = owner.ai_state
        if state == "sleeping":
            self._do_sleeping(owner, engine)
        elif state == "wandering":
            self._do_wandering(owner, engine)
        elif state == "hunting":
            self._do_hunting(owner, engine)
        elif state == "fleeing":
            self._do_fleeing(owner, engine)

    def _do_sleeping(self, owner: Entity, engine: Engine) -> None:
        if self._can_see_player(owner, engine):
            from game.helpers import chebyshev
            dist = chebyshev(owner.x, owner.y, engine.player.x, engine.player.y)
            if dist <= self._cfg(owner, "sleep_aggro_distance"):
                owner.ai_state = "hunting"
                owner.ai_target = (engine.player.x, engine.player.y)
                owner.ai_turns_since_seen = 0
                owner.ai_stuck_turns = 0
                # Reset banked energy so the creature doesn't get
                # extra moves from energy accumulated while sleeping.
                owner.ai_energy = 0
                engine.message_log.add_message(
                    f"The {owner.name} wakes up!", (255, 200, 100)
                )
                self._do_hunting(owner, engine)

    def _do_wandering(self, owner: Entity, engine: Engine) -> None:
        if self._can_see_player(owner, engine):
            from game.helpers import chebyshev
            dist = chebyshev(owner.x, owner.y, engine.player.x, engine.player.y)
            if dist <= self._cfg(owner, "aggro_distance"):
                owner.ai_state = "hunting"
                owner.ai_target = (engine.player.x, engine.player.y)
                owner.ai_turns_since_seen = 0
                owner.ai_wander_goal = None
                self._do_hunting(owner, engine)
                return
        self._wander(owner, engine)

    def _do_hunting(self, owner: Entity, engine: Engine) -> None:
        from game.helpers import chebyshev
        target = engine.player

        # Check flee threshold
        flee_threshold = self._cfg(owner, "flee_threshold")
        if flee_threshold > 0 and owner.fighter:
            hp_ratio = owner.fighter.hp / max(1, owner.fighter.max_hp)
            if hp_ratio <= flee_threshold:
                owner.ai_state = "fleeing"
                self._do_fleeing(owner, engine)
                return

        # Update vision
        can_see = self._can_see_player(owner, engine)
        if can_see:
            owner.ai_target = (target.x, target.y)
            owner.ai_turns_since_seen = 0
        else:
            owner.ai_turns_since_seen += 1
            if owner.ai_turns_since_seen > self._cfg(owner, "memory_turns"):
                owner.ai_state = self._cfg(owner, "ai_initial_state")
                owner.ai_target = None
                return

        if owner.ai_target is None:
            self._wander(owner, engine)
            return

        # Use real player pos only when we have current LOS
        if can_see:
            goal_x, goal_y = target.x, target.y
        else:
            goal_x, goal_y = owner.ai_target
        distance = chebyshev(owner.x, owner.y, goal_x, goal_y)

        # Adjacent to real player: melee attack (not gated by energy)
        real_dist = chebyshev(owner.x, owner.y, target.x, target.y)
        if real_dist <= 1:
            self._attack(owner, engine)
            return

        # Ranged attack if we can see the player (not gated by energy)
        if can_see:
            from game.helpers import get_equipped_ranged_weapon
            weapon = get_equipped_ranged_weapon(owner)
            if weapon:
                max_range = weapon.item.get("range", 5)
                if real_dist <= max_range:
                    self._attack(owner, engine)
                    return

        # At last-known position but player not here — give up target
        if not can_see and distance == 0:
            owner.ai_target = None
            return

        # Movement — spend energy, possibly multiple steps for fast creatures
        moved = False
        while self._can_spend_move(owner, engine):
            path = self._compute_path(owner, engine, owner.ai_target)
            if not self._move_along_path(owner, engine, path):
                self._simple_chase(owner, engine, owner.ai_target)
                break
            moved = True
            # After moving, check if now adjacent → attack and stop
            real_dist = chebyshev(owner.x, owner.y, target.x, target.y)
            if real_dist <= 1:
                self._attack(owner, engine)
                break

        # Track consecutive turns where we couldn't move toward the target.
        # Handles enemies that can see the player (e.g. through a window)
        # but have no walkable path — without this they'd freeze in hunting.
        if moved or real_dist <= 1:
            owner.ai_stuck_turns = 0
        else:
            owner.ai_stuck_turns += 1
            if owner.ai_stuck_turns > self._cfg(owner, "memory_turns"):
                owner.ai_state = self._cfg(owner, "ai_initial_state")
                owner.ai_target = None

    def _simple_chase(
        self, owner: Entity, engine: Engine, goal: Tuple[int, int],
    ) -> None:
        from game.helpers import is_diagonal_blocked
        dx = goal[0] - owner.x
        dy = goal[1] - owner.y
        step_x = (1 if dx > 0 else -1) if dx != 0 else 0
        step_y = (1 if dy > 0 else -1) if dy != 0 else 0
        gm = engine.game_map
        for sx, sy in [(step_x, step_y), (step_x, 0), (0, step_y)]:
            if sx == 0 and sy == 0:
                continue
            if is_diagonal_blocked(gm, owner.x, owner.y, sx, sy):
                continue
            nx, ny = owner.x + sx, owner.y + sy
            if gm.is_walkable(nx, ny) and not gm.get_blocking_entity(nx, ny):
                owner.x = nx
                owner.y = ny
                gm.invalidate_entity_index()
                return

    def _do_fleeing(self, owner: Entity, engine: Engine) -> None:
        from game.helpers import chebyshev
        target = engine.player
        dist = chebyshev(owner.x, owner.y, target.x, target.y)
        aggro = self._cfg(owner, "aggro_distance")

        if dist > 2 * aggro:
            owner.ai_state = "wandering"
            owner.ai_target = None
            owner.ai_turns_since_seen = 0
            return

        # Movement — spend energy, possibly multiple steps for fast creatures
        while self._can_spend_move(owner, engine):
            if not self._flee_pathfind(owner, engine):
                # No escape route — fight if adjacent
                if dist <= 1:
                    self._attack(owner, engine)
                break


# Backward compatibility alias
HostileAI = CreatureAI
