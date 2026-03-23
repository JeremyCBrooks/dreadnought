"""Tests for Dreadnought spawning, core item, and victory mechanics."""

from collections import deque

from engine.game_state import Engine
from game.entity import Entity, Fighter
from game.ship import Ship
from world.galaxy import DREADNOUGHT_LOCATION_NAME, DREADNOUGHT_SYSTEM_NAME, Galaxy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expand_all(galaxy: Galaxy, max_iter: int = 50) -> None:
    """Expand all frontiers so the galaxy is fully generated."""
    for _ in range(max_iter):
        frontier = list(galaxy._unexplored_frontier)
        if not frontier:
            break
        for name in frontier:
            galaxy.arrive_at(name)


def _bfs_reachable(galaxy: Galaxy, start: str) -> set[str]:
    """Return all system names reachable from *start*."""
    visited: set[str] = set()
    queue = deque([start])
    while queue:
        name = queue.popleft()
        if name in visited:
            continue
        visited.add(name)
        for nb in galaxy.systems[name].connections:
            queue.append(nb)
    return visited


def _make_engine_with_galaxy(seed: int = 42) -> tuple[Engine, Galaxy]:
    engine = Engine()
    galaxy = Galaxy(seed=seed)
    engine.galaxy = galaxy
    engine.ship = Ship()
    return engine, galaxy


# ---------------------------------------------------------------------------
# Galaxy spawn tests
# ---------------------------------------------------------------------------


class TestSpawnDreadnought:
    def test_spawn_creates_system(self):
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        galaxy.spawn_dreadnought()
        assert DREADNOUGHT_SYSTEM_NAME in galaxy.systems

    def test_spawn_single_derelict_location(self):
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        galaxy.spawn_dreadnought()
        sys = galaxy.systems[DREADNOUGHT_SYSTEM_NAME]
        assert len(sys.locations) == 1
        loc = sys.locations[0]
        assert loc.name == DREADNOUGHT_LOCATION_NAME
        assert loc.loc_type == "derelict"

    def test_spawn_beyond_deepest(self):
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        max_depth = max(s.depth for s in galaxy.systems.values())
        galaxy.spawn_dreadnought()
        dread = galaxy.systems[DREADNOUGHT_SYSTEM_NAME]
        assert dread.depth >= max_depth

    def test_spawn_reachable(self):
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        galaxy.spawn_dreadnought()
        reachable = _bfs_reachable(galaxy, galaxy.home_system)
        assert DREADNOUGHT_SYSTEM_NAME in reachable

    def test_spawn_idempotent(self):
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        name1 = galaxy.spawn_dreadnought()
        count_before = len(galaxy.systems)
        name2 = galaxy.spawn_dreadnought()
        assert name1 == name2
        assert len(galaxy.systems) == count_before

    def test_spawn_deterministic(self):
        """Same seed + same exploration = same position."""
        positions = []
        for _ in range(2):
            galaxy = Galaxy(seed=99)
            _expand_all(galaxy)
            galaxy.spawn_dreadnought()
            sys = galaxy.systems[DREADNOUGHT_SYSTEM_NAME]
            positions.append((sys.gx, sys.gy))
        assert positions[0] == positions[1]

    def test_spawn_not_on_existing_position(self):
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        occupied_before = set(galaxy._occupied_positions.keys())
        galaxy.spawn_dreadnought()
        sys = galaxy.systems[DREADNOUGHT_SYSTEM_NAME]
        assert (sys.gx, sys.gy) not in occupied_before

    def test_spawn_connections_bidirectional(self):
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        galaxy.spawn_dreadnought()
        dread = galaxy.systems[DREADNOUGHT_SYSTEM_NAME]
        assert len(dread.connections) >= 1
        for parent_name in dread.connections:
            parent = galaxy.systems[parent_name]
            assert DREADNOUGHT_SYSTEM_NAME in parent.connections

    def test_spawn_is_dead_end(self):
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        galaxy.spawn_dreadnought()
        assert DREADNOUGHT_SYSTEM_NAME in galaxy._generated_frontiers

    def test_spawn_is_frontier(self):
        """Dreadnought system has travel cost 2 (unexplored frontier)."""
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        galaxy.spawn_dreadnought()
        assert galaxy.travel_cost(DREADNOUGHT_SYSTEM_NAME) == 2


# ---------------------------------------------------------------------------
# Core item tests
# ---------------------------------------------------------------------------


