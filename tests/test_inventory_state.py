"""Tests for the InventoryState (two-section: EQUIPPED + INVENTORY)."""
import tcod.event

from game.entity import Entity, Fighter
from game.suit import Suit
from game.loadout import Loadout
from ui.inventory_state import InventoryState
from tests.conftest import make_engine


class FakeEvent:
    def __init__(self, sym):
        self.sym = sym


def _press(state, engine, sym):
    return state.ev_keydown(engine, FakeEvent(sym))


# --- Equipped section ---

def test_equipped_section_shows_slots():
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "value": 1})
    engine.player.loadout = Loadout(slot1=weapon, slot2=scanner)

    state = InventoryState()
    slots = state._equipped_slots(engine)
    assert len(slots) == 2
    assert slots[0] == ("S1", weapon)
    assert slots[1] == ("S2", scanner)


def test_unequip_via_equipped():
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    engine.player.loadout = Loadout(slot1=weapon)

    state = InventoryState()
    state.selected = 0  # S1 slot
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert engine.player.loadout.slot1 is None
    assert weapon in engine.player.inventory


def test_equip_from_inventory():
    engine = make_engine()
    engine.player.loadout = Loadout()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    engine.player.inventory.append(weapon)

    state = InventoryState()
    state._section = 1  # inventory
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert engine.player.loadout.slot1 is weapon
    assert weapon not in engine.player.inventory


def test_use_consumable_from_inventory():
    engine = make_engine()
    engine.player.fighter.hp = 3
    engine.player.loadout = Loadout()
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(heal)

    state = InventoryState()
    state._section = 1  # inventory
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert engine.player.fighter.hp == 8
    assert heal not in engine.player.inventory


def test_heal_caps_at_max():
    engine = make_engine()
    engine.player.fighter.hp = 8
    engine.player.loadout = Loadout()
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(heal)

    state = InventoryState()
    state._section = 1
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert engine.player.fighter.hp == 10


def test_repair_via_inventory():
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 2, "max_durability": 5})
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.loadout = Loadout(slot1=weapon)
    engine.player.inventory.append(repair)

    state = InventoryState()
    state._section = 1
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert weapon.item["durability"] == 5
    assert repair not in engine.player.inventory


def test_repair_not_consumed_when_nothing_to_repair():
    engine = make_engine()
    engine.player.loadout = Loadout()
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.inventory.append(repair)

    state = InventoryState()
    state._section = 1
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert repair in engine.player.inventory
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("No damaged items" in m for m in msgs)


def test_o2_via_inventory():
    engine = make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    engine.suit.current_pools["vacuum"] = 20
    engine.player.loadout = Loadout()
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.inventory.append(o2)

    state = InventoryState()
    state._section = 1
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert engine.suit.current_pools["vacuum"] == 40
    assert o2 not in engine.player.inventory


def test_o2_not_consumed_when_no_suit():
    engine = make_engine()
    engine.suit = None
    engine.player.loadout = Loadout()
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.inventory.append(o2)

    state = InventoryState()
    state._section = 1
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert o2 in engine.player.inventory
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("No suit O2" in m for m in msgs)


def test_equip_when_full():
    """Equipping when both slots full should show message."""
    engine = make_engine()
    w1 = Entity(name="Baton", item={"type": "weapon", "value": 3})
    w2 = Entity(name="Pipe", item={"type": "weapon", "value": 2})
    engine.player.loadout = Loadout(slot1=w1, slot2=w2)
    w3 = Entity(name="Rifle", item={"type": "weapon", "weapon_class": "ranged", "value": 5, "ammo": 5, "max_ammo": 20})
    engine.player.inventory.append(w3)

    state = InventoryState()
    state._section = 1
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.RETURN)

    # Slots full, item stays in inventory
    assert w3 in engine.player.inventory
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("full" in m.lower() for m in msgs)


# --- Navigation ---

def test_navigation_up_down():
    engine = make_engine()
    engine.player.loadout = Loadout(
        slot1=Entity(name="W", item={"type": "weapon", "value": 1}),
        slot2=Entity(name="T", item={"type": "scanner", "scanner_tier": 1, "value": 1}),
    )

    state = InventoryState()
    assert state.selected == 0

    _press(state, engine, tcod.event.KeySym.DOWN)
    assert state.selected == 1

    # Can't go past 2 slots
    _press(state, engine, tcod.event.KeySym.DOWN)
    assert state.selected == 1

    _press(state, engine, tcod.event.KeySym.UP)
    assert state.selected == 0


# --- Tab switching ---

def test_tab_switches_section():
    engine = make_engine()
    engine.player.loadout = Loadout()

    state = InventoryState()
    assert state._section == 0

    _press(state, engine, tcod.event.KeySym.RIGHT)
    assert state._section == 1
    assert state.selected == 0

    _press(state, engine, tcod.event.KeySym.LEFT)
    assert state._section == 0


# --- Inventory navigation ---

def test_inventory_navigation():
    engine = make_engine()
    engine.player.loadout = Loadout()
    engine.player.inventory.extend([
        Entity(name="A", item={"type": "weapon", "value": 1}),
        Entity(name="B", item={"type": "heal", "value": 5}),
    ])

    state = InventoryState()
    _press(state, engine, tcod.event.KeySym.RIGHT)  # switch to inventory
    assert state.selected == 0

    _press(state, engine, tcod.event.KeySym.DOWN)
    assert state.selected == 1

    _press(state, engine, tcod.event.KeySym.UP)
    assert state.selected == 0


# --- ESC pops ---

def test_escape_pops_state():
    engine = make_engine()

    class DummyTactical:
        def on_exit(self, engine):
            pass

    engine._state_stack = [DummyTactical()]
    state = InventoryState()
    engine._state_stack.append(state)

    _press(state, engine, tcod.event.KeySym.ESCAPE)
    assert len(engine._state_stack) == 1
