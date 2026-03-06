"""Tests for the Loadout data model (2 generic equipment slots)."""
from game.entity import Entity
from game.loadout import Loadout, is_equippable


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


# --- is_equippable ---

def test_is_equippable_weapon():
    assert is_equippable(_weapon()) is True

def test_is_equippable_scanner():
    assert is_equippable(_scanner()) is True

def test_is_equippable_heal():
    assert is_equippable(_heal()) is False

def test_is_equippable_repair():
    assert is_equippable(_repair()) is False

def test_is_equippable_o2():
    assert is_equippable(_o2()) is False

def test_is_equippable_no_item():
    e = Entity(name="Rock")
    assert is_equippable(e) is False

def test_is_equippable_unknown_type():
    e = Entity(name="Gizmo", item={"type": "unknown", "value": 1})
    assert is_equippable(e) is False


# --- Loadout basics ---

def test_loadout_defaults_empty():
    lo = Loadout()
    assert lo.slot1 is None
    assert lo.slot2 is None
    assert lo.all_items() == []


def test_loadout_all_items():
    w = _weapon()
    t = _scanner()
    lo = Loadout(slot1=w, slot2=t)
    assert lo.all_items() == [w, t]


def test_loadout_all_items_partial():
    w = _weapon()
    lo = Loadout(slot1=w)
    assert lo.all_items() == [w]


# --- has_item ---

def test_has_item_true():
    w = _weapon()
    lo = Loadout(slot1=w)
    assert lo.has_item(w) is True

def test_has_item_false():
    lo = Loadout()
    assert lo.has_item(_weapon()) is False

def test_has_item_slot2():
    t = _scanner()
    lo = Loadout(slot2=t)
    assert lo.has_item(t) is True


# --- remove_item ---

def test_remove_item_slot1():
    w = _weapon()
    lo = Loadout(slot1=w)
    assert lo.remove_item(w) is True
    assert lo.slot1 is None

def test_remove_item_slot2():
    t = _scanner()
    lo = Loadout(slot2=t)
    assert lo.remove_item(t) is True
    assert lo.slot2 is None

def test_remove_item_not_found():
    lo = Loadout()
    assert lo.remove_item(_weapon()) is False


# --- equip ---

def test_equip_into_empty_slot1():
    lo = Loadout()
    w = _weapon()
    result = lo.equip(w)
    assert result is None
    assert lo.slot1 is w

def test_equip_into_slot2_when_slot1_full():
    w = _weapon()
    t = _scanner()
    lo = Loadout(slot1=w)
    result = lo.equip(t)
    assert result is None
    assert lo.slot2 is t

def test_equip_when_both_full():
    w = _weapon()
    t = _scanner()
    lo = Loadout(slot1=w, slot2=t)
    new = _weapon("Pipe")
    result = lo.equip(new)
    assert result is None  # returns None, loadout unchanged when full
    assert lo.is_full()


# --- unequip ---

def test_unequip_slot1():
    w = _weapon()
    lo = Loadout(slot1=w)
    result = lo.unequip(w)
    assert result is w
    assert lo.slot1 is None

def test_unequip_slot2():
    t = _scanner()
    lo = Loadout(slot2=t)
    result = lo.unequip(t)
    assert result is t
    assert lo.slot2 is None

def test_unequip_not_found():
    lo = Loadout()
    assert lo.unequip(_weapon()) is None


# --- is_full ---

def test_is_full_empty():
    lo = Loadout()
    assert lo.is_full() is False

def test_is_full_one():
    lo = Loadout(slot1=_weapon())
    assert lo.is_full() is False

def test_is_full_both():
    lo = Loadout(slot1=_weapon(), slot2=_scanner())
    assert lo.is_full() is True


# --- get_ranged_weapon ---

def test_get_ranged_weapon_slot1():
    w = _weapon(weapon_class="ranged", ammo=5)
    lo = Loadout(slot1=w)
    assert lo.get_ranged_weapon() is w

def test_get_ranged_weapon_slot2():
    w = _weapon(weapon_class="ranged", ammo=5)
    lo = Loadout(slot2=w)
    assert lo.get_ranged_weapon() is w

def test_get_ranged_weapon_melee_returns_none():
    w = _weapon(weapon_class="melee", ammo=0)
    lo = Loadout(slot1=w)
    assert lo.get_ranged_weapon() is None

def test_get_ranged_weapon_no_ammo():
    w = _weapon(weapon_class="ranged", ammo=0)
    lo = Loadout(slot1=w)
    assert lo.get_ranged_weapon() is None

def test_get_ranged_weapon_empty():
    lo = Loadout()
    assert lo.get_ranged_weapon() is None


# --- get_scanner ---

def test_get_scanner_slot1():
    t = _scanner()
    lo = Loadout(slot1=t)
    assert lo.get_scanner() is t

def test_get_scanner_slot2():
    t = _scanner()
    lo = Loadout(slot2=t)
    assert lo.get_scanner() is t

def test_get_scanner_non_scanner():
    t = Entity(name="Gizmo", item={"type": "weapon", "value": 1})
    lo = Loadout(slot1=t)
    assert lo.get_scanner() is None

def test_get_scanner_empty():
    lo = Loadout()
    assert lo.get_scanner() is None


# --- get_all_scanners ---

def test_get_all_scanners_empty():
    lo = Loadout()
    assert lo.get_all_scanners() == []

def test_get_all_scanners_one():
    s = _scanner()
    lo = Loadout(slot1=s)
    assert lo.get_all_scanners() == [s]

def test_get_all_scanners_two():
    s1 = _scanner(tier=1)
    s2 = _scanner(tier=2)
    lo = Loadout(slot1=s1, slot2=s2)
    assert lo.get_all_scanners() == [s1, s2]

def test_get_all_scanners_mixed():
    w = _weapon()
    s = _scanner()
    lo = Loadout(slot1=w, slot2=s)
    assert lo.get_all_scanners() == [s]


# --- items_with_durability ---

def test_items_with_durability():
    w = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 3, "max_durability": 5})
    t = _scanner()  # no durability
    lo = Loadout(slot1=w, slot2=t)
    assert lo.items_with_durability() == [w]

def test_items_with_durability_zero():
    w = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 0, "max_durability": 5})
    lo = Loadout(slot1=w)
    assert lo.items_with_durability() == []

def test_items_with_durability_empty():
    lo = Loadout()
    assert lo.items_with_durability() == []