class TestDreadnoughtCore:
    def test_extract_core_yields_dreadnought_core(self):
        """Extracting reactor core in Dreadnought location yields dreadnought_core item."""
        from game.actions import TakeReactorCoreAction
        from tests.conftest import make_arena
        from world import tile_types
        from world.galaxy import Location

        engine = Engine()
        engine.ship = Ship()
        gm = make_arena()
        # Place reactor_core tile at (5, 4)
        gm.tiles[5, 4] = tile_types.reactor_core
        gm.light_sources = []
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine.game_map = gm
        engine.player = player

        # Simulate being in a Dreadnought location via TacticalState
        from ui.tactical_state import TacticalState

        loc = Location(DREADNOUGHT_LOCATION_NAME, "derelict", system_name=DREADNOUGHT_SYSTEM_NAME)
        loc.is_dreadnought = True
        ts = TacticalState(location=loc, depth=0)
        engine._state_stack.append(ts)

        action = TakeReactorCoreAction(dx=0, dy=-1)
        action.perform(engine, player)

        assert len(player.inventory) == 1
        assert player.inventory[0].item["type"] == "dreadnought_core"
        assert player.inventory[0].name == "Dreadnought Core"

    def test_extract_core_normal_location_yields_reactor_core(self):
        """Extracting reactor core in normal location yields regular reactor_core."""
        from game.actions import TakeReactorCoreAction
        from tests.conftest import make_arena
        from world import tile_types
        from world.galaxy import Location

        engine = Engine()
        engine.ship = Ship()
        gm = make_arena()
        gm.tiles[5, 4] = tile_types.reactor_core
        gm.light_sources = []
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine.game_map = gm
        engine.player = player

        from ui.tactical_state import TacticalState

        loc = Location("Some Derelict", "derelict", system_name="SomeSys")
        ts = TacticalState(location=loc, depth=0)
        engine._state_stack.append(ts)

        action = TakeReactorCoreAction(dx=0, dy=-1)
        action.perform(engine, player)

        assert len(player.inventory) == 1
        assert player.inventory[0].item["type"] == "reactor_core"
        assert player.inventory[0].name == "Reactor Core"

    def test_dreadnought_core_transfers_to_cargo_on_exit(self):
        """dreadnought_core auto-transfers to ship cargo on tactical exit."""
        from ui.tactical_state import TacticalState
        from world.galaxy import Location

        engine = Engine()
        engine.ship = Ship()
        engine.galaxy = Galaxy(seed=1)

        loc = Location("Test", "derelict", system_name="TestSys")
        ts = TacticalState(location=loc, depth=0)

        # Set up minimal game map and player with dreadnought_core
        from tests.conftest import make_arena

        gm = make_arena()
        core = Entity(
            char="*",
            color=(255, 0, 0),
            name="Dreadnought Core",
            blocks_movement=False,
            item={"type": "dreadnought_core", "value": 99},
        )
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        player.inventory.append(core)
        gm.entities.append(player)
        engine.game_map = gm
        engine.player = player

        ts.on_exit(engine)

        # Core should be in ship cargo, not in saved inventory
        saved_inv = engine._saved_player["inventory"]
        assert not any(i.item and i.item.get("type") == "dreadnought_core" for i in saved_inv)
        cargo_cores = [c for c in engine.ship.cargo if c.item and c.item.get("type") == "dreadnought_core"]
        assert len(cargo_cores) == 1

    def test_jettison_core_game_over(self):
        """Jettisoning dreadnought_core during drift triggers game over."""
        from ui.strategic_state import StrategicState

        engine, galaxy = _make_engine_with_galaxy(seed=42)
        state = StrategicState(galaxy)

        core = Entity(
            char="*",
            color=(255, 0, 0),
            name="Dreadnought Core",
            blocks_movement=False,
            item={"type": "dreadnought_core"},
        )
        engine.ship.cargo.append(core)
        # Force fuel to 0 to trigger drift
        engine.ship.fuel = 0

        # Mock random to make drift jettison the core
        import random

        old_choice = random.choice
        random.choice = lambda seq: core if seq is engine.ship.cargo else old_choice(seq)
        old_choices = random.choices
        # _drift_destination uses random.choices
        neighbors = list(galaxy.systems[galaxy.current_system].connections.keys())
        random.choices = lambda pop, weights, k: [neighbors[0]]

        try:
            state._drift(engine)
        finally:
            random.choice = old_choice
            random.choices = old_choices

        from ui.game_over_state import GameOverState

        assert isinstance(engine._state_stack[-1], GameOverState)
        assert "CORE IS LOST" in engine._state_stack[-1].title

    def test_victory_on_home_with_core(self):
        """Arriving at home system with core in cargo triggers victory."""
        from tests.conftest import FakeEvent
        from ui.strategic_state import StrategicState

        engine, galaxy = _make_engine_with_galaxy(seed=42)
        state = StrategicState(galaxy)
        engine._state_stack.append(state)

        core = Entity(
            char="*",
            color=(255, 0, 0),
            name="Dreadnought Core",
            blocks_movement=False,
            item={"type": "dreadnought_core"},
        )
        engine.ship.cargo.append(core)

        # Navigate away from home first
        neighbors = list(galaxy.systems[galaxy.home_system].connections.keys())
        dest = neighbors[0]
        galaxy.current_system = dest
        galaxy.arrive_at(dest)

        # Ensure we can navigate back to home
        engine.ship.fuel = 10
        state.focus = "navigation"

        # Find direction from current to home
        current_sys = galaxy.systems[galaxy.current_system]
        home_sys = galaxy.systems[galaxy.home_system]
        dx = home_sys.gx - current_sys.gx
        dy = home_sys.gy - current_sys.gy
        direction = ((dx > 0) - (dx < 0), (dy > 0) - (dy < 0))

        # Simulate keypress for that direction
        from ui.keys import move_keys

        dir_to_key = {v: k for k, v in move_keys().items()}
        key = dir_to_key[direction]
        event = FakeEvent(sym=key)
        state.ev_key(engine, event)

        from ui.game_over_state import GameOverState

        assert isinstance(engine._state_stack[-1], GameOverState)
        assert engine._state_stack[-1].victory is True
        assert "VICTORY" in engine._state_stack[-1].title

    def test_no_victory_on_home_without_core(self):
        """Arriving home without dreadnought_core does NOT trigger victory."""
        from tests.conftest import FakeEvent
        from ui.strategic_state import StrategicState

        engine, galaxy = _make_engine_with_galaxy(seed=42)
        state = StrategicState(galaxy)
        engine._state_stack.append(state)

        # Put a regular reactor_core in cargo — should not trigger victory
        regular = Entity(
            char="*",
            color=(180, 80, 255),
            name="Reactor Core",
            blocks_movement=False,
            item={"type": "reactor_core", "value": 5},
        )
        engine.ship.cargo.append(regular)

        neighbors = list(galaxy.systems[galaxy.home_system].connections.keys())
        dest = neighbors[0]
        galaxy.current_system = dest
        galaxy.arrive_at(dest)

        engine.ship.fuel = 10
        state.focus = "navigation"

        current_sys = galaxy.systems[galaxy.current_system]
        home_sys = galaxy.systems[galaxy.home_system]
        dx = home_sys.gx - current_sys.gx
        dy = home_sys.gy - current_sys.gy
        direction = ((dx > 0) - (dx < 0), (dy > 0) - (dy < 0))

        from ui.keys import move_keys

        dir_to_key = {v: k for k, v in move_keys().items()}
        key = dir_to_key[direction]
        event = FakeEvent(sym=key)
        state.ev_key(engine, event)

        # Should still be on StrategicState, no victory
        assert engine._state_stack[-1] is state

    def test_cargo_transfer_blocked_for_dreadnought_core(self):
        """Dreadnought core cannot be transferred from cargo to personal inventory."""
        from ui.cargo_state import CargoState

        engine = Engine()
        engine.ship = Ship()
        engine.mission_loadout = []
        engine._saved_player = {
            "hp": 10,
            "max_hp": 10,
            "defense": 0,
            "power": 1,
            "base_power": 1,
            "inventory": [],
            "loadout": None,
        }

        core = Entity(
            char="*",
            color=(255, 50, 50),
            name="Dreadnought Core",
            blocks_movement=False,
            item={"type": "dreadnought_core", "value": 99},
        )
        engine.ship.cargo.append(core)

        cs = CargoState()
        cs._section = 1  # _CARGO
        cs.selected = 0

        cs._transfer(engine)

        # Core must remain in cargo
        assert len(engine.ship.cargo) == 1
        assert engine.ship.cargo[0] is core


