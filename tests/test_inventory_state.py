"""Tests for the InventoryState (two-section: LOADOUT + COLLECTION TANK)."""
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


# --- Loadout section ---

def test_loadout_section_shows_slots():
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "value": 1})
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.loadout = Loadout(weapon=weapon, tool=scanner, consumable1=heal)

    state = InventoryState()
    slots = state._loadout_slots(engine)
    assert len(slots) == 4
    assert slots[0] == ("WPN", weapon, False)
    assert slots[1] == ("TOOL", scanner, False)
    assert slots[2] == ("C1", heal, True)
    assert slots[3] == ("C2", None, True)


def test_heal_via_loadout():
    engine = make_engine()
    engine.player.fighter.hp = 3
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.loadout = Loadout(consumable1=heal)

    state = InventoryState()
    state.selected = 2  # C1 slot
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert engine.player.fighter.hp == 8
    assert engine.player.loadout.consumable1 is None


def test_heal_caps_at_max():
    engine = make_engine()
    engine.player.fighter.hp = 8
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.loadout = Loadout(consumable1=heal)

    state = InventoryState()
    state.selected = 2  # C1 slot
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert engine.player.fighter.hp == 10


def test_repair_via_loadout():
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 2, "max_durability": 5})
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.loadout = Loadout(weapon=weapon, consumable1=repair)

    state = InventoryState()
    state.selected = 2  # C1 slot (repair)
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert weapon.item["durability"] == 5
    assert engine.player.loadout.consumable1 is None


def test_repair_not_consumed_when_nothing_to_repair():
    engine = make_engine()
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.loadout = Loadout(consumable1=repair)

    state = InventoryState()
    state.selected = 2
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert engine.player.loadout.consumable1 is repair
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("No damaged items" in m for m in msgs)


def test_o2_via_loadout():
    engine = make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    engine.suit.current_pools["vacuum"] = 20
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.loadout = Loadout(consumable1=o2)

    state = InventoryState()
    state.selected = 2
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert engine.suit.current_pools["vacuum"] == 40
    assert engine.player.loadout.consumable1 is None


def test_o2_not_consumed_when_no_suit():
    engine = make_engine()
    engine.suit = None
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.loadout = Loadout(consumable1=o2)

    state = InventoryState()
    state.selected = 2
    _press(state, engine, tcod.event.KeySym.RETURN)

    assert engine.player.loadout.consumable1 is o2
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("No suit O2" in m for m in msgs)


def test_weapon_not_usable():
    """Weapon slot should not be usable (info-only)."""
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    engine.player.loadout = Loadout(weapon=weapon)

    state = InventoryState()
    state.selected = 0  # WPN slot
    _press(state, engine, tcod.event.KeySym.RETURN)

    # No message, weapon stays
    assert engine.player.loadout.weapon is weapon


# --- Navigation ---

def test_navigation_up_down():
    engine = make_engine()
    engine.player.loadout = Loadout(
        weapon=Entity(name="W", item={"type": "weapon", "value": 1}),
        tool=Entity(name="T", item={"type": "scanner", "scanner_tier": 1, "value": 1}),
        consumable1=Entity(name="C1", item={"type": "heal", "value": 5}),
    )

    state = InventoryState()
    assert state.selected == 0

    _press(state, engine, tcod.event.KeySym.DOWN)
    assert state.selected == 1

    _press(state, engine, tcod.event.KeySym.DOWN)
    assert state.selected == 2

    _press(state, engine, tcod.event.KeySym.DOWN)
    assert state.selected == 3

    # Can't go past 4 slots
    _press(state, engine, tcod.event.KeySym.DOWN)
    assert state.selected == 3

    _press(state, engine, tcod.event.KeySym.UP)
    assert state.selected == 2


# --- Tab switching ---

def test_tab_switches_section():
    engine = make_engine()
    engine.player.loadout = Loadout()

    state = InventoryState()
    assert state._section == 0

    _press(state, engine, tcod.event.KeySym.TAB)
    assert state._section == 1
    assert state.selected == 0

    _press(state, engine, tcod.event.KeySym.TAB)
    assert state._section == 0


# --- Collection tank ---

def test_collection_tank_view_only():
    """Items in collection tank should be view-only (no use via ENTER)."""
    engine = make_engine()
    engine.player.loadout = Loadout()
    item = Entity(name="Pipe", item={"type": "weapon", "value": 2})
    engine.player.collection_tank.append(item)

    state = InventoryState()
    _press(state, engine, tcod.event.KeySym.TAB)  # switch to collection
    _press(state, engine, tcod.event.KeySym.RETURN)  # should do nothing

    assert engine.player.collection_tank[0] is item


def test_collection_tank_navigation():
    engine = make_engine()
    engine.player.loadout = Loadout()
    engine.player.collection_tank.extend([
        Entity(name="A", item={"type": "weapon", "value": 1}),
        Entity(name="B", item={"type": "heal", "value": 5}),
    ])

    state = InventoryState()
    _press(state, engine, tcod.event.KeySym.TAB)  # switch to collection
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
