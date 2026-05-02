"""Tests for engine.rng — deterministic per-turn RNG used for save-load determinism."""

from __future__ import annotations

import random

from engine.game_state import Engine
from world.galaxy import Galaxy


def _engine_with_seed(seed: int) -> Engine:
    engine = Engine()
    engine.galaxy = Galaxy(seed=seed)
    return engine


def test_turn_counter_starts_at_zero():
    engine = Engine()
    assert engine.turn_counter == 0


def test_rng_returns_random_instance():
    engine = _engine_with_seed(42)
    rng = engine.rng("steal")
    assert isinstance(rng, random.Random)


def test_rng_deterministic_for_same_inputs():
    e1 = _engine_with_seed(123)
    e2 = _engine_with_seed(123)
    e1.turn_counter = e2.turn_counter = 7

    a = [e1.rng("ai").random() for _ in range(5)]
    b = [e2.rng("ai").random() for _ in range(5)]
    assert a == b


def test_rng_different_salts_produce_different_streams():
    engine = _engine_with_seed(99)
    a = engine.rng("steal").random()
    b = engine.rng("wander").random()
    # Astronomically unlikely to be equal under different salts.
    assert a != b


def test_rng_different_turn_counters_produce_different_streams():
    engine = _engine_with_seed(99)
    engine.turn_counter = 0
    a = engine.rng("steal").random()
    engine.turn_counter = 1
    b = engine.rng("steal").random()
    assert a != b


def test_rng_works_without_galaxy():
    """Engine without galaxy (e.g. early init) must still produce a usable RNG."""
    engine = Engine()
    rng = engine.rng("any")
    assert isinstance(rng, random.Random)
    # Same engine state → same draw
    rng2 = engine.rng("any")
    assert rng.random() == rng2.random()


def test_rng_consecutive_calls_same_turn_same_salt_are_identical():
    """Two calls with the same (seed, turn, salt) are independent Random instances
    seeded the same way — first draw is identical (and that's by design)."""
    engine = _engine_with_seed(5)
    engine.turn_counter = 3
    a = engine.rng("steal").random()
    b = engine.rng("steal").random()
    assert a == b  # same seed → same first draw


def test_rng_independence_across_turns():
    """Reload at turn N and run forward should match original run from turn N."""
    e1 = _engine_with_seed(11)
    e2 = _engine_with_seed(11)

    # Original run: advance through several turns drawing from "ai"
    original = []
    for t in range(5):
        e1.turn_counter = t
        original.append(e1.rng("ai").random())

    # Replay from turn 0 should match
    replay = []
    for t in range(5):
        e2.turn_counter = t
        replay.append(e2.rng("ai").random())

    assert original == replay


# ── Determinism of game systems that use the engine RNG ───────────────────────


def test_steal_action_deterministic_under_same_engine_state():
    """Two engines with the same (galaxy.seed, turn_counter) must steal the same item.

    This is the core anti-savescum guarantee: if a player saves before being
    pickpocketed and reloads, the steal outcome must be identical, so they
    can't reroll for a favorable result.
    """
    from game.actions import _try_steal
    from game.entity import Entity, Fighter
    from game.loadout import Loadout
    from tests.conftest import make_creature

    def _setup() -> tuple:
        engine = _engine_with_seed(2026)
        engine.turn_counter = 12

        player = Entity(
            x=5, y=5, name="Player",
            fighter=Fighter(hp=10, max_hp=10, defense=0, power=1),
        )
        player.loadout = Loadout()
        # Three stealable items so choice() is non-trivial.
        player.inventory = [
            Entity(name="Coin", item={"type": "junk"}),
            Entity(name="Datachip", item={"type": "junk"}),
            Entity(name="Wrench", item={"type": "tool"}),
        ]
        engine.player = player

        thief = make_creature(x=4, y=5, name="Thief", ai_config={"can_steal": True})
        thief.inventory = []
        thief.stolen_loot = []

        return engine, thief, player

    e1, t1, p1 = _setup()
    e2, t2, p2 = _setup()

    # Force the chance to succeed by retrying turns until one works,
    # but in lockstep — both engines should land on the same outcome.
    for turn in range(50):
        e1.turn_counter = turn
        e2.turn_counter = turn

        before1 = list(p1.inventory)
        before2 = list(p2.inventory)
        _try_steal(e1, t1, p1)
        _try_steal(e2, t2, p2)

        # Steal happened iff inventory shrank — must happen on same turn for both
        assert (len(p1.inventory) < len(before1)) == (len(p2.inventory) < len(before2))

        if t1.stolen_loot or t2.stolen_loot:
            # Both must have stolen the same item by name (different Python objects).
            assert [s.name for s in t1.stolen_loot] == [s.name for s in t2.stolen_loot]
            return

    raise AssertionError("Expected at least one successful steal across 50 turns")
