"""Tests for InventoryState (single combined list with equipped status)."""

import tcod.event

from game.entity import Entity
from game.loadout import Loadout
from game.suit import Suit
from tests.conftest import FakeEvent, make_engine
from ui.inventory_state import InventoryState


def _press(state, engine, sym):
    return state.ev_key(engine, FakeEvent(sym))


# --- Combined list ---


def test_combined_list_shows_equipped_tags():
    """Equipped items shown with is_equipped=True in stable insertion order."""
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    medkit = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.loadout = Loadout(slot1=weapon)
    engine.player.inventory.extend([weapon, medkit])

    state = InventoryState()
    combined = state._combined_items(engine)
    assert len(combined) == 2
    assert combined[0] == (weapon, True)
    assert combined[1] == (medkit, False)


def test_combined_list_empty():
    engine = make_engine()
    engine.player.loadout = Loadout()
    state = InventoryState()
    assert state._combined_items(engine) == []


# --- Equip / Unequip via ENTER ---


def test_unequip_via_enter():
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    engine.player.loadout = Loadout(slot1=weapon)
    engine.player.inventory.append(weapon)

    state = InventoryState()
    state.selected = 0  # equipped weapon
    _press(state, engine, tcod.event.KeySym.e)

    assert engine.player.loadout.slot1 is None
    assert weapon in engine.player.inventory  # stays in inventory


def test_equip_via_enter():
    engine = make_engine()
    engine.player.loadout = Loadout()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    engine.player.inventory.append(weapon)

    state = InventoryState()
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)

    assert engine.player.loadout.slot1 is weapon
    assert weapon in engine.player.inventory  # stays in inventory


def test_equip_shows_equipped_tag():
    """After equipping, combined list should show the item as equipped in place."""
    engine = make_engine()
    engine.player.loadout = Loadout()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    engine.player.inventory.append(weapon)

    state = InventoryState()
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)

    combined = state._combined_items(engine)
    assert len(combined) == 1
    assert combined[0] == (weapon, True)


# --- Consumables via ENTER ---


def test_use_consumable_from_inventory():
    engine = make_engine()
    engine.player.fighter.hp = 3
    engine.player.loadout = Loadout()
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(heal)

    state = InventoryState()
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)

    assert engine.player.fighter.hp == 8
    assert heal not in engine.player.inventory


def test_heal_caps_at_max():
    engine = make_engine()
    engine.player.fighter.hp = 8
    engine.player.loadout = Loadout()
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(heal)

    state = InventoryState()
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)

    assert engine.player.fighter.hp == 10


def test_repair_via_inventory():
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 2, "max_durability": 5})
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.loadout = Loadout(slot1=weapon)
    engine.player.inventory.extend([weapon, repair])

    state = InventoryState()
    # repair is at index 1 (weapon equipped at 0)
    state.selected = 1
    _press(state, engine, tcod.event.KeySym.e)

    assert weapon.item["durability"] == 5
    assert repair not in engine.player.inventory


def test_repair_not_consumed_when_nothing_to_repair():
    engine = make_engine()
    engine.player.loadout = Loadout()
    repair = Entity(name="Repair Kit", item={"type": "repair", "value": 3})
    engine.player.inventory.append(repair)

    state = InventoryState()
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)

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
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)

    assert engine.suit.current_pools["vacuum"] == 40
    assert o2 not in engine.player.inventory


def test_o2_not_consumed_when_no_suit():
    engine = make_engine()
    engine.suit = None
    engine.player.loadout = Loadout()
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.player.inventory.append(o2)

    state = InventoryState()
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)

    assert o2 in engine.player.inventory
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("No suit O2" in m for m in msgs)


def test_equip_when_full():
    """Equipping when both slots full should show message."""
    engine = make_engine()
    w1 = Entity(name="Baton", item={"type": "weapon", "value": 3})
    w2 = Entity(name="Pipe", item={"type": "weapon", "value": 2})
    w3 = Entity(name="Rifle", item={"type": "weapon", "weapon_class": "ranged", "value": 5, "ammo": 5, "max_ammo": 20})
    engine.player.loadout = Loadout(slot1=w1, slot2=w2)
    engine.player.inventory.extend([w1, w2, w3])

    state = InventoryState()
    # w1=0(eq), w2=1(eq), w3=2(inv)
    state.selected = 2
    _press(state, engine, tcod.event.KeySym.e)

    assert w3 in engine.player.inventory
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("full" in m.lower() for m in msgs)


