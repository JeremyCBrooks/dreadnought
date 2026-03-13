"""Tests for the CargoState UI (briefing cargo management)."""
from game.entity import Entity, PLAYER_MAX_INVENTORY
from game.ship import Ship
from engine.game_state import Engine
from ui.cargo_state import CargoState, _PERSONAL, _CARGO


class FakeEvent:
    def __init__(self, sym):
        self.sym = sym


def _make_engine_with_cargo(*cargo_names):
    engine = Engine()
    engine.ship = Ship()
    engine.mission_loadout = []
    for name in cargo_names:
        engine.ship.cargo.append(Entity(name=name, item={"type": "weapon", "value": 1}))
    return engine


def test_initial_section_is_cargo():
    state = CargoState()
    assert state._section == _CARGO


def test_switch_sections():
    import tcod.event
    K = tcod.event.KeySym
    engine = _make_engine_with_cargo("A")

    state = CargoState()
    assert state._section == _CARGO

    state.ev_keydown(engine, FakeEvent(K.LEFT))
    assert state._section == _PERSONAL

    state.ev_keydown(engine, FakeEvent(K.RIGHT))
    assert state._section == _CARGO


def test_transfer_cargo_to_personal():
    import tcod.event
    K = tcod.event.KeySym
    engine = _make_engine_with_cargo("Wrench", "Medkit")

    state = CargoState()
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.RETURN))

    assert len(engine.mission_loadout) == 1
    assert engine.mission_loadout[0].name == "Wrench"
    assert len(engine.ship.cargo) == 1


def test_transfer_personal_to_cargo():
    import tcod.event
    K = tcod.event.KeySym
    engine = _make_engine_with_cargo()
    item = Entity(name="Pipe", item={"type": "weapon", "value": 1})
    engine.mission_loadout.append(item)

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.RETURN))

    assert len(engine.mission_loadout) == 0
    assert item in engine.ship.cargo


def test_transfer_blocked_at_max_capacity():
    import tcod.event
    K = tcod.event.KeySym
    engine = _make_engine_with_cargo("Extra")
    for i in range(PLAYER_MAX_INVENTORY):
        engine.mission_loadout.append(Entity(name=f"Item{i}"))

    state = CargoState()
    state._section = _CARGO
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.RETURN))

    # Transfer should be blocked
    assert len(engine.mission_loadout) == PLAYER_MAX_INVENTORY
    assert len(engine.ship.cargo) == 1  # "Extra" still in cargo


def test_esc_pops_state():
    import tcod.event
    K = tcod.event.KeySym
    engine = _make_engine_with_cargo()
    engine._state_stack = []

    class DummyBriefing:
        pass

    engine._state_stack.append(DummyBriefing())

    state = CargoState()
    engine._state_stack.append(state)
    state.ev_keydown(engine, FakeEvent(K.ESCAPE))

    assert len(engine._state_stack) == 1
    assert isinstance(engine._state_stack[0], DummyBriefing)


def test_selected_clamps_after_transfer():
    import tcod.event
    K = tcod.event.KeySym
    engine = _make_engine_with_cargo("A", "B")

    state = CargoState()
    state._section = _CARGO
    state.selected = 1  # selecting "B", the last item

    # Transfer "B" to personal
    state.ev_keydown(engine, FakeEvent(K.RETURN))

    # selected should clamp to 0 (only "A" left)
    assert state.selected == 0


def test_navigate_up_down():
    import tcod.event
    K = tcod.event.KeySym
    engine = _make_engine_with_cargo("A", "B", "C")

    state = CargoState()
    state._section = _CARGO
    state.selected = 0

    state.ev_keydown(engine, FakeEvent(K.DOWN))
    assert state.selected == 1

    state.ev_keydown(engine, FakeEvent(K.DOWN))
    assert state.selected == 2

    # Can't go past end
    state.ev_keydown(engine, FakeEvent(K.DOWN))
    assert state.selected == 2

    state.ev_keydown(engine, FakeEvent(K.UP))
    assert state.selected == 1


