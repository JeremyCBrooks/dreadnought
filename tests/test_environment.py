"""Tests for environment tick system."""
import numpy as np

from game.environment import apply_environment_tick
from game.suit import Suit
from tests.conftest import make_engine as _make_engine

DRAIN = Suit.DRAIN_INTERVAL


def _tick(engine, n=1):
    for _ in range(n):
        apply_environment_tick(engine)


def _add_vacuum_overlay(engine):
    """Mark the entire map as vacuum-exposed so spatial checks pass."""
    gm = engine.game_map
    gm.hazard_overlays["vacuum"] = np.full(
        (gm.width, gm.height), fill_value=True, order="F"
    )
    gm._hazards_dirty = False


def test_no_damage_with_suit_pool():
    suit = Suit("Test", {"vacuum": 10}, defense_bonus=0)
    engine = _make_engine(env={"vacuum": 1}, suit=suit)
    _add_vacuum_overlay(engine)
    _tick(engine, DRAIN)
    assert engine.player.fighter.hp == 10
    assert suit.current_pools["vacuum"] == 9


def test_damage_when_pool_depleted():
    suit = Suit("Test", {"vacuum": 1}, defense_bonus=0)
    engine = _make_engine(env={"vacuum": 1}, suit=suit)
    _add_vacuum_overlay(engine)
    # DRAIN ticks: pool drains from 1 to 0, no damage yet
    _tick(engine, DRAIN)
    assert suit.current_pools["vacuum"] == 0
    assert engine.player.fighter.hp == 10
    # Next tick: pool is 0, damage dealt
    _tick(engine)
    assert engine.player.fighter.hp == 9


def test_no_damage_without_environment():
    suit = Suit("Test", {"vacuum": 10}, defense_bonus=0)
    engine = _make_engine(env=None, suit=suit)
    apply_environment_tick(engine)
    assert engine.player.fighter.hp == 10


def test_no_damage_without_suit():
    engine = _make_engine(env={"vacuum": 1}, suit=None)
    apply_environment_tick(engine)
    assert engine.player.fighter.hp == 10


def test_damage_no_resistance():
    suit = Suit("Test", {}, defense_bonus=0)
    engine = _make_engine(env={"radiation": 1}, suit=suit)
    apply_environment_tick(engine)
    assert engine.player.fighter.hp == 9


def test_pool_depletion_over_time():
    suit = Suit("Test", {"cold": 3}, defense_bonus=0)
    engine = _make_engine(env={"cold": 1}, suit=suit)
    # 3 drain cycles of protection: pool drains 3 -> 2 -> 1 -> 0
    _tick(engine, DRAIN)
    assert suit.current_pools["cold"] == 2
    assert engine.player.fighter.hp == 10
    _tick(engine, DRAIN)
    assert suit.current_pools["cold"] == 1
    assert engine.player.fighter.hp == 10
    _tick(engine, DRAIN)
    assert suit.current_pools["cold"] == 0
    assert engine.player.fighter.hp == 10
    # Next tick: pool is 0, damage begins
    _tick(engine)
    assert engine.player.fighter.hp == 9
    # Another tick: damage continues
    _tick(engine)
    assert engine.player.fighter.hp == 8


def test_env_pool_gives_full_turns_protection():
    """Pool of N should give exactly N drain-cycles of protection."""
    suit = Suit("Test", {"vacuum": 3}, defense_bonus=0)
    engine = _make_engine(env={"vacuum": 1}, suit=suit)

    # Vacuum is spatial: needs an overlay covering the player
    gm = engine.game_map
    overlay = np.full((gm.width, gm.height), fill_value=True, order="F")
    gm.hazard_overlays["vacuum"] = overlay
    gm._hazards_dirty = False

    # 3 drain cycles: no damage
    for _ in range(3 * Suit.DRAIN_INTERVAL):
        apply_environment_tick(engine)
    assert engine.player.fighter.hp == 10
    assert suit.current_pools["vacuum"] == 0

    # Next tick: damage
    apply_environment_tick(engine)
    assert engine.player.fighter.hp == 9
