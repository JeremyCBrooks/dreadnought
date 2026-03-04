"""Tests for environment tick system."""
from game.environment import apply_environment_tick
from game.suit import Suit
from tests.conftest import make_engine as _make_engine


def test_no_damage_with_suit_pool():
    suit = Suit("Test", {"vacuum": 10}, defense_bonus=0)
    engine = _make_engine(env={"vacuum": 1}, suit=suit)
    apply_environment_tick(engine)
    assert engine.player.fighter.hp == 10
    assert suit.current_pools["vacuum"] == 9


def test_damage_when_pool_depleted():
    suit = Suit("Test", {"vacuum": 1}, defense_bonus=0)
    engine = _make_engine(env={"vacuum": 1}, suit=suit)
    # First tick: pool drains from 1 to 0, no damage yet (1 full turn of protection)
    apply_environment_tick(engine)
    assert suit.current_pools["vacuum"] == 0
    assert engine.player.fighter.hp == 10
    # Second tick: pool is 0, damage dealt
    apply_environment_tick(engine)
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
    # 3 turns of protection: pool drains 3 -> 2 -> 1 -> 0
    apply_environment_tick(engine)
    assert suit.current_pools["cold"] == 2
    assert engine.player.fighter.hp == 10
    apply_environment_tick(engine)
    assert suit.current_pools["cold"] == 1
    assert engine.player.fighter.hp == 10
    apply_environment_tick(engine)
    assert suit.current_pools["cold"] == 0
    assert engine.player.fighter.hp == 10
    # Fourth tick: pool is 0, damage begins
    apply_environment_tick(engine)
    assert engine.player.fighter.hp == 9
    # Fifth tick: damage continues
    apply_environment_tick(engine)
    assert engine.player.fighter.hp == 8