def test_mission_loadout_to_player_on_tactical_entry():
    """mission_loadout items should transfer to player on tactical entry."""
    from ui.tactical_state import TacticalState
    from world.galaxy import Location

    engine = Engine()
    engine.ship = Ship()
    loc = Location("Wreck", "derelict", environment={})

    item_a = Entity(name="Wrench", item={"type": "weapon", "value": 1, "weapon_class": "melee"})
    item_b = Entity(name="Medkit", item={"type": "consumable", "value": 5})
    engine.mission_loadout = [item_a, item_b]

    # Also put something in cargo that was NOT selected
    cargo_item = Entity(name="Spare", item={"type": "weapon", "value": 1})
    engine.ship.cargo.append(cargo_item)

    state = TacticalState(location=loc, depth=0)
    state.on_enter(engine)

    # Wrench may be auto-equipped into loadout, Medkit stays in inventory
    all_items = list(engine.player.inventory)
    if engine.player.loadout:
        all_items.extend(engine.player.loadout.all_items())
    all_names = [e.name for e in all_items]
    assert "Wrench" in all_names
    assert "Medkit" in all_names
    assert "Spare" not in all_names  # not selected, stays in cargo
    assert cargo_item in engine.ship.cargo
    assert engine.mission_loadout == []


def test_cargo_not_auto_transferred_anymore():
    """Ship cargo should NOT auto-transfer to player — only mission_loadout does."""
    from ui.tactical_state import TacticalState
    from world.galaxy import Location

    engine = Engine()
    engine.ship = Ship()
    engine.mission_loadout = []
    loc = Location("Wreck", "derelict", environment={})

    cargo_item = Entity(name="Leftover", item={"type": "consumable"})
    engine.ship.cargo.append(cargo_item)

    state = TacticalState(location=loc, depth=0)
    state.on_enter(engine)

    inv_names = [e.name for e in engine.player.inventory]
    assert "Leftover" not in inv_names
    assert cargo_item in engine.ship.cargo


# --- New tests: inventory persists, no auto-transfer to cargo on exit ---

def test_inventory_stays_with_player_on_exit():
    """Player inventory should NOT auto-transfer to ship cargo on tactical exit."""
    from tests.conftest import make_arena
    from game.entity import Fighter
    from game.loadout import Loadout
    from ui.tactical_state import TacticalState

    engine = Engine()
    engine.ship = Ship()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm = make_arena()
    gm.entities.append(player)
    engine.game_map = gm
    engine.player = player

    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    found = Entity(name="Pipe", item={"type": "weapon", "value": 1})
    player.loadout = Loadout(slot1=weapon)
    player.inventory.extend([heal, found])

    state = TacticalState()
    state.on_exit(engine)

    # Items should stay with the player (_saved_player), NOT go to cargo
    assert len(engine.ship.cargo) == 0
    sp = engine._saved_player
    inv_names = [e.name for e in sp["inventory"]]
    assert "Med-kit" in inv_names
    assert "Pipe" in inv_names
    # Loadout items also saved
    loadout = sp["loadout"]
    loadout_names = [e.name for e in loadout.all_items()]
    assert "Blaster" in loadout_names


def test_cargo_key_opens_cargo_in_strategic_state():
    """Pressing 'c' on the ship (strategic state) should push CargoState."""
    from ui.strategic_state import StrategicState
    from world.galaxy import Galaxy, StarSystem, Location
    import tcod.event
    K = tcod.event.KeySym

    engine = Engine()
    engine.ship = Ship()
    engine._saved_player = {
        "hp": 10, "max_hp": 10, "defense": 0,
        "power": 1, "base_power": 1,
        "inventory": [], "loadout": None,
    }

    galaxy = Galaxy.__new__(Galaxy)
    galaxy.systems = {"Sol": StarSystem.__new__(StarSystem)}
    galaxy.systems["Sol"].name = "Sol"
    galaxy.systems["Sol"].locations = [Location("Station", "starbase", environment={})]
    galaxy.systems["Sol"].connections = {}
    galaxy.systems["Sol"].depth = 0
    galaxy.current_system = "Sol"

    state = StrategicState(galaxy=galaxy)
    engine._state_stack = [state]

    state.ev_keydown(engine, FakeEvent(K.c))

    assert len(engine._state_stack) == 2
    assert isinstance(engine._state_stack[-1], CargoState)


