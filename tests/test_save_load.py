"""Tests for web/save_load.py — engine serialization round-trips."""

import numpy as np

from engine.game_state import Engine
from engine.message_log import MessageLog
from game.entity import Entity, Fighter
from game.loadout import Loadout
from game.ship import Ship
from world.galaxy import Galaxy

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_weapon(name: str = "Plasma Cutter") -> Entity:
    return Entity(
        name=name,
        char="/",
        color=(200, 100, 50),
        item={"type": "weapon", "weapon_class": "melee", "value": 3},
    )


def make_scanner() -> Entity:
    return Entity(
        name="Scanner Mk1",
        char="s",
        color=(100, 200, 100),
        item={"type": "scanner", "durability": 5},
    )


def make_player_entity() -> Entity:
    return Entity(
        char="@",
        color=(255, 255, 255),
        name="Player",
        fighter=Fighter(hp=7, max_hp=10, defense=1, power=2),
    )


def make_engine_with_galaxy(seed: int = 42) -> Engine:
    """Return an Engine with galaxy, ship, and message_log populated."""
    engine = Engine()
    galaxy = Galaxy(seed=seed)
    engine.galaxy = galaxy

    ship = Ship(fuel=4, max_fuel=10, scanner_quality=2, hull=8, max_hull=10)
    weapon_cargo = make_weapon("Old Sword")
    ship.cargo.append(weapon_cargo)
    engine.ship = ship

    engine.message_log.add_message("Hello world", (255, 255, 0))
    engine.message_log.add_message("Second message", (200, 200, 200))

    return engine


# ── Entity round-trip ─────────────────────────────────────────────────────────


def test_entity_item_round_trip():
    from web.save_load import _entity_from_dict, _entity_to_dict

    weapon = make_weapon()
    d = _entity_to_dict(weapon)
    assert d["name"] == "Plasma Cutter"
    assert d["char"] == "/"
    assert d["color"] == [200, 100, 50]
    assert d["item"] == {"type": "weapon", "weapon_class": "melee", "value": 3}
    assert "fighter" not in d

    restored = _entity_from_dict(d)
    assert restored.name == "Plasma Cutter"
    assert restored.char == "/"
    assert restored.color == (200, 100, 50)
    assert restored.item == {"type": "weapon", "weapon_class": "melee", "value": 3}
    assert restored.fighter is None


def test_entity_blocks_movement_preserved():
    """Items must stay non-blocking through save/load (root cause: dropped items were blocking tiles)."""
    from web.save_load import _entity_from_dict, _entity_to_dict

    item = Entity(
        name="Scanner Mk1",
        char="s",
        color=(100, 200, 100),
        blocks_movement=False,
        item={"type": "scanner", "tier": 1},
    )
    d = _entity_to_dict(item)
    restored = _entity_from_dict(d)
    assert restored.blocks_movement is False


def test_entity_blocks_movement_true_preserved():
    """blocks_movement=True is also faithfully restored."""
    from web.save_load import _entity_from_dict, _entity_to_dict

    ent = Entity(name="Blocker", char="B", color=(255, 0, 0), blocks_movement=True)
    d = _entity_to_dict(ent)
    restored = _entity_from_dict(d)
    assert restored.blocks_movement is True


def test_ship_cargo_items_not_blocking_after_round_trip():
    """Ship cargo items restored from save must have blocks_movement=False."""
    from game.ship import Ship
    from web.save_load import _ship_from_dict, _ship_to_dict

    ship = Ship()
    scanner = Entity(
        name="Scanner",
        char="s",
        color=(100, 200, 100),
        blocks_movement=False,
        item={"type": "scanner", "tier": 2},
    )
    ship.cargo.append(scanner)

    restored_ship = _ship_from_dict(_ship_to_dict(ship))
    assert restored_ship.cargo[0].blocks_movement is False