# ---------------------------------------------------------------------------
# Trigger tests
# ---------------------------------------------------------------------------


class TestDreadnoughtTrigger:
    def test_reveal_on_sixth_nav_unit(self):
        """Dreadnought spawns after installing 6th nav unit on tactical exit."""
        from tests.conftest import make_arena
        from ui.tactical_state import TacticalState
        from world.galaxy import Location

        engine = Engine()
        engine.ship = Ship()
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        engine.galaxy = galaxy
        engine.ship.nav_units = 5  # already have 5

        loc = Location("Test", "derelict", system_name="TestSys")
        ts = TacticalState(location=loc, depth=0)

        gm = make_arena()
        nav = Entity(
            char="n",
            color=(0, 255, 200),
            name="Nav Unit",
            blocks_movement=False,
            item={"type": "nav_unit", "value": 1},
        )
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        player.inventory.append(nav)
        gm.entities.append(player)
        engine.game_map = gm
        engine.player = player

        ts.on_exit(engine)

        assert engine.ship.nav_units == 6
        assert galaxy.dreadnought_system == DREADNOUGHT_SYSTEM_NAME

    def test_no_reveal_before_six(self):
        """Dreadnought does not spawn with fewer than 6 nav units."""
        from tests.conftest import make_arena
        from ui.tactical_state import TacticalState
        from world.galaxy import Location

        engine = Engine()
        engine.ship = Ship()
        galaxy = Galaxy(seed=42)
        _expand_all(galaxy)
        engine.galaxy = galaxy
        engine.ship.nav_units = 4  # only 4 before

        loc = Location("Test", "derelict", system_name="TestSys")
        ts = TacticalState(location=loc, depth=0)

        gm = make_arena()
        nav = Entity(
            char="n",
            color=(0, 255, 200),
            name="Nav Unit",
            blocks_movement=False,
            item={"type": "nav_unit", "value": 1},
        )
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        player.inventory.append(nav)
        gm.entities.append(player)
        engine.game_map = gm
        engine.player = player

        ts.on_exit(engine)

        assert engine.ship.nav_units == 5
        assert galaxy.dreadnought_system is None
