"""Tests for standalone consumable use logic."""
from game.entity import Entity, Fighter
from game.suit import Suit
from game.loadout import Loadout
from game.consumables import use_consumable
from tests.conftest import make_engine


def test_heal_restores_hp():
    engine = make_engine()
    engine.player.fighter.hp = 3
    medkit = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(medkit)
    result = use_consumable(engine, engine.player, medkit)
    assert result is True
    assert engine.player.fighter.hp == 8
    assert medkit not in engine.player.inventory


def test_heal_caps_at_max():
    engine = make_engine()
    engine.player.fighter.hp = 8
    medkit = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(medkit)
    result = use_consumable(engine, engine.player, medkit)
    assert result is True
    assert engine.player.fighter.hp == 10


def test_repair_fixes_equipped_item():
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 2, "max_durability": 5})
    engine.player.loadout = Loadout(slot1=weapon)
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.inventory.append(repair)
    result = use_consumable(engine, engine.player, repair)
    assert result is True
    assert weapon.item["durability"] == 5
    assert repair not in engine.player.inventory


def test_repair_not_consumed_when_nothing_to_repair():
    engine = make_engine()
    engine.player.loadout = Loadout()
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.inventory.append(repair)
    result = use_consumable(engine, engine.player, repair)
    assert result is False
    assert repair in engine.player.inventory


def test_o2_restores_suit_pool():
    engine = make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    engine.suit.current_pools["vacuum"] = 20
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.inventory.append(o2)
    result = use_consumable(engine, engine.player, o2)
    assert result is True
    assert engine.suit.current_pools["vacuum"] == 40
    assert o2 not in engine.player.inventory


def test_o2_caps_at_max():
    engine = make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    engine.suit.current_pools["vacuum"] = 45
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.inventory.append(o2)
    use_consumable(engine, engine.player, o2)
    assert engine.suit.current_pools["vacuum"] == 50


def test_o2_not_consumed_when_no_suit():
    engine = make_engine()
    engine.suit = None
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.inventory.append(o2)
    result = use_consumable(engine, engine.player, o2)
    assert result is False
    assert o2 in engine.player.inventory


def test_repair_fixes_damaged_item():
    """Repair kit restores durability and clears 'damaged' flag on a broken item."""
    engine = make_engine()
    weapon = Entity(name="Baton", item={
        "type": "weapon", "value": 2, "durability": 0, "max_durability": 5, "damaged": True,
    })
    engine.player.loadout = Loadout(slot1=weapon)
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.inventory.append(repair)
    result = use_consumable(engine, engine.player, repair)
    assert result is True
    assert weapon.item["durability"] == 3
    assert weapon.item.get("damaged") is not True


def test_unknown_consumable_returns_false():
    engine = make_engine()
    thing = Entity(name="Thing", item={"type": "unknown", "value": 1})
    engine.player.inventory.append(thing)
    result = use_consumable(engine, engine.player, thing)
    assert result is False