def test_saved_player_inventory_items_not_blocking_after_round_trip():
    """Player inventory items from a save must have blocks_movement=False when restored."""
    from web.save_load import _saved_player_from_dict, _saved_player_to_dict

    weapon = Entity(
        name="Plasma Cutter",
        char="/",
        color=(200, 100, 50),
        blocks_movement=False,
        item={"type": "weapon", "weapon_class": "melee", "value": 3},
    )
    scanner = Entity(
        name="Scanner",
        char="s",
        color=(100, 200, 100),
        blocks_movement=False,
        item={"type": "scanner", "tier": 1},
    )
    lo = Loadout(slot1=weapon)
    sp = {
        "hp": 8,
        "max_hp": 10,
        "defense": 1,
        "power": 2,
        "base_power": 2,
        "inventory": [weapon, scanner],
        "loadout": lo,
    }

    restored = _saved_player_from_dict(_saved_player_to_dict(sp))
    for item in restored["inventory"]:
        assert item.blocks_movement is False, f"{item.name} should not block movement after restore"


def test_entity_fighter_round_trip():
    from web.save_load import _entity_from_dict, _entity_to_dict

    player = make_player_entity()
    player.fighter.power = 5  # modified power (base is still 2)
    d = _entity_to_dict(player)
    assert d["fighter"]["hp"] == 7
    assert d["fighter"]["max_hp"] == 10
    assert d["fighter"]["defense"] == 1
    assert d["fighter"]["power"] == 5
    assert d["fighter"]["base_power"] == 2

    restored = _entity_from_dict(d)
    assert restored.fighter is not None
    assert restored.fighter.hp == 7
    assert restored.fighter.max_hp == 10
    assert restored.fighter.defense == 1
    assert restored.fighter.power == 5
    assert restored.fighter.base_power == 2


# ── Ship round-trip ───────────────────────────────────────────────────────────


def test_ship_fields_round_trip():
    from web.save_load import _ship_from_dict, _ship_to_dict

    ship = Ship(fuel=3, max_fuel=12, scanner_quality=3, hull=5, max_hull=10)
    ship.nav_units = 2
    weapon = make_weapon()
    ship.cargo.append(weapon)

    d = _ship_to_dict(ship)
    assert d["fuel"] == 3
    assert d["max_fuel"] == 12
    assert d["scanner_quality"] == 3
    assert d["hull"] == 5
    assert d["max_hull"] == 10
    assert d["nav_units"] == 2
    assert len(d["cargo"]) == 1
    assert d["cargo"][0]["name"] == "Plasma Cutter"

    restored = _ship_from_dict(d)
    assert restored.fuel == 3
    assert restored.max_fuel == 12
    assert restored.scanner_quality == 3
    assert restored.hull == 5
    assert restored.max_hull == 10
    assert restored.nav_units == 2
    assert len(restored.cargo) == 1
    assert restored.cargo[0].name == "Plasma Cutter"


def test_ship_empty_cargo():
    from web.save_load import _ship_from_dict, _ship_to_dict

    ship = Ship()
    d = _ship_to_dict(ship)
    assert d["cargo"] == []
    restored = _ship_from_dict(d)
    assert restored.cargo == []


# ── Galaxy round-trip ─────────────────────────────────────────────────────────


def test_galaxy_basic_fields_round_trip():
    from web.save_load import _galaxy_from_dict, _galaxy_to_dict

    galaxy = Galaxy(seed=99)
    d = _galaxy_to_dict(galaxy)

    assert d["seed"] == 99
    assert d["home_system"] == galaxy.home_system
    assert d["current_system"] == galaxy.current_system
    assert d["dreadnought_system"] is None

    restored = _galaxy_from_dict(d)
    assert restored.seed == 99
    assert restored.home_system == galaxy.home_system
    assert restored.current_system == galaxy.current_system
    assert restored.dreadnought_system is None


def test_galaxy_systems_preserved():
    from web.save_load import _galaxy_from_dict, _galaxy_to_dict

    galaxy = Galaxy(seed=7)
    d = _galaxy_to_dict(galaxy)
    restored = _galaxy_from_dict(d)

    assert set(restored.systems.keys()) == set(galaxy.systems.keys())
    for name, sys in galaxy.systems.items():
        rsys = restored.systems[name]
        assert rsys.gx == sys.gx
        assert rsys.gy == sys.gy
        assert rsys.depth == sys.depth
        assert rsys.star_type == sys.star_type
        assert rsys.connections == sys.connections


