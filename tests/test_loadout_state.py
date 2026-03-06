"""Tests for suit selection in BriefingState and cargo/inventory transfer flows."""
from engine.game_state import Engine
from game.ship import Ship
from game.entity import Entity, Fighter
from game.suit import EVA_SUIT, HAZARD_SUIT
from game.loadout import Loadout
from ui.briefing_state import BriefingState
from tests.conftest import make_arena


class FakeEvent:
    def __init__(self, sym):
        self.sym = sym


class FakeLocation:
    def __init__(self, name="Test", loc_type="derelict", environment=None):
        self.name = name
        self.loc_type = loc_type
        self.environment = environment or {}


def _make_engine_with_ship():
    engine = Engine()
    engine.ship = Ship()
    engine.suit = EVA_SUIT
    return engine


def test_briefing_suit_selection():
    import tcod.event
    engine = _make_engine_with_ship()
    state = BriefingState(location=FakeLocation(), depth=0)
    engine.push_state(state)
    assert state._suit_index == 0
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.DOWN))
    assert state._suit_index == 1
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.UP))
    assert state._suit_index == 0


def test_briefing_confirm_sets_suit():
    import tcod.event
    engine = _make_engine_with_ship()
    state = BriefingState(location=FakeLocation(), depth=0)
    engine.push_state(state)
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.DOWN))
    assert state._suit_index == 1
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RETURN))
    assert engine.suit.name == "Hazard Suit"


def test_briefing_confirm_transitions_to_tactical():
    import tcod.event
    engine = _make_engine_with_ship()
    state = BriefingState(location=FakeLocation(), depth=0)
    engine.push_state(state)
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RETURN))
    from ui.tactical_state import TacticalState
    assert isinstance(engine.current_state, TacticalState)


def test_briefing_esc_pops():
    import tcod.event
    engine = _make_engine_with_ship()
    from engine.game_state import State
    engine.push_state(State())
    state = BriefingState(location=FakeLocation(), depth=0)
    engine.push_state(state)
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.ESCAPE))
    assert engine.current_state is not state


def test_cargo_transfers_to_inventory_on_tactical_entry():
    """Ship cargo should transfer to player inventory when entering tactical."""
    engine = _make_engine_with_ship()
    weapon = Entity(name="Blaster", item={"type": "weapon", "weapon_class": "ranged", "value": 3, "ammo": 5, "max_ammo": 20})
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    engine.ship.cargo.extend([weapon, heal])

    import tcod.event
    state = BriefingState(location=FakeLocation(), depth=0)
    engine.push_state(state)
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RETURN))

    # Player should have items and auto-equipped weapon
    assert engine.player is not None
    # Weapon should be auto-equipped in loadout
    assert engine.player.loadout is not None
    assert engine.player.loadout.slot1 is weapon
    # Heal should be in inventory (consumables stay in inventory)
    assert heal in engine.player.inventory
    # Ship cargo should be empty
    assert len(engine.ship.cargo) == 0


def test_items_return_to_cargo_on_exit():
    """Player loadout + inventory should transfer to ship cargo on tactical exit."""
    engine = _make_engine_with_ship()
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

    from ui.tactical_state import TacticalState
    state = TacticalState()
    state.on_exit(engine)

    # All items should be in cargo
    cargo_names = [c.name for c in engine.ship.cargo]
    assert "Blaster" in cargo_names
    assert "Med-kit" in cargo_names
    assert "Pipe" in cargo_names
