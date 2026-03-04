"""Tests for the Loadout data model."""
from game.entity import Entity
from game.loadout import Loadout, SlotType, item_slot_type, ITEM_TYPE_TO_SLOT


def _weapon(name="Blaster", weapon_class="ranged", ammo=5, value=3):
    return Entity(name=name, item={
        "type": "weapon", "weapon_class": weapon_class,
        "value": value, "ammo": ammo, "max_ammo": 20,
    })


def _scanner(tier=1):
    return Entity(name="Scanner", item={"type": "scanner", "scanner_tier": tier, "value": tier})


def _heal(value=5):
    return Entity(name="Med-kit", item={"type": "heal", "value": value})


def _repair(value=3):
    return Entity(name="Repair Kit", item={"type": "repair", "value": value})


def _o2(value=20):
    return Entity(name="O2 Canister", item={"type": "o2", "value": value})


# --- item_slot_type ---

def test_item_slot_type_weapon():
    assert item_slot_type(_weapon()) == SlotType.WEAPON

def test_item_slot_type_scanner():
    assert item_slot_type(_scanner()) == SlotType.TOOL

def test_item_slot_type_heal():
    assert item_slot_type(_heal()) == SlotType.CONSUMABLE

def test_item_slot_type_repair():
    assert item_slot_type(_repair()) == SlotType.CONSUMABLE

def test_item_slot_type_o2():
    assert item_slot_type(_o2()) == SlotType.CONSUMABLE

def test_item_slot_type_no_item():
    e = Entity(name="Rock")
    assert item_slot_type(e) is None

def test_item_slot_type_unknown_type():
    e = Entity(name="Gizmo", item={"type": "unknown", "value": 1})
    assert item_slot_type(e) is None


# --- Loadout basics ---

def test_loadout_defaults_empty():
    lo = Loadout()
    assert lo.weapon is None
    assert lo.tool is None
    assert lo.consumable1 is None
    assert lo.consumable2 is None
    assert lo.all_items() == []


def test_loadout_all_items():
    w = _weapon()
    t = _scanner()
    c1 = _heal()
    c2 = _o2()
    lo = Loadout(weapon=w, tool=t, consumable1=c1, consumable2=c2)
    assert lo.all_items() == [w, t, c1, c2]


def test_loadout_all_items_partial():
    w = _weapon()
    lo = Loadout(weapon=w)
    assert lo.all_items() == [w]


# --- has_item ---

def test_has_item_true():
    w = _weapon()
    lo = Loadout(weapon=w)
    assert lo.has_item(w) is True

def test_has_item_false():
    lo = Loadout()
    assert lo.has_item(_weapon()) is False


# --- remove_item ---

def test_remove_item_weapon():
    w = _weapon()
    lo = Loadout(weapon=w)
    assert lo.remove_item(w) is True
    assert lo.weapon is None

def test_remove_item_tool():
    t = _scanner()
    lo = Loadout(tool=t)
    assert lo.remove_item(t) is True
    assert lo.tool is None

def test_remove_item_consumable1():
    c = _heal()
    lo = Loadout(consumable1=c)
    assert lo.remove_item(c) is True
    assert lo.consumable1 is None

def test_remove_item_consumable2():
    c = _o2()
    lo = Loadout(consumable2=c)
    assert lo.remove_item(c) is True
    assert lo.consumable2 is None

def test_remove_item_not_found():
    lo = Loadout()
    assert lo.remove_item(_weapon()) is False


# --- use_consumable ---

def test_use_consumable1():
    c = _heal()
    lo = Loadout(consumable1=c)
    assert lo.use_consumable(c) is True
    assert lo.consumable1 is None

def test_use_consumable2():
    c = _o2()
    lo = Loadout(consumable2=c)
    assert lo.use_consumable(c) is True
    assert lo.consumable2 is None

def test_use_consumable_weapon_fails():
    w = _weapon()
    lo = Loadout(weapon=w)
    assert lo.use_consumable(w) is False

def test_use_consumable_not_found():
    lo = Loadout()
    assert lo.use_consumable(_heal()) is False


# --- get_ranged_weapon ---

def test_get_ranged_weapon_found():
    w = _weapon(weapon_class="ranged", ammo=5)
    lo = Loadout(weapon=w)
    assert lo.get_ranged_weapon() is w

def test_get_ranged_weapon_melee_returns_none():
    w = _weapon(weapon_class="melee", ammo=0)
    lo = Loadout(weapon=w)
    assert lo.get_ranged_weapon() is None

def test_get_ranged_weapon_no_ammo():
    w = _weapon(weapon_class="ranged", ammo=0)
    lo = Loadout(weapon=w)
    assert lo.get_ranged_weapon() is None

def test_get_ranged_weapon_empty():
    lo = Loadout()
    assert lo.get_ranged_weapon() is None


# --- get_scanner ---

def test_get_scanner_found():
    t = _scanner()
    lo = Loadout(tool=t)
    assert lo.get_scanner() is t

def test_get_scanner_non_scanner_tool():
    t = Entity(name="Gizmo", item={"type": "weapon", "value": 1})
    lo = Loadout(tool=t)
    assert lo.get_scanner() is None

def test_get_scanner_empty():
    lo = Loadout()
    assert lo.get_scanner() is None


# --- items_with_durability ---

def test_items_with_durability():
    w = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 3, "max_durability": 5})
    t = _scanner()  # no durability
    c = _heal()  # no durability
    lo = Loadout(weapon=w, tool=t, consumable1=c)
    assert lo.items_with_durability() == [w]

def test_items_with_durability_zero():
    w = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 0, "max_durability": 5})
    lo = Loadout(weapon=w)
    assert lo.items_with_durability() == []

def test_items_with_durability_empty():
    lo = Loadout()
    assert lo.items_with_durability() == []


# --- ITEM_TYPE_TO_SLOT mapping ---

def test_all_consumable_types_map_to_consumable():
    for t in ("heal", "repair", "o2"):
        assert ITEM_TYPE_TO_SLOT[t] == SlotType.CONSUMABLE
