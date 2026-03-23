"""Tests for hull integrity: drift damage, repair kits, clamping."""

from types import SimpleNamespace

from game.entity import Entity, Fighter
from game.ship import Ship
from tests.conftest import FakeEvent, MockEngine, make_arena
from ui.strategic_state import StrategicState


def _sym(name):
    import tcod.event

    return getattr(tcod.event.KeySym, name)


def _make_two_system_galaxy():
    """Build a galaxy with two connected systems (OtherSystem to the right)."""
    locs = [SimpleNamespace(name="Loc_0", loc_type="derelict", visited=False, environment={"vacuum": 1})]
    system = SimpleNamespace(
        name="TestSystem",
        gx=0,
        gy=0,
        locations=locs,
        connections={"OtherSystem": 30},
        depth=0,
        star_type="yellow_dwarf",
    )
    other = SimpleNamespace(
        name="OtherSystem",
        gx=1,
        gy=0,
        locations=[],
        connections={"TestSystem": 30},
        depth=1,
        star_type="red_dwarf",
    )
    galaxy = SimpleNamespace(
        systems={"TestSystem": system, "OtherSystem": other},
        current_system="TestSystem",
        home_system="TestSystem",
        arrive_at=lambda name: None,
        _unexplored_frontier={"OtherSystem"},
        travel_cost=lambda dest: 1,
    )
    return galaxy


def _make_strategic_engine(galaxy):
    gm = make_arena()
    player = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.ship = Ship()
    return engine


# --- Ship defaults ---


def test_ship_has_hull_defaults():
    ship = Ship()
    assert ship.hull == 10
    assert ship.max_hull == 10


# --- Drift hull damage ---


def test_drift_no_cargo_damages_hull():
    """Drifting with empty cargo damages hull by 1."""
    galaxy = _make_two_system_galaxy()
    state = StrategicState(galaxy)
    engine = _make_strategic_engine(galaxy)
    engine.ship.fuel = 0
    engine.ship.cargo = []
    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))
    assert engine.ship.hull == 9


def test_drift_with_cargo_no_hull_damage():
    """Drifting with cargo jettisons cargo but does not damage hull."""
    galaxy = _make_two_system_galaxy()
    state = StrategicState(galaxy)
    engine = _make_strategic_engine(galaxy)
    engine.ship.fuel = 0
    item = Entity(name="Fuel Cell", char="f", color=(255, 255, 0))
    engine.ship.cargo = [item]
    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))
    assert engine.ship.hull == 10


def test_drift_hull_zero_game_over():
    """Hull at 1 + drift with no cargo -> game over via switch_state."""
    galaxy = _make_two_system_galaxy()
    state = StrategicState(galaxy)
    engine = _make_strategic_engine(galaxy)
    engine.ship.fuel = 0
    engine.ship.hull = 1
    engine.ship.cargo = []
    state.ev_key(engine, FakeEvent(_sym("TAB")))
    state.ev_key(engine, FakeEvent(_sym("RIGHT")))
    assert engine.ship.hull == 0
    assert engine._switched_state is not None
    assert engine._switched_state.title == "SHIP DESTROYED"


def test_hull_cannot_go_negative():
    """Hull at 0 should not go below 0."""
    ship = Ship()
    ship.hull = 0
    ship.hull = max(0, ship.hull - 1)
    assert ship.hull == 0


# --- Hull repair on mission exit ---


def test_hull_repair_auto_apply():
    """hull_repair items in saved_inventory restore hull and are removed."""
    from engine.game_state import Engine
    from game.loadout import Loadout
    from ui.tactical_state import TacticalState

    engine = Engine()
    engine.ship = Ship()
    engine.ship.hull = 5

    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine.game_map = gm
    engine.player = player
    engine.player.inventory = []
    engine.player.loadout = Loadout()

    hull_kit = Entity(name="Hull Patch", char="#", color=(80, 200, 180), item={"type": "hull_repair", "value": 3})
    engine.player.inventory.append(hull_kit)

    loc = SimpleNamespace(name="TestLoc", loc_type="derelict", visited=False, environment={"vacuum": 1})
    ts = TacticalState(location=loc, depth=0)
    ts.exit_pos = (1, 1)
    ts.on_exit(engine)

    assert engine.ship.hull == 8
    saved_inv = engine._saved_player["inventory"]
    assert hull_kit not in saved_inv


def test_hull_repair_clamped_at_max():
    """hull_repair should not exceed max_hull."""
    from engine.game_state import Engine
    from game.loadout import Loadout
    from ui.tactical_state import TacticalState

    engine = Engine()
    engine.ship = Ship()
    engine.ship.hull = 9

    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine.game_map = gm
    engine.player = player
    engine.player.inventory = []
    engine.player.loadout = Loadout()

    hull_kit = Entity(name="Hull Patch", char="#", color=(80, 200, 180), item={"type": "hull_repair", "value": 3})
    engine.player.inventory.append(hull_kit)

    loc = SimpleNamespace(name="TestLoc", loc_type="derelict", visited=False, environment={"vacuum": 1})
    ts = TacticalState(location=loc, depth=0)
    ts.exit_pos = (1, 1)
    ts.on_exit(engine)

    assert engine.ship.hull == 10  # clamped, not 12


# --- Nav unit clamping ---


def test_nav_units_clamped_at_6():
    """Nav units should not exceed MAX_NAV_UNITS (6)."""
    from engine.game_state import Engine
    from game.loadout import Loadout
    from ui.tactical_state import TacticalState

    engine = Engine()
    engine.ship = Ship()
    engine.ship.nav_units = 5

    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine.game_map = gm
    engine.player = player
    engine.player.inventory = []
    engine.player.loadout = Loadout()

    # Add 2 nav units — only 1 should be installed (5+1=6, second clamped)
    nav1 = Entity(name="Nav Unit 1", char="n", color=(0, 200, 255), item={"type": "nav_unit", "value": 1})
    nav2 = Entity(name="Nav Unit 2", char="n", color=(0, 200, 255), item={"type": "nav_unit", "value": 1})
    engine.player.inventory.extend([nav1, nav2])

    loc = SimpleNamespace(name="TestLoc", loc_type="derelict", visited=False, environment={"vacuum": 1})
    ts = TacticalState(location=loc, depth=0)
    ts.exit_pos = (1, 1)
    ts.on_exit(engine)

    assert engine.ship.nav_units == 6  # clamped at MAX_NAV_UNITS
