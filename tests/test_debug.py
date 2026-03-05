"""Tests for debug configuration flags."""
import debug
from tests.conftest import make_engine
from game.entity import Entity, Fighter
from game.suit import Suit


def _make_suited_engine():
    """Engine with vacuum environment and a suit that has O2 pool."""
    import numpy as np
    suit = Suit(name="Test Suit", resistances={"vacuum": 10}, defense_bonus=0)
    suit.refill_pools()
    engine = make_engine(env={"vacuum": 1}, suit=suit)
    # Vacuum is spatial: add an overlay covering the whole map
    gm = engine.game_map
    gm.hazard_overlays["vacuum"] = np.full(
        (gm.width, gm.height), fill_value=True, order="F"
    )
    gm._hazards_dirty = False
    return engine


class TestGodMode:
    def test_god_mode_prevents_environment_damage(self):
        """When O2 pool is depleted, GOD_MODE prevents HP loss."""
        engine = _make_suited_engine()
        engine.suit.current_pools["vacuum"] = 0
        hp_before = engine.player.fighter.hp

        debug.GOD_MODE = True
        from game.environment import apply_environment_tick
        apply_environment_tick(engine)

        assert engine.player.fighter.hp == hp_before

    def test_god_mode_prevents_melee_damage(self):
        """GOD_MODE prevents damage when player is the target."""
        engine = _make_suited_engine()
        enemy = Entity(x=4, y=5, name="Enemy", fighter=Fighter(5, 5, 0, 3))
        engine.game_map.entities.append(enemy)
        hp_before = engine.player.fighter.hp

        debug.GOD_MODE = True
        from game.actions import MeleeAction
        MeleeAction(engine.player).perform(engine, enemy)

        assert engine.player.fighter.hp == hp_before

    def test_god_mode_prevents_dot_damage(self):
        """GOD_MODE prevents DoT effect damage."""
        engine = _make_suited_engine()
        engine.active_effects = [{"type": "radiation", "dot": 2, "remaining": 3}]
        hp_before = engine.player.fighter.hp

        debug.GOD_MODE = True
        from game.hazards import apply_dot_effects
        apply_dot_effects(engine)

        assert engine.player.fighter.hp == hp_before


class TestDisableOxygen:
    def test_disable_oxygen_prevents_pool_drain(self):
        """DISABLE_OXYGEN keeps suit O2 pool from depleting."""
        engine = _make_suited_engine()
        pool_before = engine.suit.current_pools["vacuum"]

        debug.DISABLE_OXYGEN = True
        from game.environment import apply_environment_tick
        apply_environment_tick(engine)

        assert engine.suit.current_pools["vacuum"] == pool_before

    def test_oxygen_drains_normally_when_disabled_flag_off(self):
        """Without the flag, O2 pool should drain by 1 after DRAIN_INTERVAL ticks."""
        engine = _make_suited_engine()
        pool_before = engine.suit.current_pools["vacuum"]

        from game.environment import apply_environment_tick
        from game.suit import Suit
        for _ in range(Suit.DRAIN_INTERVAL):
            apply_environment_tick(engine)

        assert engine.suit.current_pools["vacuum"] == pool_before - 1


class TestDisableEnemyAI:
    def test_disable_enemy_ai_skips_turns(self):
        """DISABLE_ENEMY_AI prevents enemies from acting."""
        performed = []

        class TrackingAI:
            def perform(self, entity, engine):
                performed.append(entity.name)

        engine = _make_suited_engine()
        enemy = Entity(x=3, y=5, name="Drone", fighter=Fighter(5, 5, 0, 1))
        enemy.ai = TrackingAI()
        engine.game_map.entities.append(enemy)

        debug.DISABLE_ENEMY_AI = True
        from ui.tactical_state import TacticalState
        state = TacticalState()
        state._after_player_turn(engine)

        assert performed == []

    def test_enemy_ai_runs_when_flag_off(self):
        """Without the flag, enemies should act."""
        performed = []

        class TrackingAI:
            def perform(self, entity, engine):
                performed.append(entity.name)

        engine = _make_suited_engine()
        enemy = Entity(x=3, y=5, name="Drone", fighter=Fighter(5, 5, 0, 1))
        enemy.ai = TrackingAI()
        engine.game_map.entities.append(enemy)

        from ui.tactical_state import TacticalState
        state = TacticalState()
        state._after_player_turn(engine)

        assert "Drone" in performed


class TestDisableHazards:
    def test_disable_hazards_prevents_trigger(self):
        """DISABLE_HAZARDS causes trigger_hazard to be a no-op."""
        engine = _make_suited_engine()
        hp_before = engine.player.fighter.hp

        debug.DISABLE_HAZARDS = True
        from game.hazards import trigger_hazard
        trigger_hazard(engine, {"type": "electric", "damage": 5}, "Test Panel")

        assert engine.player.fighter.hp == hp_before


class TestOneHitKill:
    def test_one_hit_kill_destroys_enemy(self):
        """ONE_HIT_KILL makes player attacks deal lethal damage."""
        engine = _make_suited_engine()
        enemy = Entity(x=4, y=5, name="Enemy", fighter=Fighter(99, 99, 10, 1))
        engine.game_map.entities.append(enemy)

        debug.ONE_HIT_KILL = True
        from game.actions import MeleeAction
        MeleeAction(enemy).perform(engine, engine.player)

        assert enemy.fighter.hp <= 0
