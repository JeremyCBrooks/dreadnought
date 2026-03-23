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


def test_fighter_base_power_tracks_initial():
    f = Fighter(hp=5, max_hp=5, defense=1, power=7)
    assert f.base_power == 7
    f.power = 12
    assert f.base_power == 7  # base_power is snapshot of initial power


def test_can_carry_unlimited():
    e = Entity(max_inventory=None)
    assert e.can_carry() is True


def test_can_carry_with_room():
    e = Entity(max_inventory=3)
    e.inventory.append(Entity(name="a"))
    e.inventory.append(Entity(name="b"))
    assert e.can_carry() is True


def test_can_carry_full():
    e = Entity(max_inventory=2)
    e.inventory.append(Entity(name="a"))
    e.inventory.append(Entity(name="b"))
    assert e.can_carry() is False


def test_fighter_repr():
    f = Fighter(hp=8, max_hp=10, defense=2, power=3)
    r = repr(f)
    assert "Fighter" in r
    assert "8/10" in r


def test_entity_repr():
    e = Entity(x=5, y=3, name="Guard", char="g")
    r = repr(e)
    assert "Guard" in r
    assert "5" in r
    assert "3" in r


def test_entity_slots_prevent_arbitrary_attrs():
    e = Entity()
    try:
        e.nonexistent_attr = 42  # type: ignore[attr-defined]
        has_slots = False
    except AttributeError:
        has_slots = True
    assert has_slots, "Entity should use __slots__"