def test_galaxy_location_fields_preserved():
    from web.save_load import _galaxy_from_dict, _galaxy_to_dict

    galaxy = Galaxy(seed=13)
    # Mark some location state
    home_sys = galaxy.systems[galaxy.home_system]
    if home_sys.locations:
        home_sys.locations[0].visited = True
        home_sys.locations[0].scanned = True

    d = _galaxy_to_dict(galaxy)
    restored = _galaxy_from_dict(d)

    rhome = restored.systems[galaxy.home_system]
    if rhome.locations:
        assert rhome.locations[0].visited is True
        assert rhome.locations[0].scanned is True


def test_galaxy_nav_unit_rings_preserved():
    from web.save_load import _galaxy_from_dict, _galaxy_to_dict

    galaxy = Galaxy(seed=5)
    d = _galaxy_to_dict(galaxy)
    restored = _galaxy_from_dict(d)

    assert restored._nav_unit_rings == galaxy._nav_unit_rings


def test_galaxy_frontier_sets_preserved():
    from web.save_load import _galaxy_from_dict, _galaxy_to_dict

    galaxy = Galaxy(seed=17)
    d = _galaxy_to_dict(galaxy)
    restored = _galaxy_from_dict(d)

    assert restored._generated_frontiers == galaxy._generated_frontiers
    assert restored._unexplored_frontier == galaxy._unexplored_frontier


# ── _saved_player round-trip ──────────────────────────────────────────────────


def test_saved_player_none_round_trip():
    from web.save_load import _saved_player_from_dict, _saved_player_to_dict

    assert _saved_player_to_dict(None) is None
    assert _saved_player_from_dict(None) is None


def test_saved_player_fields_round_trip():
    from web.save_load import _saved_player_from_dict, _saved_player_to_dict

    weapon = make_weapon()
    scanner = make_scanner()
    lo = Loadout(slot1=weapon)
    sp = {
        "hp": 6,
        "max_hp": 10,
        "defense": 2,
        "power": 3,
        "base_power": 3,
        "inventory": [weapon, scanner],
        "loadout": lo,
    }

    d = _saved_player_to_dict(sp)
    assert d["hp"] == 6
    assert d["loadout"]["slot1_idx"] == 0
    assert d["loadout"]["slot2_idx"] is None
    assert len(d["inventory"]) == 2

    restored = _saved_player_from_dict(d)
    assert restored["hp"] == 6
    assert restored["max_hp"] == 10
    assert len(restored["inventory"]) == 2
    lo_r = restored["loadout"]
    assert lo_r is not None
    assert lo_r.slot1 is restored["inventory"][0]
    assert lo_r.slot2 is None


def test_saved_player_both_slots():
    from web.save_load import _saved_player_from_dict, _saved_player_to_dict

    weapon = make_weapon()
    scanner = make_scanner()
    lo = Loadout(slot1=weapon, slot2=scanner)
    sp = {
        "hp": 5,
        "max_hp": 10,
        "defense": 0,
        "power": 1,
        "base_power": 1,
        "inventory": [weapon, scanner],
        "loadout": lo,
    }

    d = _saved_player_to_dict(sp)
    assert d["loadout"]["slot1_idx"] == 0
    assert d["loadout"]["slot2_idx"] == 1

    restored = _saved_player_from_dict(d)
    assert restored["loadout"].slot1 is restored["inventory"][0]
    assert restored["loadout"].slot2 is restored["inventory"][1]


# ── Message log round-trip ────────────────────────────────────────────────────


def test_message_log_round_trip():
    from web.save_load import _log_from_list, _log_to_list

    log = MessageLog()
    log.add_message("Hello", (255, 200, 0))
    log.add_message("World", (100, 100, 255))

    lst = _log_to_list(log)
    assert lst == [["Hello", [255, 200, 0]], ["World", [100, 100, 255]]]

    restored = _log_from_list(lst)
    assert restored.messages == (("Hello", (255, 200, 0)), ("World", (100, 100, 255)))


def test_message_log_empty():
    from web.save_load import _log_from_list, _log_to_list

    log = MessageLog()
    assert _log_to_list(log) == []
    restored = _log_from_list([])
    assert restored.messages == ()


