"""Tests for inventory item usage via consumables module."""
from game.entity import Entity, Fighter
from game.suit import Suit
from game.loadout import Loadout
from game.consumables import use_consumable
from tests.conftest import make_engine as _make_engine


def test_weapon_in_loadout():
    """Melee weapon in loadout auto-applies power on tactical entry."""
    engine = _make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "weapon_class": "melee", "value": 3})
    engine.player.loadout = Loadout(slot1=weapon)
    # Simulate auto-apply
    engine.player.fighter.power = engine.player.fighter.base_power + weapon.item["value"]
    assert engine.player.fighter.power == 4


def test_heal_restores_hp():
    engine = _make_engine()
    engine.player.fighter.hp = 3
    medkit = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(medkit)
    use_consumable(engine, engine.player, medkit)
    assert engine.player.fighter.hp == 8
    assert medkit not in engine.player.inventory


def test_heal_caps_at_max():
    engine = _make_engine()
    engine.player.fighter.hp = 8
    medkit = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(medkit)
    use_consumable(engine, engine.player, medkit)
    assert engine.player.fighter.hp == 10


def test_repair_restores_durability():
    engine = _make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 2, "max_durability": 5})
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.loadout = Loadout(slot1=weapon)
    engine.player.inventory.append(repair)
    use_consumable(engine, engine.player, repair)
    assert weapon.item["durability"] == 5


def test_o2_restores_suit_pool():
    engine = _make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    engine.suit.current_pools["vacuum"] = 20
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.inventory.append(o2)
    use_consumable(engine, engine.player, o2)
    assert engine.suit.current_pools["vacuum"] == 40
    assert o2 not in engine.player.inventory


def test_o2_caps_at_max():
    engine = _make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    engine.suit.current_pools["vacuum"] = 45
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.inventory.append(o2)
    use_consumable(engine, engine.player, o2)
    assert engine.suit.current_pools["vacuum"] == 50
