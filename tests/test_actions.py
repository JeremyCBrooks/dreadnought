"""Tests for action classes."""
from game.entity import Entity, Fighter
from game.actions import (
    MovementAction, BumpAction, MeleeAction, WaitAction, PickupAction, DropAction,
)
from tests.conftest import make_arena, MockEngine


def test_movement_into_floor():
    gm = make_arena()
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    MovementAction(1, 0).perform(MockEngine(gm, p), p)
    assert (p.x, p.y) == (6, 5)


def test_movement_blocked_by_wall():
    gm = make_arena()
    p = Entity(x=1, y=1, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    MovementAction(-1, 0).perform(MockEngine(gm, p), p)
    assert (p.x, p.y) == (1, 1)


def test_bump_attacks_enemy():
    gm = make_arena()
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 3))
    e = Entity(x=6, y=5, name="Rat", fighter=Fighter(3, 3, 0, 1))
    gm.entities.extend([p, e])
    eng = MockEngine(gm, p)
    BumpAction(1, 0).perform(eng, p)
    assert e.fighter.hp == 0
    assert e not in gm.entities


def test_melee_minimum_damage():
    gm = make_arena()
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    e = Entity(x=6, y=5, name="Tank", fighter=Fighter(5, 5, 5, 1))
    gm.entities.extend([p, e])
    MeleeAction(e).perform(MockEngine(gm, p), p)
    assert e.fighter.hp == 4


def test_pickup():
    gm = make_arena()
    item = Entity(x=5, y=5, name="Pipe", blocks_movement=False, item={"type": "weapon", "value": 2})
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.extend([p, item])
    eng = MockEngine(gm, p)
    eng.player = p  # PickupAction checks entity is engine.player
    PickupAction().perform(eng, p)
    assert len(p.collection_tank) == 1
    assert p.collection_tank[0].name == "Pipe"
    assert item not in gm.entities


def test_drop():
    gm = make_arena()
    item = Entity(name="Pipe", blocks_movement=False, item={"type": "weapon", "value": 2})
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    p.inventory.append(item)
    gm.entities.append(p)
    DropAction(0).perform(MockEngine(gm, p), p)
    assert len(p.inventory) == 0
    assert item in gm.entities
    assert (item.x, item.y) == (5, 5)


def test_movement_blocked_by_interactable():
    gm = make_arena()
    console = Entity(x=6, y=5, name="Console", blocks_movement=False,
                     interactable={"kind": "console"})
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.extend([p, console])
    MovementAction(1, 0).perform(MockEngine(gm, p), p)
    assert (p.x, p.y) == (5, 5)


def test_bump_blocked_by_interactable():
    gm = make_arena()
    crate = Entity(x=6, y=5, name="Crate", blocks_movement=False,
                   interactable={"kind": "crate"})
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.extend([p, crate])
    BumpAction(1, 0).perform(MockEngine(gm, p), p)
    assert (p.x, p.y) == (5, 5)


def test_wait_does_nothing():
    gm = make_arena()
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    WaitAction().perform(MockEngine(gm, p), p)
    assert (p.x, p.y) == (5, 5)


# -- perform return values (True = turn consumed, False = no-op) --


def test_movement_into_floor_consumes_turn():
    gm = make_arena()
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    assert MovementAction(1, 0).perform(MockEngine(gm, p), p) is True


def test_movement_into_wall_does_not_consume_turn():
    gm = make_arena()
    p = Entity(x=1, y=1, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    assert MovementAction(-1, 0).perform(MockEngine(gm, p), p) is False


def test_bump_into_wall_does_not_consume_turn():
    gm = make_arena()
    p = Entity(x=1, y=1, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    assert BumpAction(-1, 0).perform(MockEngine(gm, p), p) is False


def test_bump_attack_consumes_turn():
    gm = make_arena()
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 3))
    e = Entity(x=6, y=5, name="Rat", fighter=Fighter(3, 3, 0, 1))
    gm.entities.extend([p, e])
    assert BumpAction(1, 0).perform(MockEngine(gm, p), p) is True


def test_wait_consumes_turn():
    gm = make_arena()
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    assert WaitAction().perform(MockEngine(gm, p), p) is True


def test_bump_into_interactable_does_not_consume_turn():
    gm = make_arena()
    crate = Entity(x=6, y=5, name="Crate", blocks_movement=False,
                   interactable={"kind": "crate"})
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.extend([p, crate])
    assert BumpAction(1, 0).perform(MockEngine(gm, p), p) is False