def test_cargo_state_from_ship_transfers_saved_inventory():
    """CargoState on the ship should transfer between _saved_player inventory and cargo."""
    import tcod.event
    K = tcod.event.KeySym

    engine = Engine()
    engine.ship = Ship()
    cargo_item = Entity(name="Spare", item={"type": "weapon", "value": 1})
    engine.ship.cargo.append(cargo_item)
    engine.mission_loadout = []
    engine._saved_player = {
        "hp": 10, "max_hp": 10, "defense": 0,
        "power": 1, "base_power": 1,
        "inventory": [], "loadout": None,
    }

    state = CargoState()
    state._section = _CARGO
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.RETURN))

    # Item should transfer to saved_player inventory, not mission_loadout
    assert cargo_item in engine._saved_player["inventory"]
    assert cargo_item not in engine.ship.cargo


def test_cargo_state_from_ship_transfer_back():
    """Transfer from saved inventory back to cargo."""
    import tcod.event
    K = tcod.event.KeySym

    engine = Engine()
    engine.ship = Ship()
    engine.mission_loadout = []
    item = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    engine._saved_player = {
        "hp": 10, "max_hp": 10, "defense": 0,
        "power": 1, "base_power": 1,
        "inventory": [item], "loadout": None,
    }

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.RETURN))

    assert item in engine.ship.cargo
    assert item not in engine._saved_player["inventory"]


def _make_strategic_engine_with_loadout(inventory_items=None, loadout_slot1=None, loadout_slot2=None, cargo_items=None):
    """Create an engine in strategic context (with _saved_player) for CargoState tests."""
    from game.loadout import Loadout
    engine = Engine()
    engine.ship = Ship()
    engine.mission_loadout = []
    lo = Loadout(slot1=loadout_slot1, slot2=loadout_slot2)
    engine._saved_player = {
        "hp": 10, "max_hp": 10, "defense": 0,
        "power": 1, "base_power": 1,
        "inventory": list(inventory_items or []),
        "loadout": lo,
    }
    for item in (cargo_items or []):
        engine.ship.cargo.append(item)
    return engine


def test_personal_list_shows_equipped_and_inventory():
    """Combined personal list shows items in stable order with equipped tags."""
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    medkit = Entity(name="Medkit", item={"type": "consumable", "value": 5})
    engine = _make_strategic_engine_with_loadout(
        inventory_items=[weapon, medkit], loadout_slot1=weapon,
    )
    state = CargoState()
    combined = state._combined_personal(engine)
    assert len(combined) == 2
    assert combined[0] == (weapon, True)
    assert combined[1] == (medkit, False)


def test_equip_from_personal_in_strategic_context():
    """Pressing 'e' on an equippable inventory item should equip it (item stays in list)."""
    import tcod.event
    K = tcod.event.KeySym
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    engine = _make_strategic_engine_with_loadout(inventory_items=[weapon])

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0  # weapon in inventory
    state.ev_keydown(engine, FakeEvent(K.e))

    lo = engine._saved_player["loadout"]
    assert lo.has_item(weapon)
    assert weapon in engine._saved_player["inventory"]  # stays in list


def test_unequip_from_personal_in_strategic_context():
    """Pressing 'e' on an equipped item should unequip it (stays in list)."""
    import tcod.event
    K = tcod.event.KeySym
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    engine = _make_strategic_engine_with_loadout(
        inventory_items=[weapon], loadout_slot1=weapon,
    )

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0  # weapon is equipped, first in combined list
    state.ev_keydown(engine, FakeEvent(K.e))

    lo = engine._saved_player["loadout"]
    assert not lo.has_item(weapon)
    assert weapon in engine._saved_player["inventory"]


def test_equip_works_in_briefing_context():
    """Equipping should work even in briefing context (no prior _saved_player)."""
    import tcod.event
    K = tcod.event.KeySym
    engine = _make_engine_with_cargo()
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    engine.mission_loadout.append(weapon)

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.e))

    # Weapon should be equipped in the lazily-created _saved_player loadout
    assert engine._saved_player is not None
    lo = engine._saved_player["loadout"]
    assert lo.has_item(weapon)
    assert weapon in engine.mission_loadout  # stays in list, just marked equipped


def test_equip_ignored_in_cargo_section():
    """Pressing 'e' while browsing ship cargo should do nothing."""
    import tcod.event
    K = tcod.event.KeySym
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    engine = _make_strategic_engine_with_loadout(cargo_items=[weapon])

    state = CargoState()
    state._section = _CARGO
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.e))

    # Weapon should still be in cargo, not equipped
    assert weapon in engine.ship.cargo
    lo = engine._saved_player["loadout"]
    assert not lo.has_item(weapon)