# ── Full engine round-trip ────────────────────────────────────────────────────


def test_engine_to_dict_structure():
    from web.save_load import engine_to_dict

    engine = make_engine_with_galaxy()
    d = engine_to_dict(engine)

    assert "galaxy" in d
    assert "ship" in d
    assert "message_log" in d
    assert "saved_player" in d
    assert d["saved_player"] is None  # no player yet


def test_engine_to_dict_with_saved_player():
    from web.save_load import engine_to_dict

    engine = make_engine_with_galaxy()
    weapon = make_weapon()
    engine._saved_player = {
        "hp": 8,
        "max_hp": 10,
        "defense": 1,
        "power": 2,
        "base_power": 2,
        "inventory": [weapon],
        "loadout": Loadout(slot1=weapon),
    }
    d = engine_to_dict(engine)
    assert d["saved_player"]["hp"] == 8
    assert len(d["saved_player"]["inventory"]) == 1


def test_dict_to_engine_restores_state():
    from ui.strategic_state import StrategicState
    from web.save_load import dict_to_engine, engine_to_dict

    engine = make_engine_with_galaxy(seed=55)
    engine._saved_player = {
        "hp": 7,
        "max_hp": 10,
        "defense": 0,
        "power": 1,
        "base_power": 1,
        "inventory": [],
        "loadout": None,
    }

    d = engine_to_dict(engine)

    new_engine = Engine()
    dict_to_engine(d, new_engine)

    assert new_engine.galaxy is not None
    assert new_engine.galaxy.seed == 55
    assert new_engine.ship is not None
    assert new_engine.ship.fuel == engine.ship.fuel
    assert new_engine._saved_player is not None
    assert new_engine._saved_player["hp"] == 7
    assert isinstance(new_engine.current_state, StrategicState)


def test_dict_to_engine_message_log_restored():
    from web.save_load import dict_to_engine, engine_to_dict

    engine = make_engine_with_galaxy()
    d = engine_to_dict(engine)

    new_engine = Engine()
    dict_to_engine(d, new_engine)

    # "You are aboard your ship." is added by StrategicState.on_enter, but original messages are there too
    texts = [m[0] for m in new_engine.message_log.messages]
    assert "Hello world" in texts
    assert "Second message" in texts


def test_dict_to_engine_cargo_restored():
    from web.save_load import dict_to_engine, engine_to_dict

    engine = make_engine_with_galaxy()
    d = engine_to_dict(engine)

    new_engine = Engine()
    dict_to_engine(d, new_engine)

    assert len(new_engine.ship.cargo) == 1
    assert new_engine.ship.cargo[0].name == "Old Sword"


def test_dict_to_engine_no_saved_player():
    from web.save_load import dict_to_engine, engine_to_dict

    engine = make_engine_with_galaxy()
    d = engine_to_dict(engine)

    new_engine = Engine()
    dict_to_engine(d, new_engine)

    assert new_engine._saved_player is None


def test_save_load_preserves_ship_map():
    """Ship map should be regenerated from galaxy seed on load, not serialized."""
    from web.save_load import dict_to_engine, engine_to_dict
    from world.dungeon_gen import generate_player_ship

    seed = 42
    engine = make_engine_with_galaxy(seed=seed)

    # Set up ship with map from the seed
    gm_orig, rooms_orig, exit_pos_orig = generate_player_ship(seed=seed)
    engine.ship.game_map = gm_orig
    engine.ship.rooms = rooms_orig
    engine.ship.exit_pos = exit_pos_orig

    # Save the engine
    d = engine_to_dict(engine)

    # Load into a fresh engine
    new_engine = Engine()
    dict_to_engine(d, new_engine)

    # Verify tiles are identical — same seed must produce the same layout
    assert new_engine.ship is not None
    assert new_engine.ship.game_map is not None
    assert np.array_equal(new_engine.ship.game_map.tiles, gm_orig.tiles)
    assert new_engine.ship.rooms is not None
    assert len(new_engine.ship.rooms) > 0
    assert new_engine.ship.exit_pos is not None
