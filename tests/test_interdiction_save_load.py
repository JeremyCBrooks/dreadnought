"""Tests for Interdiction save/load round-trip.

Composite map is NOT serialized - it's deterministically rebuilt from
``pirate_ship_seed`` + saved airlock interior positions when the player
next enters the ship. Pirate entities serialize with their composite-coord
positions and re-attach via ``rebuild_composite``.
"""

from __future__ import annotations

import random

from game.entity import Entity
from game.interdiction import Interdiction, rebuild_composite, start_interdiction
from game.ship import Ship
from web.save_load import dict_to_engine, engine_to_dict
from world.dungeon_gen import generate_player_ship
from world.galaxy import Galaxy


def _engine_with_galaxy_and_ship(seed: int = 42):
    from engine.game_state import Engine

    engine = Engine()
    engine.galaxy = Galaxy(seed=seed)
    ship = Ship(fuel=5, max_fuel=10)
    gm, rooms, exit_pos = generate_player_ship(seed=engine.galaxy.seed)
    ship.game_map = gm
    ship.rooms = rooms
    ship.exit_pos = exit_pos
    ship.cargo.append(Entity(x=0, y=0, char="!", color=(255, 255, 255), name="placeholder", item={"type": "junk"}))
    engine.ship = ship
    engine.saved_player = None
    engine.environment = None
    return engine


def _start_in_engine(engine, system_name: str):
    """Hand-roll an interdiction at *system_name* using a seed that produces a valid composite."""
    sys = engine.galaxy.systems[system_name]
    for s in range(50):
        interdiction = Interdiction()
        # We need a fresh ship-map for each retry, since start_interdiction swaps.
        gm, rooms, exit_pos = generate_player_ship(seed=engine.galaxy.seed)
        engine.ship.game_map = gm
        engine.ship.rooms = rooms
        engine.ship.exit_pos = exit_pos
        start_interdiction(interdiction, engine.ship, rng=random.Random(s))
        if interdiction.started:
            sys.interdiction = interdiction
            return interdiction
    raise RuntimeError("could not start interdiction with any seed")


# ---- Resolved interdiction ----


def test_save_load_preserves_resolved_interdiction():
    engine = _engine_with_galaxy_and_ship()
    name = next(iter(engine.galaxy.systems[engine.galaxy.home_system].connections))
    engine.galaxy.systems[name].interdiction = Interdiction(started=True, resolved=True)
    data = engine_to_dict(engine)

    from engine.game_state import Engine

    new_engine = Engine()
    dict_to_engine(data, new_engine)
    loaded = new_engine.galaxy.systems[name].interdiction
    assert loaded is not None
    assert loaded.started is True
    assert loaded.resolved is True


# ---- Active interdiction ----


def test_save_load_preserves_active_interdiction_metadata():
    engine = _engine_with_galaxy_and_ship()
    name = next(iter(engine.galaxy.systems[engine.galaxy.home_system].connections))
    interdiction = _start_in_engine(engine, engine.galaxy.home_system)
    # Move the interdiction to a non-home system for realism (it's just bookkeeping)
    engine.galaxy.systems[engine.galaxy.home_system].interdiction = None
    engine.galaxy.systems[name].interdiction = interdiction

    interdiction.pirate_entities[0].fighter.hp = 1
    data = engine_to_dict(engine)

    from engine.game_state import Engine

    new_engine = Engine()
    dict_to_engine(data, new_engine)
    loaded = new_engine.galaxy.systems[name].interdiction

    assert loaded is not None
    assert loaded.started is True
    assert loaded.resolved is False
    assert len(loaded.pirate_entities) == len(interdiction.pirate_entities)
    assert loaded.pirate_entities[0].fighter.hp == 1
    assert loaded.pirate_ship_seed == interdiction.pirate_ship_seed
    assert loaded.player_offset == interdiction.player_offset
    assert loaded.pirate_offset == interdiction.pirate_offset
    assert loaded.player_airlock_interior == interdiction.player_airlock_interior
    assert loaded.pirate_airlock_interior == interdiction.pirate_airlock_interior
    # composite_map is NOT serialized - must be None on load
    assert loaded.composite_map is None
    assert loaded.original_ship_map is None


