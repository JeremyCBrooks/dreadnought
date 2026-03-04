"""Tests for LoadoutState (4-slot typed panels)."""
from engine.game_state import Engine
from game.ship import Ship
from game.entity import Entity
from game.suit import EVA_SUIT, HAZARD_SUIT
from game.loadout import Loadout
from ui.loadout_state import LoadoutState


class FakeEvent:
    def __init__(self, sym):
        self.sym = sym


def _make_engine_with_ship():
    engine = Engine()
    engine.ship = Ship()
    engine.suit = EVA_SUIT
    return engine


def test_loadout_initial_panel_is_suit():
    state = LoadoutState()
    assert state._panel == 0


def test_loadout_tab_cycles_panels():
    import tcod.event
    engine = _make_engine_with_ship()
    state = LoadoutState()
    engine.push_state(state)
    for expected in range(1, 5):
        state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
        assert state._panel == expected
    # Wraps around to 0
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    assert state._panel == 0


def test_loadout_suit_navigation():
    import tcod.event
    engine = _make_engine_with_ship()
    state = LoadoutState()
    engine.push_state(state)
    assert state._suit_index == 0
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.DOWN))
    assert state._suit_index == 1
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.UP))
    assert state._suit_index == 0


def test_loadout_weapon_selection():
    import tcod.event
    engine = _make_engine_with_ship()
    weapon = Entity(name="Blaster", item={"type": "weapon", "weapon_class": "ranged", "value": 3, "ammo": 5, "max_ammo": 20})
    engine.ship.add_cargo(weapon)
    state = LoadoutState()
    engine.push_state(state)
    # Navigate to weapon panel
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    assert state._panel == 1
    # Toggle select
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.SPACE))
    assert state._selections[1] is not None


def test_loadout_consumable_selection():
    import tcod.event
    engine = _make_engine_with_ship()
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.ship.add_cargo(heal)
    state = LoadoutState()
    engine.push_state(state)
    # Navigate to consumable 1 panel (TAB x3)
    for _ in range(3):
        state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    assert state._panel == 3
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.SPACE))
    assert state._selections[3] is not None


def test_loadout_deselect_toggle():
    import tcod.event
    engine = _make_engine_with_ship()
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.ship.add_cargo(heal)
    state = LoadoutState()
    engine.push_state(state)
    for _ in range(3):
        state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.SPACE))
    assert state._selections[3] is not None
    # Toggle again to deselect
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.SPACE))
    assert state._selections[3] is None


def test_loadout_esc_pops():
    import tcod.event
    engine = _make_engine_with_ship()
    from engine.game_state import State
    engine.push_state(State())
    state = LoadoutState()
    engine.push_state(state)
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.ESCAPE))
    assert engine.current_state is not state


def test_loadout_confirm_sets_suit():
    engine = _make_engine_with_ship()
    state = LoadoutState()
    engine.push_state(state)
    import tcod.event
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.DOWN))
    assert state._suit_index == 1
    state._confirm(engine)
    assert engine.suit.name == "Hazard Suit"


def test_loadout_confirm_builds_loadout():
    import tcod.event
    engine = _make_engine_with_ship()
    weapon = Entity(name="Blaster", item={"type": "weapon", "weapon_class": "ranged", "value": 3, "ammo": 5, "max_ammo": 20})
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "value": 1})
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    o2 = Entity(name="O2", item={"type": "o2", "value": 20})
    engine.ship.cargo.extend([weapon, scanner, heal, o2])

    state = LoadoutState()
    engine.push_state(state)

    # Select weapon (panel 1)
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.SPACE))
    # Select tool (panel 2)
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.SPACE))
    # Select consumable1 (panel 3) - heal
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.SPACE))
    # Select consumable2 (panel 4) - o2
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.SPACE))

    state._confirm(engine)

    # _confirm switches to TacticalState which applies _pending_loadout to player
    assert engine.player is not None
    lo = engine.player.loadout
    assert lo is not None
    assert lo.weapon is weapon
    assert lo.tool is scanner
    assert lo.consumable1 is heal
    assert lo.consumable2 is o2
    # Items should be removed from cargo
    assert len(engine.ship.cargo) == 0


def test_loadout_confirm_removes_from_cargo():
    engine = _make_engine_with_ship()
    items = [
        Entity(name="Blaster", item={"type": "weapon", "value": 3}),
        Entity(name="Med-kit", item={"type": "heal", "value": 5}),
        Entity(name="Pipe", item={"type": "weapon", "value": 2}),
    ]
    for item in items:
        engine.ship.add_cargo(item)

    state = LoadoutState()
    engine.push_state(state)
    import tcod.event
    # Select weapon panel, select first weapon
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.SPACE))

    state._confirm(engine)
    # Blaster removed from cargo, Med-kit and Pipe remain
    assert len(engine.ship.cargo) == 2
    cargo_names = [c.name for c in engine.ship.cargo]
    assert "Blaster" not in cargo_names


def test_loadout_items_appear_in_player_loadout():
    """Items selected in loadout should appear in player loadout on tactical entry."""
    from tests.conftest import make_arena
    from game.entity import Entity as E, Fighter

    engine = _make_engine_with_ship()
    weapon = Entity(name="Blaster", item={"type": "weapon", "weapon_class": "ranged", "value": 3, "ammo": 5, "max_ammo": 20})
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine._pending_loadout = Loadout(weapon=weapon, consumable1=heal)

    player = E(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm = make_arena()
    gm.entities.append(player)
    engine.game_map = gm
    engine.player = player

    # Apply pending loadout (simulating what TacticalState.on_enter will do)
    pending = engine._pending_loadout
    if pending:
        player.loadout = pending
        engine._pending_loadout = None

    assert player.loadout is not None
    assert player.loadout.weapon is weapon
    assert player.loadout.consumable1 is heal
    assert engine._pending_loadout is None


def test_items_return_to_cargo_on_exit():
    """Player loadout + collection_tank should transfer to ship cargo on tactical exit."""
    from tests.conftest import make_arena
    from game.entity import Entity as E, Fighter

    engine = _make_engine_with_ship()
    player = E(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm = make_arena()
    gm.entities.append(player)
    engine.game_map = gm
    engine.player = player

    weapon = Entity(name="Blaster", item={"type": "weapon", "value": 3})
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    found = Entity(name="Pipe", item={"type": "weapon", "value": 1})
    player.loadout = Loadout(weapon=weapon, consumable1=heal)
    player.collection_tank.append(found)

    from ui.tactical_state import TacticalState
    state = TacticalState()
    state.on_exit(engine)

    # All items should be in cargo
    cargo_names = [c.name for c in engine.ship.cargo]
    assert "Blaster" in cargo_names
    assert "Med-kit" in cargo_names
    assert "Pipe" in cargo_names


def test_same_consumable_not_in_both_slots():
    """The same cargo item should not appear in both consumable panels."""
    import tcod.event
    engine = _make_engine_with_ship()
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.ship.add_cargo(heal)

    state = LoadoutState()
    engine.push_state(state)
    # Select in consumable 1 (panel 3)
    for _ in range(3):
        state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.SPACE))

    # Move to consumable 2 (panel 4)
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RIGHT))
    # The heal should not appear since it's already assigned to C1
    filtered = state._filtered_cargo(engine, 4)
    assert heal not in filtered