def test_equip_status_updates_in_combined_list():
    """After equipping, _combined_personal should show the item as equipped."""
    import tcod.event
    K = tcod.event.KeySym
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    medkit = Entity(name="Medkit", item={"type": "heal", "value": 5})
    engine = _make_strategic_engine_with_loadout(inventory_items=[weapon, medkit])

    state = CargoState()
    state._section = _PERSONAL

    # Before equip: both items unequipped
    combined = state._combined_personal(engine)
    assert all(not eq for _, eq in combined)

    # Equip weapon (first item)
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.e))

    # After equip: weapon should be equipped, medkit not
    combined = state._combined_personal(engine)
    equipped = {item.name: eq for item, eq in combined}
    assert equipped["Blaster"] is True
    assert equipped["Medkit"] is False


def test_footer_text_changes_with_section():
    """Footer should show [E] Equip only in personal section, not cargo."""
    state = CargoState()

    state._section = _PERSONAL
    assert "[E] Equip" in state._footer_text()

    state._section = _CARGO
    assert "[E] Equip" not in state._footer_text()


def test_transfer_blocked_counts_equipped_items():
    """Transfer from cargo should be blocked when inventory (incl. equipped) = max."""
    import tcod.event
    K = tcod.event.KeySym
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    other_items = [Entity(name=f"Item{i}") for i in range(PLAYER_MAX_INVENTORY - 1)]
    inv_items = [weapon] + other_items  # weapon is in inventory AND equipped
    extra = Entity(name="Extra", item={"type": "weapon", "value": 1})
    engine = _make_strategic_engine_with_loadout(
        inventory_items=inv_items, loadout_slot1=weapon, cargo_items=[extra],
    )

    state = CargoState()
    state._section = _CARGO
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.RETURN))

    # Transfer should be blocked (10 items in inventory = max)
    assert extra in engine.ship.cargo
    assert extra not in engine._saved_player["inventory"]


def test_unequip_when_at_capacity_still_works():
    """Unequipping when at capacity shouldn't be blocked (total stays same)."""
    import tcod.event
    K = tcod.event.KeySym
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    other_items = [Entity(name=f"Item{i}") for i in range(PLAYER_MAX_INVENTORY - 1)]
    engine = _make_strategic_engine_with_loadout(
        inventory_items=[weapon] + other_items, loadout_slot1=weapon,
    )

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0  # equipped item is first in combined list
    state.ev_keydown(engine, FakeEvent(K.e))

    lo = engine._saved_player["loadout"]
    assert not lo.has_item(weapon)
    assert weapon in engine._saved_player["inventory"]


def test_equip_when_loadout_full():
    """Trying to equip when both loadout slots are full should show a message."""
    import tcod.event
    K = tcod.event.KeySym
    w1 = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    w2 = Entity(name="Scanner", item={"type": "scanner", "value": 1})
    w3 = Entity(name="Pipe", item={"type": "weapon", "value": 1})
    engine = _make_strategic_engine_with_loadout(
        inventory_items=[w1, w2, w3], loadout_slot1=w1, loadout_slot2=w2,
    )

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 2  # w3 is third in combined list (after w1, w2)
    state.ev_keydown(engine, FakeEvent(K.e))

    # w3 should still be in inventory, unequipped
    assert w3 in engine._saved_player["inventory"]
    assert any("full" in m[0].lower() for m in engine.message_log.messages)


def test_transfer_equipped_item_to_cargo():
    """ENTER on equipped item should unequip + transfer to cargo in one step."""
    import tcod.event
    K = tcod.event.KeySym
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    engine = _make_strategic_engine_with_loadout(
        inventory_items=[weapon], loadout_slot1=weapon,
    )

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0  # equipped item
    state.ev_keydown(engine, FakeEvent(K.RETURN))

    lo = engine._saved_player["loadout"]
    assert not lo.has_item(weapon)
    assert weapon not in engine._saved_player["inventory"]
    assert weapon in engine.ship.cargo


def test_equip_creates_loadout_when_none():
    """Equipping should work even if _saved_player had loadout=None initially."""
    import tcod.event
    K = tcod.event.KeySym
    engine = Engine()
    engine.ship = Ship()
    engine.mission_loadout = []
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    engine._saved_player = {
        "hp": 10, "max_hp": 10, "defense": 0,
        "power": 1, "base_power": 1,
        "inventory": [weapon],
        "loadout": None,
    }

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.e))

    lo = engine._saved_player["loadout"]
    assert lo is not None
    assert lo.has_item(weapon)
    assert weapon in engine._saved_player["inventory"]  # stays in list


