"""Tests for limited carry capacity (max_inventory on Entity)."""
from game.entity import Entity, Fighter, PLAYER_MAX_INVENTORY
from game.actions import PickupAction, InteractAction
from tests.conftest import make_arena, MockEngine


def test_can_carry_unlimited_when_none():
    """max_inventory=None means unlimited capacity."""
    e = Entity(name="Player")
    assert e.max_inventory is None
    assert e.can_carry() is True


def test_can_carry_true_under_limit():
    e = Entity(name="Player", max_inventory=3)
    e.inventory.append(Entity(name="Item"))
    assert e.can_carry() is True


def test_can_carry_false_at_limit():
    e = Entity(name="Player", max_inventory=2)
    e.inventory.append(Entity(name="A"))
    e.inventory.append(Entity(name="B"))
    assert e.can_carry() is False


def test_can_carry_false_over_limit():
    """If somehow over limit, can_carry should still be False."""
    e = Entity(name="Player", max_inventory=1)
    e.inventory.extend([Entity(name="A"), Entity(name="B")])
    assert e.can_carry() is False


def test_player_max_inventory_constant():
    assert PLAYER_MAX_INVENTORY == 10


def test_pickup_succeeds_under_limit():
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1),
                    max_inventory=3)
    item = Entity(x=5, y=5, name="Wrench", blocks_movement=False,
                  item={"type": "weapon", "value": 1})
    gm.entities.extend([player, item])
    eng = MockEngine(gm, player)

    result = PickupAction().perform(eng, player)
    assert result == 1
    assert item in player.inventory


def test_pickup_refused_when_full():
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1),
                    max_inventory=1)
    player.inventory.append(Entity(name="Existing"))
    item = Entity(x=5, y=5, name="Wrench", blocks_movement=False,
                  item={"type": "weapon", "value": 1})
    gm.entities.extend([player, item])
    eng = MockEngine(gm, player)

    result = PickupAction().perform(eng, player)
    assert result == 0
    assert item not in player.inventory
    assert item in gm.entities
    assert any("full" in m[0].lower() for m in eng.message_log.messages)


def test_pickup_unlimited_when_no_max():
    """Without max_inventory, pickup always works."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    for i in range(20):
        player.inventory.append(Entity(name=f"Item{i}"))
    item = Entity(x=5, y=5, name="NewItem", blocks_movement=False,
                  item={"type": "weapon", "value": 1})
    gm.entities.extend([player, item])
    eng = MockEngine(gm, player)

    result = PickupAction().perform(eng, player)
    assert result == 1
    assert item in player.inventory


def test_interact_loot_refused_when_full():
    """InteractAction should refuse to open container when inventory is full."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1),
                    max_inventory=1)
    player.inventory.append(Entity(name="Existing"))
    crate = Entity(x=6, y=5, name="Crate", blocks_movement=False,
                   interactable={
                       "kind": "crate",
                       "loot": {"char": "!", "color": (255, 255, 255),
                                "name": "Medkit", "type": "consumable", "value": 5},
                   })
    gm.entities.extend([player, crate])
    eng = MockEngine(gm, player)

    result = InteractAction(dx=1, dy=0).perform(eng, player)
    # Action blocked: no turn consumed, container preserved
    assert result == 0
    assert len(player.inventory) == 1  # still just "Existing"
    assert crate in gm.entities  # container NOT removed
    assert any("full" in m[0].lower() for m in eng.message_log.messages)


def test_interact_empty_container_refused_when_full():
    """InteractAction should refuse to open even empty containers when inventory is full."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1),
                    max_inventory=1)
    player.inventory.append(Entity(name="Existing"))
    crate = Entity(x=6, y=5, name="Crate", blocks_movement=False,
                   interactable={"kind": "crate"})
    gm.entities.extend([player, crate])
    eng = MockEngine(gm, player)

    result = InteractAction(dx=1, dy=0).perform(eng, player)
    assert result == 0
    assert crate in gm.entities
    assert any("full" in m[0].lower() for m in eng.message_log.messages)


def test_can_carry_counts_loadout_items():
    """Equipped items are in inventory, so they count toward capacity."""
    from game.loadout import Loadout
    weapon = Entity(name="Weapon")
    scanner = Entity(name="Scanner")
    e = Entity(name="Player", max_inventory=5)
    e.inventory.extend([Entity(name="A"), Entity(name="B"), weapon, scanner])
    e.loadout = Loadout(slot1=weapon, slot2=scanner)
    # 4 items in inventory (2 equipped) → can carry
    assert e.can_carry() is True
    e.inventory.append(Entity(name="C"))
    # 5/5 → cannot carry
    assert e.can_carry() is False


def test_can_carry_with_loadout_under_limit():
    from game.loadout import Loadout
    weapon = Entity(name="Weapon")
    e = Entity(name="Player", max_inventory=10)
    e.inventory.append(weapon)
    e.loadout = Loadout(slot1=weapon)
    # 1 item in inventory (equipped) → can carry
    assert e.can_carry() is True


def test_can_carry_no_loadout_unchanged():
    """Without a loadout, can_carry only counts inventory."""
    e = Entity(name="Player", max_inventory=2)
    e.inventory.append(Entity(name="A"))
    assert e.can_carry() is True
    e.inventory.append(Entity(name="B"))
    assert e.can_carry() is False


def test_interact_loot_succeeds_under_limit():
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1),
                    max_inventory=3)
    crate = Entity(x=6, y=5, name="Crate", blocks_movement=False,
                   interactable={
                       "kind": "crate",
                       "loot": {"char": "!", "color": (255, 255, 255),
                                "name": "Medkit", "type": "consumable", "value": 5},
                   })
    gm.entities.extend([player, crate])
    eng = MockEngine(gm, player)

    result = InteractAction(dx=1, dy=0).perform(eng, player)
    assert result == 1
    assert any(i.name == "Medkit" for i in player.inventory)
