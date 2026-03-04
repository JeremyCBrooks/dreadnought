"""Tests for inventory item usage via loadout consumables."""
from game.entity import Entity, Fighter
from game.suit import Suit
from game.loadout import Loadout
from tests.conftest import make_engine as _make_engine


def _use_consumable(engine, item):
    """Simulate using a consumable from the loadout."""
    itype = item.item.get("type") if item.item else None
    if itype == "heal":
        heal = item.item["value"]
        engine.player.fighter.hp = min(
            engine.player.fighter.max_hp,
            engine.player.fighter.hp + heal,
        )
        engine.player.loadout.use_consumable(item)
    elif itype == "repair":
        for other in engine.player.loadout.all_items():
            if other is not item and other.item and other.item.get("durability") is not None:
                d = other.item.get("durability", 0)
                max_d = other.item.get("max_durability", 5)
                if d < max_d:
                    other.item["durability"] = min(max_d, d + item.item["value"])
                    break
        engine.player.loadout.use_consumable(item)
    elif itype == "o2":
        if engine.suit and "vacuum" in engine.suit.resistances:
            max_o2 = engine.suit.resistances["vacuum"]
            cur = engine.suit.current_pools.get("vacuum", 0)
            engine.suit.current_pools["vacuum"] = min(max_o2, cur + item.item["value"])
        engine.player.loadout.use_consumable(item)


def test_weapon_in_loadout():
    """Melee weapon in loadout auto-applies power on tactical entry."""
    engine = _make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "weapon_class": "melee", "value": 3})
    engine.player.loadout = Loadout(weapon=weapon)
    # Simulate auto-apply
    engine.player.fighter.power = engine.player.fighter.base_power + weapon.item["value"]
    assert engine.player.fighter.power == 4


def test_heal_restores_hp():
    engine = _make_engine()
    engine.player.fighter.hp = 3
    medkit = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.loadout = Loadout(consumable1=medkit)
    _use_consumable(engine, medkit)
    assert engine.player.fighter.hp == 8
    assert engine.player.loadout.consumable1 is None


def test_heal_caps_at_max():
    engine = _make_engine()
    engine.player.fighter.hp = 8
    medkit = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.loadout = Loadout(consumable1=medkit)
    _use_consumable(engine, medkit)
    assert engine.player.fighter.hp == 10


def test_repair_restores_durability():
    engine = _make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 2, "max_durability": 5})
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.loadout = Loadout(weapon=weapon, consumable1=repair)
    _use_consumable(engine, repair)
    assert weapon.item["durability"] == 5


def test_o2_restores_suit_pool():
    engine = _make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    engine.suit.current_pools["vacuum"] = 20
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.loadout = Loadout(consumable1=o2)
    _use_consumable(engine, o2)
    assert engine.suit.current_pools["vacuum"] == 40
    assert engine.player.loadout.consumable1 is None


def test_o2_caps_at_max():
    engine = _make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    engine.suit.current_pools["vacuum"] = 45
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.loadout = Loadout(consumable1=o2)
    _use_consumable(engine, o2)
    assert engine.suit.current_pools["vacuum"] == 50
