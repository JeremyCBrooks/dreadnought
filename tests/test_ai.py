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