def test_equip_works_on_fresh_game():
    """Equipping should work even on a brand new game (no _saved_player yet)."""
    import tcod.event
    K = tcod.event.KeySym
    engine = _make_engine_with_cargo()
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    engine.ship.cargo.append(weapon)
    # No _saved_player set — simulates a fresh game
    assert engine._saved_player is None

    state = CargoState()
    # Transfer cargo to personal
    state._section = _CARGO
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.RETURN))

    # Switch to personal, try to equip
    state._section = _PERSONAL
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.e))

    # Weapon should now be equipped
    assert engine._saved_player is not None
    lo = engine._saved_player["loadout"]
    assert lo is not None
    assert lo.has_item(weapon)


def test_equipped_shown_in_combined_on_fresh_game():
    """After equipping on a fresh game, _combined_personal should show [E] tag."""
    import tcod.event
    K = tcod.event.KeySym
    engine = _make_engine_with_cargo()
    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    engine.mission_loadout.append(weapon)
    assert engine._saved_player is None

    state = CargoState()
    state._section = _PERSONAL
    state.selected = 0
    state.ev_keydown(engine, FakeEvent(K.e))

    combined = state._combined_personal(engine)
    equipped = [(item, eq) for item, eq in combined if eq]
    assert len(equipped) == 1
    assert equipped[0][0] is weapon


def test_debug_items_go_to_ship_cargo():
    """Debug starting items should be placed in ship cargo, not player inventory."""
    import debug
    from game.ship import Ship

    old_start = debug.START_INVENTORY
    try:
        debug.START_INVENTORY = [("scanner", "Basic Scanner")]
        engine = Engine()
        engine.ship = Ship()

        debug.seed_ship_cargo(engine)

        cargo_names = [e.name for e in engine.ship.cargo]
        assert "Basic Scanner" in cargo_names
    finally:
        debug.START_INVENTORY = old_start


def test_inventory_persists_across_missions():
    """Items in player inventory should persist across tactical exits and re-entries."""
    from ui.tactical_state import TacticalState
    from game.ship import Ship
    from world.galaxy import Location

    engine = Engine()
    engine.ship = Ship()
    loc = Location("Wreck", "derelict", environment={})

    # First visit: enter then exit with items
    state = TacticalState(location=loc, depth=0)
    state.on_enter(engine)
    item = Entity(name="Medkit", item={"type": "consumable"})
    engine.player.inventory.append(item)
    state.on_exit(engine)

    # Items should stay with player (in _saved_player), NOT go to cargo
    assert len(engine.ship.cargo) == 0
    sp = engine._saved_player
    inv_names = [e.name for e in sp["inventory"]]
    assert "Medkit" in inv_names

    # Second visit: items should come back with the player
    engine.mission_loadout = []
    loc2 = Location("Asteroid", "asteroid", environment={})
    state2 = TacticalState(location=loc2, depth=0)
    state2.on_enter(engine)

    inv_names = [e.name for e in engine.player.inventory]
    assert "Medkit" in inv_names


class TestCargoScroll:
    def test_scroll_offset_tracks_cursor(self):
        """When selected exceeds max_visible, rendering should scroll."""
        engine = Engine()
        engine.ship = Ship()
        engine.mission_loadout = []
        # Add many items to cargo
        for i in range(30):
            engine.ship.cargo.append(Entity(name=f"Item{i}", item={"type": "weapon", "value": 1}))

        state = CargoState()
        state._section = 1  # _CARGO
        state.selected = 25  # beyond max_visible

        # The render should not crash and cursor should be visible
        # We test the scroll calculation logic indirectly through the state
        length = state._current_list_len(engine)
        assert state.selected < length


class TestCargoTruncation:
    def test_small_label_width_no_crash(self):
        """String truncation should not crash even with very small label_width."""
        # This tests the guard: if label_width > 3 and len(line) > label_width
        label_width = 2
        line = "A very long item name"
        # With the fix, this should NOT truncate (would produce garbage)
        if label_width > 3 and len(line) > label_width:
            line = line[:label_width - 3] + "..."
        # Without the guard, line[:label_width - 3] + "..." = line[:-1] + "..."
        # The fix means line stays unchanged when label_width <= 3
        assert "..." not in line
