"""Tests for standalone consumable use logic."""

from game.consumables import use_consumable
from game.entity import Entity
from game.loadout import Loadout
from game.suit import Suit
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
    weapon = Entity(
        name="Baton",
        item={
            "type": "weapon",
            "value": 2,
            "durability": 0,
            "max_durability": 5,
            "damaged": True,
        },
    )
    engine.player.loadout = Loadout(slot1=weapon)
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.inventory.append(repair)
    result = use_consumable(engine, engine.player, repair)
    assert result is True
    assert weapon.item["durability"] == 3
    assert weapon.item.get("damaged") is not True


def test_heal_not_consumed_at_full_hp():
    """Healing at full HP should not waste the consumable."""
    engine = make_engine()
    engine.player.fighter.hp = engine.player.fighter.max_hp
    medkit = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(medkit)
    result = use_consumable(engine, engine.player, medkit)
    assert result is False
    assert medkit in engine.player.inventory


def test_repair_not_consumed_when_all_at_full_durability():
    """Repair kit should not be consumed when all equipped items are at max durability."""
    engine = make_engine()
    weapon = Entity(
        name="Baton",
        item={"type": "weapon", "value": 2, "durability": 5, "max_durability": 5},
    )
    engine.player.loadout = Loadout(slot1=weapon)
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.inventory.append(repair)
    result = use_consumable(engine, engine.player, repair)
    assert result is False
    assert repair in engine.player.inventory


def test_o2_not_consumed_when_pool_full():
    """O2 canister should not be consumed when suit pool is already full."""
    engine = make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    engine.suit.current_pools["vacuum"] = 50
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.inventory.append(o2)
    result = use_consumable(engine, engine.player, o2)
    assert result is False
    assert o2 in engine.player.inventory


def test_consumable_with_no_item_dict():
    """An entity with item=None should return False."""
    engine = make_engine()
    thing = Entity(name="Thing", item=None)
    result = use_consumable(engine, engine.player, thing)
    assert result is False


def test_unknown_consumable_returns_false():
    engine = make_engine()
    thing = Entity(name="Thing", item={"type": "unknown", "value": 1})
    engine.player.inventory.append(thing)
    result = use_consumable(engine, engine.player, thing)
    assert result is False


def test_heal_message_reports_actual_amount():
    """Heal message should report actual HP restored, not the item's full value."""
    engine = make_engine()
    engine.player.fighter.hp = 8  # 8/10, only 2 can be healed
    medkit = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(medkit)
    use_consumable(engine, engine.player, medkit)
    last_text = engine.message_log.messages[-1][0]
    assert "2" in last_text
    assert "5" not in last_text


def test_repair_recalcs_melee_power():
    """Repairing a damaged melee weapon should restore its melee power bonus."""
    engine = make_engine()
    weapon = Entity(
        name="Baton",
        item={
            "type": "weapon",
            "weapon_class": "melee",
            "value": 3,
            "durability": 0,
            "max_durability": 5,
            "damaged": True,
        },
    )
    engine.player.loadout = Loadout(slot1=weapon)
    engine.player.inventory.append(weapon)
    # Damaged weapon should not contribute to melee power
    from game.loadout import recalc_melee_power

    recalc_melee_power(engine.player)
    assert engine.player.fighter.power == engine.player.fighter.base_power
    # Repair it
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 5})
    engine.player.inventory.append(repair)
    use_consumable(engine, engine.player, repair)
    # Melee power should now include the weapon bonus
    assert engine.player.fighter.power == engine.player.fighter.base_power + 3