# --- Navigation ---


def test_navigation_up_down():
    engine = make_engine()
    weapon = Entity(name="W", item={"type": "weapon", "value": 1})
    scanner = Entity(name="T", item={"type": "scanner", "scanner_tier": 1, "value": 1})
    medkit = Entity(name="M", item={"type": "heal", "value": 5})
    engine.player.loadout = Loadout(slot1=weapon, slot2=scanner)
    engine.player.inventory.extend([weapon, scanner, medkit])

    state = InventoryState()
    assert state.selected == 0

    _press(state, engine, tcod.event.KeySym.DOWN)
    assert state.selected == 1

    _press(state, engine, tcod.event.KeySym.DOWN)
    assert state.selected == 2

    # Can't go past end
    _press(state, engine, tcod.event.KeySym.DOWN)
    assert state.selected == 2

    _press(state, engine, tcod.event.KeySym.UP)
    assert state.selected == 1


def test_selected_clamps_after_unequip():
    """After unequipping, selected should remain valid."""
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    engine.player.loadout = Loadout(slot1=weapon)
    engine.player.inventory.append(weapon)

    state = InventoryState()
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)  # unequip

    # Weapon stays in inventory at index 0, selected should be valid
    combined = state._combined_items(engine)
    assert state.selected < len(combined)


# --- Drop ---


def test_drop_in_tactical():
    """Pressing 'd' in tactical mode drops the selected item onto the map."""
    from ui.tactical_state import TacticalState

    engine = make_engine()
    engine.player.loadout = Loadout()
    item = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(item)

    # Simulate tactical state on the stack
    tac = TacticalState.__new__(TacticalState)
    engine._state_stack = [tac]
    state = InventoryState()
    engine._state_stack.append(state)

    state.selected = 0
    _press(state, engine, tcod.event.KeySym.d)

    assert item not in engine.player.inventory
    assert item.x == engine.player.x
    assert item.y == engine.player.y


def test_drop_blocked_outside_tactical():
    """Drop should do nothing when not in tactical mode."""
    engine = make_engine()
    engine.player.loadout = Loadout()
    item = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(item)

    # No tactical state on the stack
    engine._state_stack = []
    state = InventoryState()

    state.selected = 0
    _press(state, engine, tcod.event.KeySym.d)

    assert item in engine.player.inventory


def test_drop_equipped_item_unequips():
    """Dropping an equipped item should also unequip it."""
    from ui.tactical_state import TacticalState

    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 3})
    engine.player.loadout = Loadout(slot1=weapon)
    engine.player.inventory.append(weapon)

    tac = TacticalState.__new__(TacticalState)
    engine._state_stack = [tac]
    state = InventoryState()
    engine._state_stack.append(state)

    state.selected = 0
    _press(state, engine, tcod.event.KeySym.d)

    assert weapon not in engine.player.inventory
    assert engine.player.loadout.slot1 is None


def test_drop_clamps_selected():
    """After dropping the last item, selected should clamp to 0."""
    from ui.tactical_state import TacticalState

    engine = make_engine()
    engine.player.loadout = Loadout()
    item = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.player.inventory.append(item)

    tac = TacticalState.__new__(TacticalState)
    engine._state_stack = [tac]
    state = InventoryState()
    engine._state_stack.append(state)

    state.selected = 0
    _press(state, engine, tcod.event.KeySym.d)

    assert state.selected == 0


def test_unhandled_keys_swallowed():
    """Inventory is modal: unhandled keys return True (don't leak to states below)."""
    engine = make_engine()
    engine.player.loadout = Loadout()
    state = InventoryState()
    assert _press(state, engine, tcod.event.KeySym.z) is True


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
