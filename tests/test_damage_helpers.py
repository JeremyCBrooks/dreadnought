"""Tests for _calc_damage and _apply_damage_and_death helpers."""

import debug
from game.actions import _apply_damage_and_death, _calc_damage
from game.entity import Entity, Fighter
from game.suit import Suit
from tests.conftest import make_engine

# -- _calc_damage -------------------------------------------------------------


def test_calc_damage_basic():
    eng = make_engine()
    target = Entity(x=6, y=5, name="Drone", fighter=Fighter(10, 10, 2, 1))
    eng.game_map.entities.append(target)
    # power=5, defense=2 -> max(1, 5-2) = 3
    assert _calc_damage(eng, eng.player, target, 5) == 3


def test_calc_damage_minimum_one():
    eng = make_engine()
    target = Entity(x=6, y=5, name="Tank", fighter=Fighter(10, 10, 99, 1))
    eng.game_map.entities.append(target)
    assert _calc_damage(eng, eng.player, target, 1) == 1


def test_calc_damage_suit_defense_bonus_for_player():
    eng = make_engine(suit=Suit("Test Suit", {"vacuum": 10}, defense_bonus=3))
    attacker = Entity(x=6, y=5, name="Drone", fighter=Fighter(10, 10, 0, 5))
    eng.game_map.entities.append(attacker)
    # player defense=0, suit bonus=3, power=5 -> max(1, 5-(0+3)) = 2
    assert _calc_damage(eng, attacker, eng.player, 5) == 2


def test_calc_damage_god_mode_zeroes_player_damage():
    eng = make_engine()
    attacker = Entity(x=6, y=5, name="Drone", fighter=Fighter(10, 10, 0, 5))
    eng.game_map.entities.append(attacker)
    debug.GOD_MODE = True
    assert _calc_damage(eng, attacker, eng.player, 5) == 0


def test_calc_damage_one_hit_kill():
    eng = make_engine()
    target = Entity(x=6, y=5, name="Drone", fighter=Fighter(50, 50, 99, 1))
    eng.game_map.entities.append(target)
    debug.ONE_HIT_KILL = True
    assert _calc_damage(eng, eng.player, target, 1) == 50


# -- _apply_damage_and_death --------------------------------------------------


def test_apply_damage_reduces_hp():
    eng = make_engine()
    target = Entity(x=6, y=5, name="Drone", fighter=Fighter(10, 10, 0, 1))
    eng.game_map.entities.append(target)
    _apply_damage_and_death(eng, eng.player, target, 3)
    assert target.fighter.hp == 7


def test_apply_damage_kills_enemy():
    eng = make_engine()
    target = Entity(x=6, y=5, name="Drone", fighter=Fighter(5, 5, 0, 1))
    eng.game_map.entities.append(target)
    _apply_damage_and_death(eng, eng.player, target, 5)
    assert target.fighter.hp == 0
    assert target not in eng.game_map.entities


def test_apply_damage_kills_player_message():
    eng = make_engine()
    _apply_damage_and_death(eng, eng.player, eng.player, 999)
    assert eng.player.fighter.hp == 0
    assert any("die" in m[0].lower() for m in eng.message_log._messages)


def test_apply_damage_enemy_death_message():
    eng = make_engine()
    target = Entity(x=6, y=5, name="Drone", fighter=Fighter(1, 1, 0, 1))
    eng.game_map.entities.append(target)
    _apply_damage_and_death(eng, eng.player, target, 1)
    assert any("destroyed" in m[0].lower() for m in eng.message_log._messages)


# -- Melee HP floor / suit defense ------------------------------------------


def test_melee_hp_floor_at_zero():
    from game.actions import MeleeAction
    from tests.conftest import MockEngine, make_arena

    gm = make_arena()
    attacker = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 10))
    target = Entity(x=6, y=5, name="Rat", fighter=Fighter(3, 3, 0, 1))
    gm.entities.extend([attacker, target])
    MeleeAction(target).perform(MockEngine(gm, attacker), attacker)
    assert target.fighter.hp == 0  # Not negative


def test_melee_hp_cannot_go_negative():
    from game.actions import MeleeAction
    from tests.conftest import MockEngine, make_arena

    gm = make_arena()
    attacker = Entity(x=5, y=5, name="Big", fighter=Fighter(10, 10, 0, 100))
    target = Entity(x=6, y=5, name="Weak", fighter=Fighter(1, 1, 0, 1))
    gm.entities.extend([attacker, target])
    MeleeAction(target).perform(MockEngine(gm, attacker), attacker)
    assert target.fighter.hp == 0


def test_melee_suit_defense_reduces_damage():
    from game.actions import MeleeAction
    from game.ai import HostileAI
    from tests.conftest import MockEngine, make_arena

    gm = make_arena()
    suit = Suit("Armor", {}, defense_bonus=2)
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    enemy = Entity(x=6, y=5, name="Rat", fighter=Fighter(3, 3, 0, 3), ai=HostileAI())
    gm.entities.extend([player, enemy])
    eng = MockEngine(gm, player, suit=suit)
    # Enemy power=3, player defense=0 + suit bonus=2, so damage = max(1, 3-2) = 1
    MeleeAction(player).perform(eng, enemy)
    assert player.fighter.hp == 9  # Only 1 damage
