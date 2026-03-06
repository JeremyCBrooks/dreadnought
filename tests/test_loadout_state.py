"""Tests for cargo/inventory transfer flows on tactical entry/exit."""
from engine.game_state import Engine
from game.ship import Ship
from game.entity import Entity, Fighter
from game.suit import EVA_SUIT
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


def test_cargo_transfers_to_inventory_on_tactical_entry():
    """Mission loadout should transfer to player inventory when entering tactical."""
    engine = _make_engine_with_ship()
    weapon = Entity(name="Blaster", item={"type": "weapon", "weapon_class": "ranged", "value": 3, "ammo": 5, "max_ammo": 20})
    heal = Entity(name="Med-kit", item={"type": "heal", "value": 5})
    import tcod.event
    state = BriefingState(location=FakeLocation(), depth=0)
    engine.push_state(state)
    # Set mission_loadout after push (on_enter clears it)
    engine.mission_loadout = [weapon, heal]
    state.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RETURN))

    # Player should have items and auto-equipped weapon
    assert engine.player is not None
    # Weapon should be auto-equipped in loadout
    assert engine.player.loadout is not None
    assert engine.player.loadout.slot1 is weapon
    # Heal should be in inventory (consumables stay in inventory)
    assert heal in engine.player.inventory
    # Mission loadout should be cleared
    assert engine.mission_loadout == []


def test_items_stay_with_player_on_exit():
    """Player loadout + inventory should stay with player on tactical exit, NOT go to cargo."""
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

    # Nothing should go to cargo
    assert len(engine.ship.cargo) == 0
    # Items preserved in saved_player
    sp = engine._saved_player
    inv_names = [e.name for e in sp["inventory"]]
    assert "Med-kit" in inv_names
    assert "Pipe" in inv_names
    loadout_names = [e.name for e in sp["loadout"].all_items()]
    assert "Blaster" in loadout_names
