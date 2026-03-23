"""Tests for GameMap helper methods added in current changes."""

from game.entity import Entity
from tests.conftest import make_arena

# -- get_non_blocking_entity_at -----------------------------------------------


def test_get_non_blocking_entity_returns_item():
    gm = make_arena()
    item = Entity(x=3, y=3, name="Medkit", blocks_movement=False, item={"type": "medkit"})
    gm.entities.append(item)
    assert gm.get_non_blocking_entity_at(3, 3) is item


def test_get_non_blocking_entity_ignores_blocking():
    gm = make_arena()
    from game.entity import Fighter

    enemy = Entity(x=3, y=3, name="Drone", blocks_movement=True, fighter=Fighter(5, 5, 0, 1))
    gm.entities.append(enemy)
    assert gm.get_non_blocking_entity_at(3, 3) is None


def test_get_non_blocking_entity_returns_interactable():
    gm = make_arena()
    obj = Entity(x=4, y=4, name="Console", blocks_movement=False, interactable={"type": "console"})
    gm.entities.append(obj)
    assert gm.get_non_blocking_entity_at(4, 4) is obj


def test_get_non_blocking_entity_none_for_empty():
    gm = make_arena()
    assert gm.get_non_blocking_entity_at(5, 5) is None


def test_get_non_blocking_entity_returns_first_match():
    gm = make_arena()
    a = Entity(x=2, y=2, name="A", blocks_movement=False, item={"type": "a"})
    b = Entity(x=2, y=2, name="B", blocks_movement=False, item={"type": "b"})
    gm.entities.extend([a, b])
    assert gm.get_non_blocking_entity_at(2, 2) is a
