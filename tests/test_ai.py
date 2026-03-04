"""Tests for HostileAI behaviour."""
from game.entity import Entity, Fighter
from game.ai import HostileAI
from tests.conftest import make_arena, MockEngine


def test_hostile_wanders_when_not_visible():
    gm = make_arena()
    player = Entity(x=1, y=1, fighter=Fighter(10, 10, 0, 1))
    enemy = Entity(x=5, y=5, fighter=Fighter(3, 3, 0, 1), ai=HostileAI())
    gm.entities.extend([player, enemy])
    # FOV not updated, so enemy tile is not visible
    gm.visible[:] = False
    engine = MockEngine(gm, player)
    enemy.ai.perform(enemy, engine)
    # Enemy should wander (move to an adjacent tile) rather than idle
    dist = abs(enemy.x - 5) + abs(enemy.y - 5)
    assert dist <= 2  # moved at most 1 step diagonally


def test_hostile_chase_when_visible():
    gm = make_arena()
    player = Entity(x=1, y=1, fighter=Fighter(10, 10, 0, 1))
    enemy = Entity(x=4, y=4, fighter=Fighter(3, 3, 0, 1), ai=HostileAI())
    gm.entities.extend([player, enemy])
    gm.visible[:] = True
    engine = MockEngine(gm, player)
    old_x, old_y = enemy.x, enemy.y
    enemy.ai.perform(enemy, engine)
    # Enemy should have moved closer
    new_dist = max(abs(enemy.x - player.x), abs(enemy.y - player.y))
    old_dist = max(abs(old_x - player.x), abs(old_y - player.y))
    assert new_dist < old_dist


def test_hostile_attack_when_adjacent():
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    enemy = Entity(x=6, y=5, name="Rat", fighter=Fighter(3, 3, 0, 2), ai=HostileAI())
    gm.entities.extend([player, enemy])
    gm.visible[:] = True
    engine = MockEngine(gm, player)
    enemy.ai.perform(enemy, engine)
    # Enemy should attack, dealing damage
    assert player.fighter.hp < 10
    # Enemy should NOT have moved
    assert (enemy.x, enemy.y) == (6, 5)