def test_loaded_interdiction_can_rebuild_composite():
    """After load, the saved metadata must let us regenerate the same composite."""
    engine = _engine_with_galaxy_and_ship()
    interdiction = _start_in_engine(engine, engine.galaxy.home_system)
    saved_pirate_int = interdiction.pirate_airlock_interior
    saved_player_int = interdiction.player_airlock_interior
    data = engine_to_dict(engine)

    from engine.game_state import Engine

    new_engine = Engine()
    dict_to_engine(data, new_engine)
    loaded = new_engine.galaxy.systems[new_engine.galaxy.home_system].interdiction
    ok = rebuild_composite(loaded, new_engine.ship)
    assert ok is True
    assert loaded.composite_map is not None
    # Same airlock positions reproduced
    assert loaded.player_airlock_interior == saved_player_int
    assert loaded.pirate_airlock_interior == saved_pirate_int


def test_save_load_pirate_stolen_loot_round_trips():
    """Stolen items carried by pirates survive save/load."""
    engine = _engine_with_galaxy_and_ship()
    interdiction = _start_in_engine(engine, engine.galaxy.home_system)
    pirate = interdiction.pirate_entities[0]
    if not pirate.inventory:
        item = Entity(
            x=0, y=0, char="!", color=(255, 255, 255), name="Stolen Med-kit", item={"type": "heal", "value": 5}
        )
        pirate.inventory.append(item)
    pirate.stolen_loot.append(pirate.inventory[0])

    data = engine_to_dict(engine)

    from engine.game_state import Engine

    new_engine = Engine()
    dict_to_engine(data, new_engine)
    loaded_pirate = new_engine.galaxy.systems[new_engine.galaxy.home_system].interdiction.pirate_entities[0]
    assert loaded_pirate.inventory
    assert loaded_pirate.stolen_loot
    assert loaded_pirate.stolen_loot[0] is loaded_pirate.inventory[0]


def test_save_mid_ship_explore_persists_pirates_and_flushes_player():
    """Disconnect-style save while INSIDE the ship during an interdiction:
    1. Persists alive pirates without stripping them from the live map
       (a reconnect reuses the in-memory engine).
    2. Refreshes _saved_player from live engine.player.
    """
    from unittest.mock import patch

    from ui.tactical_state import TacticalState

    engine = _engine_with_galaxy_and_ship()
    engine.galaxy.current_system = engine.galaxy.home_system
    interdiction = _start_in_engine(engine, engine.galaxy.home_system)

    # Push a TacticalState in explore_ship mode and call on_enter so engine
    # is fully wired up (player placed, pirates attached).
    state = TacticalState(explore_ship=True)
    engine.push_state(state)
    with patch("world.game_map.GameMap.update_fov", lambda *a, **k: None):
        state.on_enter(engine)
    assert any(p in engine.game_map.entities for p in interdiction.pirate_entities)

    engine.player.fighter.hp = 3
    pickup = Entity(x=0, y=0, char="!", color=(255, 255, 255), name="picked-up", item={"type": "junk"})
    engine.player.inventory.append(pickup)

    data = engine_to_dict(engine)

    # Live engine: pirates still on the map for a reconnecting player.
    assert all(p in engine.game_map.entities for p in interdiction.pirate_entities)
    # _saved_player reflects live engine.player.
    assert engine.saved_player["hp"] == 3
    assert "picked-up" in [it.name for it in engine.saved_player["inventory"]]

    # Reload: composite rebuilds via prepare_ship_entry, pirates re-attach.
    from engine.game_state import Engine

    new_engine = Engine()
    dict_to_engine(data, new_engine)
    loaded = new_engine.galaxy.systems[engine.galaxy.home_system].interdiction
    assert loaded.started is True and loaded.resolved is False
    assert loaded.pirate_entities
    # Saved player carries HP=3 and the pickup.
    assert new_engine.saved_player["hp"] == 3
    assert "picked-up" in [it.name for it in new_engine.saved_player["inventory"]]


def test_save_load_no_interdiction_still_works():
    engine = _engine_with_galaxy_and_ship()
    data = engine_to_dict(engine)

    from engine.game_state import Engine

    new_engine = Engine()
    dict_to_engine(data, new_engine)
    for sys in new_engine.galaxy.systems.values():
        assert sys.interdiction is None
