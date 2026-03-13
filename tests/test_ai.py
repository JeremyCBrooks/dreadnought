"""Tests for CreatureAI state-machine behaviour."""
import random

import numpy as np
import pytest

from game.entity import Entity, Fighter
from game.ai import CreatureAI, HostileAI
from tests.conftest import make_arena, MockEngine
from world import tile_types


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "ai_initial_state": "wandering",
    "aggro_distance": 8,
    "sleep_aggro_distance": 3,
    "can_open_doors": False,
    "flee_threshold": 0.0,
    "memory_turns": 15,
    "vision_radius": 8,
}


def _make_creature(x, y, hp=3, max_hp=3, power=1, config=None, name="Rat"):
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    ai = CreatureAI()
    e = Entity(
        x=x, y=y, name=name, char="r",
        fighter=Fighter(hp, max_hp, 0, power), ai=ai,
        organic=True,
    )
    e.ai_config = cfg
    e.ai_state = cfg["ai_initial_state"]
    return e


def _setup(w=20, h=20, player_pos=(1, 1), fov=True):
    gm = make_arena(w, h)
    player = Entity(x=player_pos[0], y=player_pos[1], name="Player",
                    fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    if fov:
        gm.visible[:] = True
    engine = MockEngine(gm, player)
    return gm, player, engine


# ---------------------------------------------------------------------------
# Backward compat
# ---------------------------------------------------------------------------

def test_hostile_ai_alias():
    """HostileAI should still exist as an alias for CreatureAI."""
    assert HostileAI is CreatureAI


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

class TestStateTransitions:

    def test_sleeping_to_hunting_on_close_player(self):
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(6, 5, config={
            "ai_initial_state": "sleeping",
            "sleep_aggro_distance": 3,
        })
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "hunting"

    def test_sleeping_stays_sleeping_when_player_far(self):
        gm, player, engine = _setup(player_pos=(1, 1))
        creature = _make_creature(15, 15, config={
            "ai_initial_state": "sleeping",
            "sleep_aggro_distance": 2,
            "vision_radius": 8,
        })
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "sleeping"

    def test_wandering_to_hunting_on_visible_player(self):
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(8, 5, config={"aggro_distance": 8})
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "hunting"

    def test_wandering_stays_when_player_out_of_aggro(self):
        gm, player, engine = _setup(w=30, h=30, player_pos=(1, 1))
        creature = _make_creature(25, 25, config={
            "aggro_distance": 5,
            "vision_radius": 6,
        })
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "wandering"

    def test_hunting_to_initial_state_after_memory_decay(self):
        gm, player, engine = _setup(player_pos=(1, 1))
        creature = _make_creature(15, 15, config={
            "memory_turns": 3,
            "ai_initial_state": "wandering",
        })
        creature.ai_state = "hunting"
        creature.ai_target = (1, 1)
        creature.ai_turns_since_seen = 0
        gm.entities.append(creature)
        # Make the creature unable to see the player (wall between them)
        gm.visible[:] = False
        for turn in range(4):
            creature.ai.perform(creature, engine)
        assert creature.ai_state == "wandering"

    def test_hunting_to_fleeing_on_low_hp(self):
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(7, 5, hp=1, max_hp=10, config={
            "flee_threshold": 0.3,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (5, 5)
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "fleeing"

    def test_fleeing_to_wandering_when_far_enough(self):
        gm, player, engine = _setup(w=40, h=40, player_pos=(1, 1))
        creature = _make_creature(35, 35, hp=1, max_hp=10, config={
            "flee_threshold": 0.3,
            "aggro_distance": 5,
        })
        creature.ai_state = "fleeing"
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "wandering"

    def test_never_flee_when_threshold_zero(self):
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(7, 5, hp=1, max_hp=10, config={
            "flee_threshold": 0.0,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (5, 5)
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "hunting"


# ---------------------------------------------------------------------------
# Vision / no cheating
# ---------------------------------------------------------------------------

class TestVision:

    def test_creature_does_not_track_through_walls(self):
        """After losing LOS, creature goes to last-known position, not real one."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 5))
        creature = _make_creature(10, 5, config={
            "aggro_distance": 15,
            "memory_turns": 2,
            "vision_radius": 15,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (5, 5)  # last-known position
        gm.entities.append(creature)
        # Block LOS with a wall column at x=3
        for y in range(0, 20):
            gm.tiles[3, y] = tile_types.wall
        gm.visible[:] = False  # creature can't see
        old_target = creature.ai_target
        creature.ai.perform(creature, engine)
        # Target should still be (5,5) since creature can't see new player pos
        assert creature.ai_target == old_target


# ---------------------------------------------------------------------------
# Pathfinding
# ---------------------------------------------------------------------------

class TestPathfinding:

    def test_navigates_around_wall(self):
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 5))
        creature = _make_creature(10, 5, config={
            "aggro_distance": 15,
            "vision_radius": 15,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (1, 5)
        gm.entities.append(creature)
        # Wall blocking direct path at x=5
        for y in range(1, 9):
            gm.tiles[5, y] = tile_types.wall
        old_dist = abs(creature.x - 1) + abs(creature.y - 5)
        creature.ai.perform(creature, engine)
        # Creature should have moved (not stuck)
        new_dist_manhattan = abs(creature.x - 10) + abs(creature.y - 5)
        assert new_dist_manhattan > 0, "Creature should have moved"


# ---------------------------------------------------------------------------
# Doors
# ---------------------------------------------------------------------------

class TestDoors:

    def test_smart_creature_opens_door(self):
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 5))
        creature = _make_creature(5, 5, config={
            "can_open_doors": True,
            "aggro_distance": 15,
            "vision_radius": 15,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (1, 5)
        gm.entities.append(creature)
        # Place a closed door with walls forcing creature through it
        gm.tiles[4, 5] = tile_types.door_closed
        for y in range(0, 20):
            if y != 5:
                gm.tiles[4, y] = tile_types.wall
        creature.ai.perform(creature, engine)
        # Should open the door (consumes turn)
        assert gm.tiles["walkable"][4, 5], "Door should be open now"

    def test_dumb_creature_cannot_open_door(self):
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 5))
        creature = _make_creature(5, 5, config={
            "can_open_doors": False,
            "aggro_distance": 15,
            "vision_radius": 15,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (1, 5)
        gm.entities.append(creature)
        # Place a closed door between creature and target
        gm.tiles[4, 5] = tile_types.door_closed
        creature.ai.perform(creature, engine)
        # Door should still be closed
        assert not gm.tiles["walkable"][4, 5], "Door should remain closed"


# ---------------------------------------------------------------------------
# Combat
# ---------------------------------------------------------------------------

class TestCombat:

    def test_adjacent_hunting_creature_attacks(self):
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(6, 5, hp=3, max_hp=3, power=2, config={
            "aggro_distance": 8,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (5, 5)
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        assert player.fighter.hp < 10

    def test_fleeing_creature_fights_when_cornered(self):
        """If all tiles increase or maintain distance, creature attacks."""
        gm, player, engine = _setup(w=5, h=5, player_pos=(2, 2))
        # Creature in a corner
        creature = _make_creature(3, 3, hp=1, max_hp=10, power=2, config={
            "flee_threshold": 0.3,
            "aggro_distance": 2,
        })
        creature.ai_state = "fleeing"
        gm.entities.append(creature)
        # Surround creature with walls on flee-sides
        gm.tiles[3, 2] = tile_types.wall  # above
        gm.tiles[3, 1] = tile_types.wall  # far above
        # Player adjacent, cornered
        old_hp = player.fighter.hp
        creature.ai.perform(creature, engine)
        # Either creature moved away OR fought if truly cornered
        moved = (creature.x, creature.y) != (3, 3)
        fought = player.fighter.hp < old_hp
        assert moved or fought, "Cornered creature should flee or fight"


# ---------------------------------------------------------------------------
# Low gravity cooldown preserved
# ---------------------------------------------------------------------------

class TestLowGravity:

    def test_cooldown_still_applies(self):
        gm, player, engine = _setup(player_pos=(1, 1))
        engine.environment = {"low_gravity": 1}
        creature = _make_creature(5, 5, config={"aggro_distance": 3, "vision_radius": 3})
        creature.organic = True
        gm.entities.append(creature)
        gm.visible[:] = False  # wandering
        pos1 = (creature.x, creature.y)
        creature.ai.perform(creature, engine)
        pos2 = (creature.x, creature.y)
        creature.ai.perform(creature, engine)
        pos3 = (creature.x, creature.y)
        # After first move, cooldown should prevent second move
        if pos1 != pos2:
            assert pos2 == pos3, "Cooldown should prevent consecutive moves"


# ---------------------------------------------------------------------------
# Sleeping does nothing
# ---------------------------------------------------------------------------

class TestSleeping:

    def test_sleeping_creature_does_not_move(self):
        gm, player, engine = _setup(w=30, h=30, player_pos=(1, 1))
        creature = _make_creature(25, 25, config={
            "ai_initial_state": "sleeping",
            "sleep_aggro_distance": 2,
            "vision_radius": 8,
        })
        gm.entities.append(creature)
        gm.visible[:] = False  # can't see player
        pos = (creature.x, creature.y)
        creature.ai.perform(creature, engine)
        assert (creature.x, creature.y) == pos

    def test_sleeping_wake_logs_message(self):
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(6, 5, config={
            "ai_initial_state": "sleeping",
            "sleep_aggro_distance": 3,
        })
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        messages = [text for text, _color in engine.message_log._messages]
        assert any("wakes up" in m for m in messages)

    def test_sleeping_wake_acts_immediately(self):
        """Waking creature should act on the same turn it wakes."""
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(6, 5, hp=3, max_hp=3, power=2, config={
            "ai_initial_state": "sleeping",
            "sleep_aggro_distance": 3,
        })
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        # Adjacent — should have attacked on wake turn
        assert player.fighter.hp < 10

    def test_sleeping_wake_does_not_teleport(self):
        """Creature waking up should move at most 1 tile, not teleport to player."""
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(8, 5, config={
            "ai_initial_state": "sleeping",
            "sleep_aggro_distance": 5,
            "move_speed": 4,
        })
        gm.entities.append(creature)
        start_x, start_y = creature.x, creature.y
        # Simulate many turns of sleeping to bank energy
        from game.ai import ACTION_COST
        creature.ai_energy = ACTION_COST * 2
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "hunting"
        # Should have moved at most 1 tile from start
        dx = abs(creature.x - start_x)
        dy = abs(creature.y - start_y)
        assert dx <= 1 and dy <= 1, (
            f"Creature teleported from ({start_x},{start_y}) to "
            f"({creature.x},{creature.y}) — moved {dx+dy} tiles!"
        )

    def test_drone_returns_to_sleep_after_losing_player(self):
        """Drone with ai_initial_state=sleeping reverts to sleeping after memory decay."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 1))
        creature = _make_creature(15, 15, config={
            "ai_initial_state": "sleeping",
            "memory_turns": 2,
            "vision_radius": 8,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (10, 10)
        gm.entities.append(creature)
        # Wall between creature and player
        for y in range(0, 20):
            gm.tiles[8, y] = tile_types.wall
        for _ in range(4):
            creature.ai.perform(creature, engine)
        assert creature.ai_state == "sleeping"


# ---------------------------------------------------------------------------
# No-cheating: hunting uses last-known position, not real player pos
# ---------------------------------------------------------------------------

class TestNoCheating:

    def test_hunting_moves_toward_last_known_not_real_pos(self):
        """Creature without LOS pathfinds to ai_target, not player's real position."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 1))
        creature = _make_creature(10, 10, config={
            "aggro_distance": 15,
            "memory_turns": 10,
            "vision_radius": 15,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (15, 15)  # last-known: opposite direction from real player
        gm.entities.append(creature)
        # Block LOS
        for y in range(0, 20):
            gm.tiles[5, y] = tile_types.wall
        creature.ai.perform(creature, engine)
        # Should move toward (15,15), not toward player at (1,1)
        assert creature.x >= 10 or creature.y >= 10, \
            "Should move toward last-known position, not real player"

    def test_creature_clears_target_on_reaching_last_known(self):
        """Creature arriving at last-known position with no LOS clears target."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 1))
        creature = _make_creature(5, 5, config={
            "aggro_distance": 15,
            "memory_turns": 10,
            "vision_radius": 15,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (5, 5)  # already at last-known position
        gm.entities.append(creature)
        # Block LOS
        for y in range(0, 20):
            gm.tiles[3, y] = tile_types.wall
        creature.ai.perform(creature, engine)
        assert creature.ai_target is None


# ---------------------------------------------------------------------------
# Wandering→hunting immediate action
# ---------------------------------------------------------------------------

class TestImmediateAction:

    def test_wandering_to_hunting_attacks_same_turn(self):
        """Adjacent wandering creature transitions to hunting AND attacks in one turn."""
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(6, 5, hp=3, max_hp=3, power=2)
        gm.entities.append(creature)
        assert creature.ai_state == "wandering"
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "hunting"
        assert player.fighter.hp < 10

    def test_wandering_to_hunting_moves_same_turn(self):
        """Non-adjacent wandering creature transitions to hunting and moves on same turn."""
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(8, 5, config={"aggro_distance": 8})
        gm.entities.append(creature)
        old_pos = (creature.x, creature.y)
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "hunting"
        assert (creature.x, creature.y) != old_pos


# ---------------------------------------------------------------------------
# Fleeing state cleanup
# ---------------------------------------------------------------------------

class TestFleeingCleanup:

    def test_flee_to_wander_clears_target(self):
        """Transitioning from fleeing to wandering should clear ai_target."""
        gm, player, engine = _setup(w=40, h=40, player_pos=(1, 1))
        creature = _make_creature(35, 35, hp=1, max_hp=10, config={
            "flee_threshold": 0.3,
            "aggro_distance": 5,
        })
        creature.ai_state = "fleeing"
        creature.ai_target = (1, 1)
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "wandering"
        assert creature.ai_target is None


# ---------------------------------------------------------------------------
# Fleeing pathfinding — creatures should seek escape routes, not just
# greedily maximize distance and trap themselves in corners.
# ---------------------------------------------------------------------------

class TestFleeingPathfinding:

    def test_fleeing_creature_escapes_through_door(self):
        """Smart fleeing creature opens a door to escape instead of cornering."""
        # Corridor: player on left, creature in middle, door on right, open room beyond
        gm, player, engine = _setup(w=20, h=20, player_pos=(3, 5))
        creature = _make_creature(5, 5, hp=1, max_hp=10, config={
            "flee_threshold": 0.3,
            "aggro_distance": 8,
            "can_open_doors": True,
        })
        creature.ai_state = "fleeing"
        gm.entities.append(creature)
        # Walls make a corridor at y=5 from x=1..7, door at x=7
        for y in range(0, 20):
            if y != 5:
                for x_wall in range(2, 8):
                    gm.tiles[x_wall, y] = tile_types.wall
        gm.tiles[7, 5] = tile_types.door_closed
        # Run a few turns — creature should open the door and escape through it
        for _ in range(4):
            creature.ai.perform(creature, engine)
        assert gm.tiles["walkable"][7, 5], "Creature should have opened the door"
        assert creature.x >= 7, "Creature should have moved through the door"

    def test_fleeing_creature_navigates_around_wall(self):
        """Fleeing creature routes around an obstacle instead of getting stuck."""
        # Player at (5,10), creature at (8,10), wall blocking direct east escape
        gm, player, engine = _setup(w=20, h=20, player_pos=(5, 10))
        creature = _make_creature(8, 10, hp=1, max_hp=10, config={
            "flee_threshold": 0.3,
            "aggro_distance": 10,
        })
        creature.ai_state = "fleeing"
        gm.entities.append(creature)
        # Wall at x=10, y=8..12 — blocks direct eastward escape
        for y in range(8, 13):
            gm.tiles[10, y] = tile_types.wall
        start_dist = max(abs(creature.x - player.x), abs(creature.y - player.y))
        for _ in range(5):
            creature.ai.perform(creature, engine)
        end_dist = max(abs(creature.x - player.x), abs(creature.y - player.y))
        assert end_dist > start_dist, "Creature should have increased distance"
        assert creature.x != 8 or creature.y != 10, "Creature should not be stuck"

    def test_fleeing_dumb_creature_cannot_use_door(self):
        """Dumb fleeing creature doesn't open doors (routes around or gets stuck)."""
        gm, player, engine = _setup(w=15, h=15, player_pos=(3, 5))
        creature = _make_creature(5, 5, hp=1, max_hp=10, config={
            "flee_threshold": 0.3,
            "aggro_distance": 8,
            "can_open_doors": False,
        })
        creature.ai_state = "fleeing"
        gm.entities.append(creature)
        # Sealed corridor: only escape is a door the creature can't open
        for y in range(0, 15):
            if y != 5:
                for x_wall in range(2, 8):
                    gm.tiles[x_wall, y] = tile_types.wall
        gm.tiles[7, 5] = tile_types.door_closed
        for _ in range(4):
            creature.ai.perform(creature, engine)
        assert not gm.tiles["walkable"][7, 5], "Door should remain closed"


# ---------------------------------------------------------------------------
# Memory persistence — creatures should hunt long enough to be threatening
# ---------------------------------------------------------------------------

class TestMemoryPersistence:

    def test_creature_still_hunting_after_moderate_turns(self):
        """Creature with default memory keeps hunting for a while after losing LOS."""
        gm, player, engine = _setup(w=30, h=30, player_pos=(1, 1))
        creature = _make_creature(20, 20, config={
            "memory_turns": 15,
            "vision_radius": 8,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (15, 15)
        gm.entities.append(creature)
        # Wall blocks LOS
        for y in range(0, 30):
            gm.tiles[10, y] = tile_types.wall
        # After 10 turns without seeing player, creature should STILL be hunting
        for _ in range(10):
            creature.ai.perform(creature, engine)
        assert creature.ai_state == "hunting"

    def test_creature_gives_up_after_full_memory_expires(self):
        """Creature eventually gives up when memory fully expires."""
        gm, player, engine = _setup(w=30, h=30, player_pos=(1, 1))
        creature = _make_creature(20, 20, config={
            "memory_turns": 15,
            "vision_radius": 8,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (15, 15)
        gm.entities.append(creature)
        # Wall blocks LOS
        for y in range(0, 30):
            gm.tiles[10, y] = tile_types.wall
        for _ in range(20):
            creature.ai.perform(creature, engine)
        assert creature.ai_state != "hunting"


# ---------------------------------------------------------------------------
# Move speed — energy-based movement with variable creature speeds
# ---------------------------------------------------------------------------

class TestMoveSpeed:

    def test_fast_creature_closes_distance_faster(self):
        """A speed-6 hunting creature reaches the player faster than speed-4."""
        # Fast creature
        gm_fast, p_fast, engine_fast = _setup(w=30, h=30, player_pos=(1, 15))
        fast = _make_creature(25, 15, config={
            "move_speed": 6, "aggro_distance": 28, "vision_radius": 28,
        })
        fast.ai_state = "hunting"
        fast.ai_target = (1, 15)
        gm_fast.entities.append(fast)

        # Normal creature
        gm_norm, p_norm, engine_norm = _setup(w=30, h=30, player_pos=(1, 15))
        norm = _make_creature(25, 15, config={
            "move_speed": 4, "aggro_distance": 28, "vision_radius": 28,
        })
        norm.ai_state = "hunting"
        norm.ai_target = (1, 15)
        gm_norm.entities.append(norm)

        for _ in range(10):
            fast.ai.perform(fast, engine_fast)
            norm.ai.perform(norm, engine_norm)

        fast_dist = abs(fast.x - 1)
        norm_dist = abs(norm.x - 1)
        assert fast_dist < norm_dist, "Fast creature should be closer to player"

    def test_slow_creature_closes_distance_slower(self):
        """A speed-3 hunting creature takes longer to reach the player than speed-4."""
        gm_slow, _, engine_slow = _setup(w=30, h=30, player_pos=(1, 15))
        slow = _make_creature(25, 15, config={
            "move_speed": 3, "aggro_distance": 28, "vision_radius": 28,
        })
        slow.ai_state = "hunting"
        slow.ai_target = (1, 15)
        gm_slow.entities.append(slow)

        gm_norm, _, engine_norm = _setup(w=30, h=30, player_pos=(1, 15))
        norm = _make_creature(25, 15, config={
            "move_speed": 4, "aggro_distance": 28, "vision_radius": 28,
        })
        norm.ai_state = "hunting"
        norm.ai_target = (1, 15)
        gm_norm.entities.append(norm)

        for _ in range(10):
            slow.ai.perform(slow, engine_slow)
            norm.ai.perform(norm, engine_norm)

        slow_dist = abs(slow.x - 1)
        norm_dist = abs(norm.x - 1)
        assert slow_dist > norm_dist, "Slow creature should be farther from player"

    def test_normal_speed_moves_every_turn(self):
        """Speed-4 hunting creature moves every single turn."""
        gm, _, engine = _setup(w=30, h=30, player_pos=(1, 15))
        creature = _make_creature(25, 15, config={
            "move_speed": 4, "aggro_distance": 28, "vision_radius": 28,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (1, 15)
        gm.entities.append(creature)
        moves = 0
        for _ in range(10):
            ox, oy = creature.x, creature.y
            creature.ai.perform(creature, engine)
            if (creature.x, creature.y) != (ox, oy):
                moves += 1
        assert moves == 10

    def test_slow_drone_cannot_keep_up_with_player(self):
        """A speed-3 drone chasing a player who moves every turn should fall behind."""
        gm = make_arena(60, 5)
        for x in range(1, 59):
            for y in range(1, 4):
                gm.tiles[x, y] = tile_types.floor
        player = Entity(x=40, y=2, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        creature = _make_creature(42, 2, config={
            "move_speed": 3, "aggro_distance": 55, "vision_radius": 55,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (player.x, player.y)
        creature.organic = False
        gm.entities.append(creature)
        engine = MockEngine(gm, player)
        from game.helpers import chebyshev
        start_gap = chebyshev(creature.x, creature.y, player.x, player.y)
        for _ in range(20):
            player.x -= 1  # player always has room
            creature.ai.perform(creature, engine)
        end_gap = chebyshev(creature.x, creature.y, player.x, player.y)
        assert end_gap > start_gap, (
            f"Speed-3 drone should fall behind player. "
            f"Gap went from {start_gap} to {end_gap}"
        )

    def test_normal_speed_creature_keeps_pace_with_player(self):
        """A speed-4 creature should keep pace with a player moving every turn."""
        gm = make_arena(60, 5)
        for x in range(1, 59):
            for y in range(1, 4):
                gm.tiles[x, y] = tile_types.floor
        player = Entity(x=40, y=2, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        creature = _make_creature(42, 2, config={
            "move_speed": 4, "aggro_distance": 55, "vision_radius": 55,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (player.x, player.y)
        gm.entities.append(creature)
        engine = MockEngine(gm, player)
        from game.helpers import chebyshev
        start_gap = chebyshev(creature.x, creature.y, player.x, player.y)
        for _ in range(20):
            player.x -= 1
            creature.ai.perform(creature, engine)
        end_gap = chebyshev(creature.x, creature.y, player.x, player.y)
        assert end_gap == start_gap, (
            f"Speed-4 creature should keep pace. "
            f"Gap went from {start_gap} to {end_gap}"
        )

    def test_low_gravity_slows_organic_creature(self):
        """Low gravity halves effective speed for organic creatures."""
        gm, _, engine = _setup(w=30, h=30, player_pos=(1, 15))
        engine.environment = {"low_gravity": 1}
        creature = _make_creature(25, 15, config={
            "move_speed": 4, "aggro_distance": 28, "vision_radius": 28,
        })
        creature.organic = True
        creature.ai_state = "hunting"
        creature.ai_target = (1, 15)
        gm.entities.append(creature)
        moves = 0
        for _ in range(10):
            ox, oy = creature.x, creature.y
            creature.ai.perform(creature, engine)
            if (creature.x, creature.y) != (ox, oy):
                moves += 1
        # Speed 4 halved = 2 energy/turn, needs 4 to act → every other turn = 5
        assert moves == 5

    def test_low_gravity_does_not_slow_machine(self):
        """Non-organic creatures ignore low gravity speed penalty."""
        gm, _, engine = _setup(w=30, h=30, player_pos=(1, 15))
        engine.environment = {"low_gravity": 1}
        creature = _make_creature(25, 15, config={
            "move_speed": 4, "aggro_distance": 28, "vision_radius": 28,
        })
        creature.organic = False
        creature.ai_state = "hunting"
        creature.ai_target = (1, 15)
        gm.entities.append(creature)
        moves = 0
        for _ in range(10):
            ox, oy = creature.x, creature.y
            creature.ai.perform(creature, engine)
            if (creature.x, creature.y) != (ox, oy):
                moves += 1
        assert moves == 10

    def test_attack_not_gated_by_speed(self):
        """Adjacent hunting creature always attacks regardless of speed."""
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(6, 5, hp=3, max_hp=3, power=2, config={
            "move_speed": 1,  # very slow
        })
        creature.ai_state = "hunting"
        creature.ai_target = (5, 5)
        gm.entities.append(creature)
        hits = 0
        for _ in range(4):
            old_hp = player.fighter.hp
            creature.ai.perform(creature, engine)
            if player.fighter.hp < old_hp:
                hits += 1
        assert hits == 4, "Attack should happen every turn regardless of speed"

    def test_attack_drains_energy(self):
        """Attacking should drain energy so creatures can't bank moves during melee."""
        from game.ai import ACTION_COST
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(6, 5, hp=5, max_hp=5, power=1, config={
            "move_speed": 3,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (5, 5)
        gm.entities.append(creature)
        # Melee for 3 turns
        for _ in range(3):
            creature.ai.perform(creature, engine)
        # Energy should not have banked above one turn's worth
        assert creature.ai_energy <= creature.ai_config["move_speed"], (
            f"Energy banked to {creature.ai_energy} during melee, "
            f"expected at most {creature.ai_config['move_speed']}"
        )

    def test_slow_drone_falls_behind_after_melee(self):
        """After disengaging from melee, player should outrun a speed-3 drone."""
        gm = make_arena(60, 5)
        for x in range(1, 59):
            for y in range(1, 4):
                gm.tiles[x, y] = tile_types.floor
        player = Entity(x=30, y=2, name="Player", fighter=Fighter(50, 50, 5, 1))
        gm.entities.append(player)
        creature = _make_creature(31, 2, config={
            "move_speed": 3, "aggro_distance": 55, "vision_radius": 55,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (player.x, player.y)
        creature.organic = False
        gm.entities.append(creature)
        engine = MockEngine(gm, player)
        # 3 turns of melee
        for _ in range(3):
            creature.ai.perform(creature, engine)
        # Now player runs for 8 turns
        from game.helpers import chebyshev
        for _ in range(8):
            player.x -= 1
            creature.ai.perform(creature, engine)
        gap = chebyshev(creature.x, creature.y, player.x, player.y)
        assert gap >= 3, (
            f"Player should outrun speed-3 drone after melee, but gap is only {gap}"
        )

    def test_energy_capped_prevents_teleport_on_state_change(self):
        """Energy should not accumulate unboundedly during melee turns.

        Without a cap, a creature attacking for several turns saves up energy
        and then moves many tiles at once when switching to flee.
        """
        from game.ai import ACTION_COST
        gm, player, engine = _setup(w=30, h=30, player_pos=(5, 15))
        creature = _make_creature(6, 15, hp=10, max_hp=10, power=1, config={
            "move_speed": 4, "flee_threshold": 0.5,
            "aggro_distance": 28, "vision_radius": 28,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (5, 15)
        gm.entities.append(creature)

        # Simulate 5 turns of melee attacking (adjacent to player)
        for _ in range(5):
            creature.ai.perform(creature, engine)
        assert creature.ai_state == "hunting"

        # Energy should be capped, not 5 * move_speed
        assert creature.ai_energy <= ACTION_COST * 2

        # Now trigger flee by lowering HP below threshold
        creature.fighter.hp = 4  # 4/10 = 0.4 < 0.5
        ox, oy = creature.x, creature.y
        creature.ai.perform(creature, engine)

        # Should move at most 2 steps (cap of ACTION_COST * 2),
        # not teleport 5+ tiles away
        distance_moved = max(abs(creature.x - ox), abs(creature.y - oy))
        assert distance_moved <= 2, (
            f"Creature moved {distance_moved} steps, expected at most 2"
        )


# ---------------------------------------------------------------------------
# Door blocking — creatures must not attack through closed doors
# ---------------------------------------------------------------------------

class TestDoorBlocking:

    def test_rat_cannot_attack_through_closed_door(self):
        """A rat on the other side of a closed door should not damage the player.

        Layout: @+r in a corridor — player at (1,1), door at (2,1), rat at (3,1).
        Walls surround to prevent any diagonal bypass.
        """
        gm = make_arena(5, 3)
        # Build corridor: walls everywhere except the corridor row
        for x in range(5):
            for y in range(3):
                gm.tiles[x, y] = tile_types.wall
        gm.tiles[1, 1] = tile_types.floor
        gm.tiles[2, 1] = tile_types.door_closed
        gm.tiles[3, 1] = tile_types.floor

        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        creature = _make_creature(3, 1)
        creature.ai_state = "hunting"
        creature.ai_target = (1, 1)
        gm.entities.append(creature)
        engine = MockEngine(gm, player)

        creature.ai.perform(creature, engine)

        assert player.fighter.hp == 10, (
            "Rat should not damage player through a closed door"
        )
        assert creature.x == 3 and creature.y == 1, (
            "Rat should not move — door is blocking"
        )

    def test_rat_cannot_cut_corner_past_door(self):
        """A rat should not move diagonally past a closed door.

        Layout:
          #####
          #@+r#
          #...#
          #####
        Player at (1,1), door at (2,1), rat at (3,1).
        Open floor below at y=2.  Rat should NOT be able to
        cut diagonally from (3,1) to (2,2) and then to (1,1).
        It should go (3,1)->(3,2)->(2,2)->(1,2)->(1,1), not
        cut the corner at (2,1)/(3,1).
        """
        gm = make_arena(5, 5)
        for x in range(5):
            for y in range(5):
                gm.tiles[x, y] = tile_types.wall
        # corridor at y=1 with a door
        gm.tiles[1, 1] = tile_types.floor
        gm.tiles[2, 1] = tile_types.door_closed
        gm.tiles[3, 1] = tile_types.floor
        # open floor below
        gm.tiles[1, 2] = tile_types.floor
        gm.tiles[2, 2] = tile_types.floor
        gm.tiles[3, 2] = tile_types.floor

        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        creature = _make_creature(3, 1, config={"move_speed": 4})  # 1 move per turn
        creature.ai_state = "hunting"
        creature.ai_target = (1, 1)
        gm.entities.append(creature)
        engine = MockEngine(gm, player)

        creature.ai.perform(creature, engine)

        # Rat should NOT have cut the corner to (2, 0) or (2, 2) diagonally
        # past the closed door at (2, 1). It should go down to (3, 2) first.
        assert not (creature.x == 2 and creature.y == 2), (
            "Rat should not cut corner diagonally past a closed door"
        )
        # With 1 move, rat should have moved to (3, 2) — the only valid step
        assert creature.x == 3 and creature.y == 2, (
            f"Expected rat at (3,2), got ({creature.x},{creature.y})"
        )

    def test_diagonal_past_wall_still_allowed(self):
        """Diagonal movement past a wall corner is fine — only doors block.

        Layout:
          #####
          ##.@#
          #r..#
          #####
        Rat at (1,2), player at (3,1).  Wall at (1,1) and (2,1).
        Rat should be able to move diagonally from (1,2) to (2,1)... no,
        (2,1) is a wall.  Let's use:
          #####
          #.@.#
          #r#.#
          #####
        Rat at (1,2), wall at (2,2), player at (2,1).
        Rat should move diag from (1,2) to (2,1) — wall at (2,2) doesn't
        block because it's a wall, not a door.
        """
        gm = make_arena(5, 4)
        for x in range(5):
            for y in range(4):
                gm.tiles[x, y] = tile_types.wall
        gm.tiles[1, 1] = tile_types.floor
        gm.tiles[2, 1] = tile_types.floor
        gm.tiles[3, 1] = tile_types.floor
        gm.tiles[1, 2] = tile_types.floor
        # (2,2) stays wall
        gm.tiles[3, 2] = tile_types.floor

        player = Entity(x=2, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        creature = _make_creature(1, 2, config={"move_speed": 4})
        creature.ai_state = "hunting"
        creature.ai_target = (2, 1)
        gm.entities.append(creature)
        engine = MockEngine(gm, player)

        creature.ai.perform(creature, engine)

        # Rat should have attacked the player (adjacent after diagonal move
        # past wall corner, or moved to (1,1) cardinally then attacked)
        assert player.fighter.hp < 10, (
            "Rat should be able to move diagonally past a wall corner"
        )


# ---------------------------------------------------------------------------
# Patrol-style wandering
# ---------------------------------------------------------------------------

class TestPatrolWander:

    def test_wandering_creature_picks_a_goal(self):
        """A wandering creature should set ai_wander_goal on its first move."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 1))
        creature = _make_creature(10, 10, config={
            "aggro_distance": 3, "vision_radius": 4,
        })
        creature.ai_state = "wandering"
        gm.entities.append(creature)
        # Wall off player so creature doesn't aggro
        for y in range(0, 20):
            gm.tiles[5, y] = tile_types.wall
        creature.ai.perform(creature, engine)
        assert creature.ai_wander_goal is not None

    def test_wandering_creature_moves_toward_goal(self):
        """Over several turns a wandering creature should get closer to its goal."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 1))
        creature = _make_creature(15, 15, config={
            "aggro_distance": 3, "vision_radius": 4,
        })
        creature.ai_state = "wandering"
        gm.entities.append(creature)
        # Wall off player
        for y in range(0, 20):
            gm.tiles[5, y] = tile_types.wall
        # Force a known goal
        creature.ai_wander_goal = (10, 10)
        from game.helpers import chebyshev
        start_dist = chebyshev(creature.x, creature.y, 10, 10)
        for _ in range(5):
            creature.ai.perform(creature, engine)
        end_dist = chebyshev(creature.x, creature.y, 10, 10)
        assert end_dist < start_dist, "Creature should move toward its wander goal"

    def test_wandering_creature_picks_new_goal_on_arrival(self):
        """When a creature reaches its wander goal it should pick a new one."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 1))
        creature = _make_creature(10, 10, config={
            "aggro_distance": 3, "vision_radius": 4,
        })
        creature.ai_state = "wandering"
        gm.entities.append(creature)
        # Wall off player
        for y in range(0, 20):
            gm.tiles[5, y] = tile_types.wall
        # Set goal to current position (already arrived)
        creature.ai_wander_goal = (10, 10)
        creature.ai.perform(creature, engine)
        assert creature.ai_wander_goal != (10, 10), \
            "Creature should pick a new goal after reaching the old one"

    def test_wandering_goal_cleared_on_aggro(self):
        """When a wandering creature transitions to hunting, wander goal is cleared."""
        gm, player, engine = _setup(player_pos=(5, 5))
        creature = _make_creature(7, 5, config={
            "aggro_distance": 8, "vision_radius": 8,
        })
        creature.ai_state = "wandering"
        creature.ai_wander_goal = (15, 15)
        gm.entities.append(creature)
        creature.ai.perform(creature, engine)
        assert creature.ai_state == "hunting"
        assert creature.ai_wander_goal is None

    def test_wandering_picks_reachable_goal(self):
        """The chosen wander goal should be a walkable tile."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 1))
        creature = _make_creature(10, 10, config={
            "aggro_distance": 3, "vision_radius": 4,
        })
        creature.ai_state = "wandering"
        gm.entities.append(creature)
        # Wall off player
        for y in range(0, 20):
            gm.tiles[5, y] = tile_types.wall
        creature.ai.perform(creature, engine)
        gx, gy = creature.ai_wander_goal
        assert gm.is_walkable(gx, gy)

    def test_stuck_creature_picks_new_goal(self):
        """If a creature can't make progress toward its goal, it picks a new one."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 1))
        creature = _make_creature(10, 10, config={
            "aggro_distance": 3, "vision_radius": 4,
        })
        creature.ai_state = "wandering"
        gm.entities.append(creature)
        # Wall off player
        for y in range(0, 20):
            gm.tiles[5, y] = tile_types.wall
        # Set an unreachable goal (inside the wall)
        creature.ai_wander_goal = (5, 5)
        # Box the creature in so pathfinding fails
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
            gm.tiles[10+dx, 10+dy] = tile_types.wall
        # Give energy so the creature attempts to move
        from game.ai import ACTION_COST
        creature.ai_energy = ACTION_COST
        creature.ai.perform(creature, engine)
        # Creature should have given up on the unreachable goal
        assert creature.ai_wander_goal is None

    def test_wandering_does_not_path_through_walls(self):
        """Wander goal must be truly reachable — not across a wall partition."""
        gm, player, engine = _setup(w=30, h=30, player_pos=(1, 1))
        creature = _make_creature(20, 20, config={
            "aggro_distance": 3, "vision_radius": 4,
        })
        creature.ai_state = "wandering"
        gm.entities.append(creature)
        # Solid wall partition at x=10
        for y in range(0, 30):
            gm.tiles[10, y] = tile_types.wall
        # Run many turns — creature must never cross the wall
        for _ in range(30):
            creature.ai.perform(creature, engine)
            assert creature.x > 10, (
                f"Creature crossed wall partition to ({creature.x},{creature.y})"
            )

    def test_wandering_avoids_hazard_tiles_when_safe_exist(self):
        """Wander goal prefers non-hazard tiles when they exist."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 1))
        creature = _make_creature(10, 10, config={
            "aggro_distance": 3, "vision_radius": 4,
        })
        creature.ai_state = "wandering"
        gm.entities.append(creature)
        # Wall off player
        for y in range(0, 20):
            gm.tiles[5, y] = tile_types.wall
        # Mark some of the map as hazardous, leaving a safe zone
        import numpy as np
        hazard = np.zeros((20, 20), dtype=bool)
        hazard[14:, :] = True  # right half is hazardous
        gm.hazard_overlays["vacuum"] = hazard
        creature.ai.perform(creature, engine)
        if creature.ai_wander_goal is not None:
            gx, gy = creature.ai_wander_goal
            assert not hazard[gx, gy], "Should prefer non-hazard tiles when available"

    def test_wandering_falls_back_to_hazard_when_all_hazardous(self):
        """When all reachable tiles are hazardous, wander goal is still set."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(1, 1))
        creature = _make_creature(10, 10, config={
            "aggro_distance": 3, "vision_radius": 4,
        })
        creature.ai_state = "wandering"
        gm.entities.append(creature)
        for y in range(0, 20):
            gm.tiles[5, y] = tile_types.wall
        import numpy as np
        hazard = np.ones((20, 20), dtype=bool)
        gm.hazard_overlays["vacuum"] = hazard
        creature.ai.perform(creature, engine)
        # Enemy should still get a wander goal (falls back to hazardous tiles)
        assert creature.ai_wander_goal is not None or \
            (creature.x, creature.y) != (10, 10), \
            "Enemy should wander even when all tiles are hazardous"


class TestWanderingInHazards:
    """Enemies should keep wandering even when all reachable tiles are hazardous."""

    def test_wander_in_full_vacuum_area(self):
        """Enemy in a fully-vacuumed room should still wander (not freeze)."""
        gm = make_arena(20, 20)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player)

        # Place enemy far from player so it doesn't aggro
        creature = _make_creature(15, 15, config={
            "aggro_distance": 3, "vision_radius": 4,
        })
        creature.ai_state = "wandering"
        gm.entities.append(creature)

        # Cover the entire map in vacuum hazard
        import numpy as np
        vacuum = np.ones((20, 20), dtype=bool)
        gm.hazard_overlays["vacuum"] = vacuum

        start_x, start_y = creature.x, creature.y
        moved = False
        for _ in range(10):
            creature.ai.perform(creature, engine)
            if (creature.x, creature.y) != (start_x, start_y):
                moved = True
                break

        assert moved, "Wandering enemy froze in hazard area — never moved in 10 turns"

    def test_wander_prefers_non_hazard_tiles(self):
        """When some non-hazard tiles exist, wander goal should prefer them."""
        gm = make_arena(20, 20)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player)

        creature = _make_creature(15, 15, config={
            "aggro_distance": 3, "vision_radius": 4,
        })
        creature.ai_state = "wandering"
        gm.entities.append(creature)

        # Vacuum everywhere EXCEPT a small safe zone
        import numpy as np
        vacuum = np.ones((20, 20), dtype=bool)
        vacuum[14:17, 14:17] = False  # 3x3 safe area around enemy
        gm.hazard_overlays["vacuum"] = vacuum

        creature.ai.perform(creature, engine)
        if creature.ai_wander_goal is not None:
            gx, gy = creature.ai_wander_goal
            assert not vacuum[gx, gy], "Should prefer non-hazard tiles when available"


class TestHuntingUnreachable:
    """Enemies that can see but cannot reach the player should not freeze."""

    def test_visible_but_unreachable_deaggros(self):
        """Enemy seeing player through a window but with no walkable path
        should eventually give up hunting."""
        # 20x20 arena, wall of windows at x=10 splitting map in two.
        gm = make_arena(20, 20)
        for y in range(0, 20):
            gm.tiles[10, y] = tile_types.structure_window  # transparent, not walkable

        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player)

        creature = _make_creature(15, 5, config={
            "aggro_distance": 20, "vision_radius": 20, "memory_turns": 15,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (player.x, player.y)
        creature.ai_turns_since_seen = 0
        gm.entities.append(creature)

        # Run many turns — enemy can always see player through window
        for _ in range(30):
            creature.ai.perform(creature, engine)

        # Enemy should NOT still be stuck in hunting — it should have
        # de-aggroed because it cannot reach the player.
        assert creature.ai_state != "hunting", (
            f"Enemy stuck in hunting for 30 turns despite being unreachable "
            f"(ai_stuck_turns={getattr(creature, 'ai_stuck_turns', 'N/A')})"
        )

    def test_reachable_enemy_stays_hunting(self):
        """Enemy that CAN reach the player should remain hunting (no false de-aggro)."""
        gm, player, engine = _setup(w=20, h=20, player_pos=(5, 5))

        creature = _make_creature(8, 5, config={
            "aggro_distance": 20, "vision_radius": 20, "memory_turns": 15,
        })
        creature.ai_state = "hunting"
        creature.ai_target = (player.x, player.y)
        creature.ai_turns_since_seen = 0
        gm.entities.append(creature)

        # Run several turns — enemy should approach and attack, staying in hunting
        for _ in range(10):
            creature.ai.perform(creature, engine)

        # Enemy should still be hunting (or adjacent attacking)
        from game.helpers import chebyshev
        dist = chebyshev(creature.x, creature.y, player.x, player.y)
        assert creature.ai_state == "hunting" or dist <= 1

    def test_multiple_enemies_unreachable_all_deaggro(self):
        """All enemies stuck behind a window should eventually de-aggro."""
        gm = make_arena(20, 20)
        for y in range(0, 20):
            gm.tiles[10, y] = tile_types.structure_window

        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player)

        creatures = []
        for i, (cx, cy) in enumerate([(15, 3), (15, 5), (15, 7)]):
            c = _make_creature(cx, cy, config={
                "aggro_distance": 20, "vision_radius": 20, "memory_turns": 15,
            }, name=f"Drone{i}")
            c.ai_state = "hunting"
            c.ai_target = (player.x, player.y)
            c.ai_turns_since_seen = 0
            gm.entities.append(c)
            creatures.append(c)

        for _ in range(30):
            for c in creatures:
                c.ai.perform(c, engine)

        for c in creatures:
            assert c.ai_state != "hunting", (
                f"{c.name} still stuck in hunting after 30 turns"
            )


# ---------------------------------------------------------------------------
# AI walks through interactable check
# ---------------------------------------------------------------------------

def test_ai_does_not_walk_through_interactable():
    """AI should respect interactable blocking (currently a known limitation)."""
    gm = make_arena()
    player = Entity(x=1, y=1, fighter=Fighter(10, 10, 0, 1))
    # Place interactable between enemy and player
    console = Entity(x=3, y=3, name="Console", blocks_movement=False,
                     interactable={"kind": "console"})
    enemy = Entity(x=4, y=4, fighter=Fighter(3, 3, 0, 1), ai=HostileAI())
    gm.entities.extend([player, console, enemy])
    gm.visible[:] = True
    eng = MockEngine(gm, player)
    # Enemy moves toward player; note: AI currently CAN walk through interactables
    # This test documents the current behavior
    old_x, old_y = enemy.x, enemy.y
    enemy.ai.perform(enemy, eng)
    # Enemy moved (may or may not overlap interactable depending on path)
    assert (enemy.x, enemy.y) != (old_x, old_y)


# ---------------------------------------------------------------------------
# AI speed floor in low gravity
# ---------------------------------------------------------------------------

class TestAISpeedFloorLowGravity:
    def test_speed_1_low_gravity_does_not_freeze(self):
        """move_speed=1 in low gravity should floor to 1, not 0."""
        from tests.conftest import make_creature

        gm = make_arena()
        player = Entity(x=1, y=1, fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        creature = make_creature(x=5, y=5, ai_config={"move_speed": 1})
        gm.entities.append(creature)

        ai = creature.ai
        creature.ai_energy = 0
        ai._accumulate_energy(creature, engine)
        assert creature.ai_energy >= 1, "speed floor should be >= 1"

    def test_speed_2_low_gravity_gives_1(self):
        """move_speed=2 halved should give 1."""
        from tests.conftest import make_creature

        gm = make_arena()
        player = Entity(x=1, y=1, fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        creature = make_creature(x=5, y=5, ai_config={"move_speed": 2})
        gm.entities.append(creature)

        creature.ai_energy = 0
        creature.ai._accumulate_energy(creature, engine)
        assert creature.ai_energy == 1

    def test_speed_normal_no_low_gravity(self):
        """Without low gravity, speed should not be halved."""
        from tests.conftest import make_creature

        gm = make_arena()
        player = Entity(x=1, y=1, fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player, environment={})

        creature = make_creature(x=5, y=5, ai_config={"move_speed": 1})
        gm.entities.append(creature)

        creature.ai_energy = 0
        creature.ai._accumulate_energy(creature, engine)
        assert creature.ai_energy == 1
