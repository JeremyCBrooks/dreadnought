"""Tests for Entity and Fighter."""
from game.entity import Entity, Fighter


def test_entity_defaults():
    e = Entity()
    assert e.x == 0
    assert e.y == 0
    assert e.char == "?"
    assert e.blocks_movement is True
    assert e.inventory == []
    assert e.loadout is None


def test_entity_with_fighter():
    f = Fighter(hp=10, max_hp=10, defense=0, power=1)
    e = Entity(fighter=f)
    assert e.fighter.hp == 10
    assert e.fighter.power == 1


def test_fighter_takes_damage():
    f = Fighter(hp=10, max_hp=10, defense=0, power=1)
    f.hp -= 3
    assert f.hp == 7


def test_entity_inventory():
    player = Entity(name="Player")
    item = Entity(name="Sword", blocks_movement=False)
    player.inventory.append(item)
    assert len(player.inventory) == 1
    assert player.inventory[0].name == "Sword"


def test_separate_inventories():
    a = Entity(name="A")
    b = Entity(name="B")
    a.inventory.append(Entity(name="item"))
    assert len(b.inventory) == 0
