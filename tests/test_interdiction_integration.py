"""End-to-end integration test for ship interdiction (Phase 9).

Wires the full feature together:
1. Travel to a non-home system with non-empty cargo + forced RNG hit.
2. Strategic banner appears; navigation gated.
3. Press [S] -> ship interior shows craft + pirates.
4. Kill all pirates -> resolution fires.
5. Exit ship -> navigation works again.
"""

from __future__ import annotations

import random
from unittest.mock import patch

from game.entity import Entity, Fighter
from game.ship import Ship
from tests.conftest import FakeEvent, MockEngine, make_arena
from ui.strategic_state import StrategicState
from world.dungeon_gen import generate_player_ship
from world.galaxy import Galaxy


def _sym(name):
    import tcod.event

    return getattr(tcod.event.KeySym, name)


def _fully_loaded_engine(seed: int = 42):
    galaxy = Galaxy(seed=seed)
    ship = Ship(fuel=10, max_fuel=10)
    gm, rooms, exit_pos = generate_player_ship(seed=galaxy.seed)
    ship.game_map = gm
    ship.rooms = rooms
    ship.exit_pos = exit_pos
    # Cargo so interdiction is eligible
    ship.cargo.append(Entity(x=0, y=0, char="!", color=(255, 255, 255), name="loot", item={"type": "junk"}))

    arena = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(50, 50, 0, 5))
    arena.entities.append(player)
    engine = MockEngine(arena, player)
    engine.ship = ship
    engine.galaxy = galaxy
    engine.CONSOLE_WIDTH = 160
    engine.CONSOLE_HEIGHT = 50
    return engine, galaxy


def test_full_interdiction_round_trip():
    engine, galaxy = _fully_loaded_engine()
    # Force the next interdiction roll to succeed by patching engine.rng for the salt
    # we know strategic_state uses.
    real_rng = engine.rng

    class _ForceTrigger:
        """Force the trigger roll (random()) to succeed; delegate everything else
        to a real Random so pirate-ship generation/airlock-pair search works."""

        def __init__(self) -> None:
            self._real = random.Random(0)

        def random(self):
            return 0.0  # < INTERDICTION_CHANCE

        def randint(self, a, b):
            return self._real.randint(a, b)

        def choice(self, seq):
            return self._real.choice(seq)

        def choices(self, seq, weights=None):
            return self._real.choices(seq, weights=weights)

        def sample(self, seq, k):
            return self._real.sample(seq, k)

        def shuffle(self, seq):
            self._real.shuffle(seq)

    def _fake_rng(salt):
        if salt.startswith("interdiction:") or salt.startswith("start_interdiction:"):
            return _ForceTrigger()
        return real_rng(salt)

    engine.rng = _fake_rng

    # ---- Step 1: travel ----
    home = galaxy.systems[galaxy.home_system]
    dest_name = next(iter(home.connections))
    state = StrategicState(galaxy)
    state.ev_key(engine, FakeEvent(_sym("TAB")))  # navigation focus
    # Pick the right direction toward dest
    dest_sys = galaxy.systems[dest_name]
    dx_grid = dest_sys.gx - home.gx
    dy_grid = dest_sys.gy - home.gy
    direction_to_key = {
        (0, -1): "UP",
        (0, 1): "DOWN",
        (-1, 0): "LEFT",
        (1, 0): "RIGHT",
        (-1, -1): "HOME",
        (1, -1): "PAGEUP",
        (-1, 1): "END",
        (1, 1): "PAGEDOWN",
    }
    state.ev_key(engine, FakeEvent(_sym(direction_to_key.get((dx_grid, dy_grid), "RIGHT"))))

    assert galaxy.current_system == dest_name
    interdiction = galaxy.systems[dest_name].interdiction
    assert interdiction is not None, "interdiction should have been queued"
    assert not interdiction.resolved

    # ---- Step 2: navigation blocked ----
    fuel_before = engine.ship.fuel
    state.ev_key(engine, FakeEvent(_sym("LEFT")))
    assert engine.ship.fuel == fuel_before, "fuel should not be consumed when blocked"
    assert galaxy.current_system == dest_name, "must still be at dest"

    # ---- Step 3: enter ship and verify pirates spawn ----
    from ui.tactical_state import TacticalState

    ts = TacticalState(explore_ship=True)
    with patch.object(engine.ship.game_map, "update_fov"):
        ts.on_enter(engine)
    assert interdiction.started
    assert interdiction.pirate_entities, "pirates should be on the boarding craft"
    for p in interdiction.pirate_entities:
        assert p in engine.game_map.entities

    # ---- Step 4: kill all pirates and resolve ----
    for p in interdiction.pirate_entities:
        p.fighter.hp = 0
    ts._after_player_turn(engine)
    assert interdiction.resolved is True

    # Reset engine.rng so the next arrive_at uses a real (non-forcing) RNG.
    engine.rng = real_rng

    # ---- Step 5: exit ship and travel away ----
    ts.on_exit(engine)
    # Now navigation should work again.
    state.ev_key(engine, FakeEvent(_sym(direction_to_key.get((-dx_grid, -dy_grid), "LEFT"))))
    assert galaxy.current_system == galaxy.home_system, f"should have returned to home, got {galaxy.current_system}"
