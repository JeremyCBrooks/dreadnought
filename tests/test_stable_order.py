"""Tests for stable item ordering in inventory and cargo lists.

Items should maintain their insertion order regardless of equip/unequip operations.
New items should always appear at the end of the list.
"""
import tcod.event

from game.entity import Entity, Fighter
from game.loadout import Loadout
from game.ship import Ship
from engine.game_state import Engine
from ui.inventory_state import InventoryState
from ui.cargo_state import CargoState, _PERSONAL, _CARGO
from tests.conftest import make_engine


class FakeEvent:
    def __init__(self, sym):
        self.sym = sym


def _press(state, engine, sym):
    return state.ev_keydown(engine, FakeEvent(sym))


# ---------------------------------------------------------------------------
# InventoryState: stable order
# ---------------------------------------------------------------------------

def test_equip_does_not_change_item_order():
    """Equipping an item should NOT move it in the combined list."""
    engine = make_engine()
    engine.player.loadout = Loadout()
    sword = Entity(name="Sword", item={"type": "weapon", "value": 3})
    medkit = Entity(name="Medkit", item={"type": "heal", "value": 5})
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "value": 1})
    engine.player.inventory.extend([sword, medkit, scanner])

    state = InventoryState()
    # Equip the sword (index 0)
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)

    combined = state._combined_items(engine)
    names = [item.name for item, _ in combined]
    assert names == ["Sword", "Medkit", "Scanner"]
    # Sword is equipped, others are not
    assert combined[0] == (sword, True)
    assert combined[1] == (medkit, False)
    assert combined[2] == (scanner, False)


def test_unequip_does_not_change_item_order():
    """Unequipping an item should NOT move it in the combined list."""
    engine = make_engine()
    sword = Entity(name="Sword", item={"type": "weapon", "value": 3})
    medkit = Entity(name="Medkit", item={"type": "heal", "value": 5})
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "value": 1})
    engine.player.loadout = Loadout(slot1=sword, slot2=scanner)
    engine.player.inventory.extend([sword, medkit, scanner])

    state = InventoryState()
    # Unequip the sword (index 0)
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)

    combined = state._combined_items(engine)
    names = [item.name for item, _ in combined]
    assert names == ["Sword", "Medkit", "Scanner"]
    assert combined[0] == (sword, False)   # now unequipped
    assert combined[1] == (medkit, False)
    assert combined[2] == (scanner, True)  # still equipped


def test_equip_unequip_cycle_preserves_order():
    """Multiple equip/unequip cycles should not reorder items."""
    engine = make_engine()
    engine.player.loadout = Loadout()
    a = Entity(name="A", item={"type": "weapon", "value": 1})
    b = Entity(name="B", item={"type": "heal", "value": 5})
    c = Entity(name="C", item={"type": "weapon", "value": 2})
    engine.player.inventory.extend([a, b, c])

    state = InventoryState()

    # Equip A
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)
    # Equip C
    state.selected = 2
    _press(state, engine, tcod.event.KeySym.e)
    # Unequip A
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)
    # Re-equip A
    state.selected = 0
    _press(state, engine, tcod.event.KeySym.e)

    combined = state._combined_items(engine)
    names = [item.name for item, _ in combined]
    assert names == ["A", "B", "C"]


def test_new_pickup_goes_to_end():
    """Newly picked up items should appear at the end of the inventory list."""
    engine = make_engine()
    engine.player.loadout = Loadout()
    a = Entity(name="A", item={"type": "weapon", "value": 1})
    b = Entity(name="B", item={"type": "heal", "value": 5})
    engine.player.inventory.extend([a, b])

    # Simulate picking up a new item
    c = Entity(name="C", item={"type": "weapon", "value": 2})
    engine.player.inventory.append(c)

    state = InventoryState()
    combined = state._combined_items(engine)
    names = [item.name for item, _ in combined]
    assert names == ["A", "B", "C"]


def test_consuming_item_does_not_reorder_others():
    """Using a consumable should remove it without moving other items."""
    engine = make_engine()
    engine.player.fighter.hp = 5
    engine.player.loadout = Loadout()
    a = Entity(name="A", item={"type": "weapon", "value": 1})
    heal = Entity(name="Heal", item={"type": "heal", "value": 5})
    c = Entity(name="C", item={"type": "weapon", "value": 2})
    engine.player.inventory.extend([a, heal, c])

    state = InventoryState()
    state.selected = 1  # the heal
    _press(state, engine, tcod.event.KeySym.e)

    combined = state._combined_items(engine)
    names = [item.name for item, _ in combined]
    assert names == ["A", "C"]


# ---------------------------------------------------------------------------
# CargoState: stable order
# ---------------------------------------------------------------------------

def _make_strategic_engine(inventory_items=None, loadout_slot1=None, loadout_slot2=None, cargo_items=None):
    from game.loadout import Loadout
    engine = Engine()
    engine.ship = Ship()
    engine.mission_loadout = []
    lo = Loadout(slot1=loadout_slot1, slot2=loadout_slot2)
    inv = list(inventory_items or [])
    engine._saved_player = {
        "hp": 10, "max_hp": 10, "defense": 0,
        "power": 1, "base_power": 1,
        "inventory": inv,
        "loadout": lo,
    }
    for item in (cargo_items or []):
        engine.ship.cargo.append(item)
    return engine


def test_cargo_equip_does_not_change_personal_order():
    """Equipping in cargo state should not change personal list order."""
    sword = Entity(name="Sword", item={"type": "weapon", "value": 3})
    medkit = Entity(name="Medkit", item={"type": "heal", "value": 5})
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "value": 1})
    engine = _make_strategic_engine(inventory_items=[sword, medkit, scanner])

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0  # sword
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.e))

    combined = state._combined_personal(engine)
    names = [item.name for item, _ in combined]
    assert names == ["Sword", "Medkit", "Scanner"]
    assert combined[0][1] is True  # equipped


def test_cargo_unequip_does_not_change_personal_order():
    """Unequipping in cargo state should not change personal list order."""
    sword = Entity(name="Sword", item={"type": "weapon", "value": 3})
    medkit = Entity(name="Medkit", item={"type": "heal", "value": 5})
    engine = _make_strategic_engine(
        inventory_items=[sword, medkit], loadout_slot1=sword,
    )

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0  # sword (equipped)
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.e))

    combined = state._combined_personal(engine)
    names = [item.name for item, _ in combined]
    assert names == ["Sword", "Medkit"]
    assert combined[0][1] is False  # unequipped


def test_cargo_transfer_preserves_cargo_order():
    """Transferring one item from cargo should not reorder remaining items."""
    a = Entity(name="A", item={"type": "weapon", "value": 1})
    b = Entity(name="B", item={"type": "weapon", "value": 2})
    c = Entity(name="C", item={"type": "weapon", "value": 3})
    engine = _make_strategic_engine(cargo_items=[a, b, c])

    state = CargoState()
    state._section = _CARGO
    state.selected = 1  # transfer B
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RETURN))

    cargo_names = [item.name for item in engine.ship.cargo]
    assert cargo_names == ["A", "C"]


def test_cargo_transfer_to_personal_goes_to_end():
    """Items transferred from cargo should appear at end of personal list."""
    existing = Entity(name="Existing", item={"type": "heal", "value": 5})
    new_item = Entity(name="New", item={"type": "weapon", "value": 1})
    engine = _make_strategic_engine(inventory_items=[existing], cargo_items=[new_item])

    state = CargoState()
    state._section = _CARGO
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RETURN))

    combined = state._combined_personal(engine)
    names = [item.name for item, _ in combined]
    assert names == ["Existing", "New"]
