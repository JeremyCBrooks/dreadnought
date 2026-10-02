"""Regression tests for the bugs found in the whole-project audit."""

from __future__ import annotations

import asyncio
import json
import os
import random
import subprocess
import sys
import zlib
from pathlib import Path

import pytest
import tcod.console
import tcod.event
from fastapi import FastAPI
from starlette.testclient import TestClient

import web.db as db
import web.game_manager as gm
from engine.game_state import Engine
from game.actions import RangedAction
from game.ai import CreatureAI
from game.entity import Entity, Fighter
from game.interdiction import Interdiction, start_interdiction
from game.ship import Ship
from game.suit import EVA_SUIT
from tests.conftest import FakeEvent, make_heal_item, make_scanner, make_weapon
from ui.game_over_state import GameOverState
from ui.keys import move_keys
from ui.strategic_state import StrategicState
from ui.tactical_state import TacticalState
from ui.title_state import TitleState
from web.save_load import dict_to_engine, engine_to_dict
from world import tile_types
from world.galaxy import Galaxy
from world.game_map import GameMap

K = tcod.event.KeySym
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _new_game(seed: int = 1) -> tuple[Engine, StrategicState]:
    engine = Engine()
    engine.galaxy = Galaxy(seed=seed)
    engine.ship = Ship()
    engine.ship.generate_interior(engine.galaxy.seed)
    strategic = StrategicState(engine.galaxy)
    engine.push_state(strategic)
    return engine, strategic


def _location(engine: Engine, loc_type: str):
    for system in engine.galaxy.systems.values():
        for loc in system.locations:
            if loc.loc_type == loc_type:
                return loc
    pytest.fail(f"seed has no {loc_type}")


def _enter_mission(engine: Engine, loc_type: str = "colony") -> TacticalState:
    state = TacticalState(location=_location(engine, loc_type), depth=0)
    engine.push_state(state)
    return state


def _enter_ship(engine: Engine) -> TacticalState:
    state = TacticalState(explore_ship=True)
    engine.push_state(state)
    return state


def _key_for(direction: tuple[int, int]) -> int:
    return next(key for key, move in move_keys().items() if move == direction)


def _messages(engine: Engine) -> list[str]:
    return [text for text, _ in engine.message_log.messages]


def _reload(engine: Engine) -> Engine:
    """Round-trip *engine* through a JSON save into a fresh engine, as a new server process would."""
    loaded = Engine()
    dict_to_engine(json.loads(json.dumps(engine_to_dict(engine))), loaded)
    return loaded


def _console() -> tcod.console.Console:
    return tcod.console.Console(Engine.CONSOLE_WIDTH, Engine.CONSOLE_HEIGHT, order="F")


# ── 2. turn_counter advances with game time ───────────────────────────────────


def test_turn_counter_advances_once_per_game_turn():
    engine, _ = _new_game()
    state = _enter_mission(engine)
    before = engine.turn_counter
    state._after_player_turn(engine)
    state._after_player_turn(engine)
    assert engine.turn_counter == before + 2


def test_same_salt_rolls_differently_on_later_turns():
    engine, _ = _new_game()
    state = _enter_mission(engine)
    rolls = set()
    for _ in range(6):
        state._after_player_turn(engine)
        rolls.add(engine.rng("steal:5,5").random())
    assert len(rolls) == 6


# ── 3. only walking onto the exit leaves the mission ──────────────────────────


def test_scanning_on_the_spawn_tile_stays_in_the_mission():
    engine, _ = _new_game()
    engine.mission_loadout = [make_scanner()]
    state = _enter_mission(engine, "derelict")
    assert (engine.player.x, engine.player.y) == state.exit_pos

    state.ev_key(engine, FakeEvent(K.S))

    assert engine.current_state is state
    assert engine.scan_results is not None


def test_waiting_on_the_spawn_tile_stays_in_the_mission():
    engine, _ = _new_game()
    state = _enter_mission(engine, "derelict")

    state.ev_key(engine, FakeEvent(K.PERIOD))

    assert engine.current_state is state


def test_walking_back_onto_the_exit_leaves_the_mission():
    engine, strategic = _new_game()
    state = _enter_mission(engine)
    ex, ey = state.exit_pos
    dx, dy = next(
        (dx, dy)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        if engine.game_map.is_walkable(ex + dx, ey + dy) and not engine.game_map.get_blocking_entity(ex + dx, ey + dy)
    )
    state.ev_key(engine, FakeEvent(_key_for((dx, dy))))
    assert engine.current_state is state

    state.ev_key(engine, FakeEvent(_key_for((-dx, -dy))))

    assert engine.current_state is strategic


# ── 4. interdiction resolves however the last pirate dies ─────────────────────


def _boarded_ship(seed: int = 11) -> tuple[Engine, StrategicState, TacticalState, Interdiction]:
    engine, strategic = _new_game(seed)
    interdiction = Interdiction()
    engine.galaxy.systems[engine.galaxy.current_system].interdiction = interdiction
    state = _enter_ship(engine)
    assert interdiction.started and interdiction.pirate_entities
    return engine, strategic, state, interdiction


def test_killing_the_last_pirate_from_the_hatch_resolves_the_interdiction():
    engine, _, state, interdiction = _boarded_ship()
    game_map = engine.game_map
    for extra in interdiction.pirate_entities[1:]:
        extra.fighter.hp = 0
        game_map.entities.remove(extra)
    pirate = interdiction.pirate_entities[0]
    px, py = engine.player.x, engine.player.y
    assert (px, py) == state.exit_pos
    dx, dy = next(
        (dx, dy)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        if game_map.is_walkable(px + dx, py + dy) and not game_map.get_blocking_entity(px + dx, py + dy)
    )
    pirate.x, pirate.y = px + dx, py + dy
    pirate.fighter.hp = 1
    pirate.fighter.defense = 0
    game_map.invalidate_entity_index()

    state.ev_key(engine, FakeEvent(_key_for((dx, dy))))

    assert interdiction.alive_pirate_count() == 0
    assert interdiction.resolved is True


def test_leaving_the_ship_with_every_pirate_dead_resolves_and_restores():
    engine, strategic, _, interdiction = _boarded_ship()
    for pirate in interdiction.pirate_entities:
        pirate.fighter.hp = 0
    assert interdiction.resolved is False

    engine.pop_state()

    assert engine.current_state is strategic
    assert interdiction.resolved is True
    assert interdiction.composite_map is None


def test_leaving_the_ship_with_a_live_pirate_stays_unresolved():
    engine, _, _, interdiction = _boarded_ship()

    engine.pop_state()

    assert interdiction.resolved is False
    assert interdiction.composite_map is not None


# ── 5. the boarding corridor is airtight, bends included ──────────────────────


def test_boarding_corridor_has_no_diagonal_gap_into_space():
    space_tid = int(tile_types.space["tile_id"])
    bent = 0
    for seed in range(15):
        ship = Ship()
        ship.generate_interior(seed)
        interdiction = Interdiction()
        start_interdiction(interdiction, ship, random.Random(seed))
        if not interdiction.started:
            continue
        composite = interdiction.composite_map
        corridor = interdiction.connector_tiles
        bent += len({x for x, _ in corridor}) > 1 and len({y for _, y in corridor}) > 1
        gaps = [
            ((x, y), (dx, dy))
            for x, y in corridor
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if composite.in_bounds(x + dx, y + dy) and int(composite.tiles["tile_id"][x + dx, y + dy]) == space_tid
        ]
        assert gaps == [], f"seed {seed}: corridor tile next to open space"
    assert bent, "no bent corridor in the sample; the test would prove nothing"


# ── 6. a furnishing sitting on a door or switch tile can be searched ──────────


def _arena_with_player() -> tuple[Engine, GameMap, Entity]:
    game_map = GameMap(9, 9)
    for x in range(1, 8):
        for y in range(1, 8):
            game_map.tiles[x, y] = tile_types.floor
    engine = Engine()
    player = Entity(x=4, y=4, char="@", name="Player", fighter=Fighter(10, 10, 0, 1))
    player.max_inventory = 10
    game_map.entities.append(player)
    engine.game_map = game_map
    engine.player = player
    return engine, game_map, player


def _locker(x: int, y: int) -> Entity:
    loot = {"char": "!", "color": (0, 255, 100), "name": "Med-kit", "type": "heal", "value": 5}
    return Entity(
        x=x,
        y=y,
        char="[",
        name="Locker",
        blocks_movement=False,
        interactable={"kind": "locker", "hazard": None, "loot": loot},
    )


@pytest.mark.parametrize(
    ("tile", "kind_after_search"),
    [(tile_types.door_closed, "door"), (tile_types.airlock_switch_off, "switch")],
)
def test_furnishing_on_a_door_or_switch_tile_is_searched_first(tile, kind_after_search):
    engine, game_map, player = _arena_with_player()
    game_map.tiles[4, 3] = tile
    locker = _locker(4, 3)
    game_map.entities.append(locker)

    assert TacticalState._adjacent_interact_dirs(engine) == [(0, -1, "entity")]
    TacticalState._perform_interact(engine, 0, -1, "entity")

    assert locker not in game_map.entities
    assert [item.name for item in player.inventory] == ["Med-kit"]
    assert TacticalState._adjacent_interact_dirs(engine) == [(0, -1, kind_after_search)]


def test_plain_door_still_resolves_to_door():
    engine, game_map, _ = _arena_with_player()
    game_map.tiles[4, 3] = tile_types.door_closed

    assert TacticalState._adjacent_interact_dirs(engine) == [(0, -1, "door")]


# ── 7. a save taken on the post-death title screen loads ──────────────────────


def test_save_from_title_screen_after_death_reloads_to_title():
    engine, _ = _new_game(5)
    engine.switch_state(GameOverState(victory=False, cause="Killed in action."))
    engine.current_state._fade_start -= 5
    engine.current_state.ev_key(engine, FakeEvent(K.RETURN))
    assert isinstance(engine.current_state, TitleState)

    loaded = _reload(engine)

    assert isinstance(loaded.current_state, TitleState)
    loaded.current_state.on_render(_console(), loaded)


# ── 8. a disconnect save never undoes a death or heals the player ─────────────


def test_save_on_the_death_screen_reloads_as_game_over():
    engine, _ = _new_game(5)
    state = _enter_mission(engine)
    engine.player.inventory.append(make_heal_item())
    engine.player.fighter.hp = 0
    state._handle_player_death(engine, "Killed in action.")
    state._death_fade_start -= 5
    state.on_render(_console(), engine)
    assert isinstance(engine.current_state, GameOverState)

    loaded = _reload(engine)

    assert isinstance(loaded.current_state, GameOverState)
    assert loaded.current_state.victory is False
    assert loaded.current_state.cause == "Killed in action."


def test_save_during_the_death_fade_reloads_as_game_over():
    engine, _ = _new_game(5)
    state = _enter_mission(engine)
    engine.player.fighter.hp = 0
    state._handle_player_death(engine, "Overwhelmed by hostiles.")

    loaded = _reload(engine)

    assert isinstance(loaded.current_state, GameOverState)
    assert loaded.current_state.cause == "Overwhelmed by hostiles."


def test_save_on_the_victory_screen_reloads_as_victory():
    engine, _ = _new_game(5)
    engine.switch_state(GameOverState(victory=True, title="VICTORY", cause="You delivered the core."))

    loaded = _reload(engine)

    assert isinstance(loaded.current_state, GameOverState)
    assert loaded.current_state.victory is True
    assert loaded.current_state.title == "VICTORY"


def test_mid_mission_save_keeps_current_hp_not_pre_mission_hp():
    engine, _ = _new_game(5)
    engine._saved_player = {
        "hp": 10,
        "max_hp": 10,
        "defense": 0,
        "power": 1,
        "base_power": 1,
        "inventory": [],
        "loadout": None,
    }
    _enter_mission(engine)
    engine.player.fighter.hp = 1

    loaded = _reload(engine)

    assert isinstance(loaded.current_state, StrategicState)
    assert loaded._saved_player["hp"] == 1


def test_mid_mission_save_leaves_the_live_session_untouched():
    engine, _ = _new_game(5)
    state = _enter_mission(engine)
    player = engine.player
    entities_before = list(engine.game_map.entities)

    engine_to_dict(engine)

    assert engine.current_state is state
    assert engine.player is player
    assert engine.game_map.entities == entities_before


# ── 9. drifting home with the Dreadnought core wins ───────────────────────────


def _adrift_next_to_home(monkeypatch) -> tuple[Engine, StrategicState, str]:
    engine, strategic = _new_game(7)
    galaxy = engine.galaxy
    home = galaxy.home_system
    neighbour = next(iter(galaxy.systems[home].connections))
    galaxy.current_system = neighbour
    galaxy.arrive_at(neighbour)
    engine.ship.fuel = 0
    monkeypatch.setattr(strategic, "_drift_destination", lambda: home)
    # Every random pick takes the last option: the jettisoned item is the last cargo entry.
    monkeypatch.setattr("ui.strategic_state.random.choice", lambda seq: seq[-1])
    return engine, strategic, home


def _core() -> Entity:
    return Entity(name="Dreadnought Core", blocks_movement=False, item={"type": "dreadnought_core", "value": 99})


def test_drifting_home_with_the_core_is_a_victory(monkeypatch):
    engine, strategic, home = _adrift_next_to_home(monkeypatch)
    engine.ship.cargo = [_core(), make_heal_item()]

    strategic._drift(engine)

    assert engine.galaxy.current_system == home
    assert isinstance(engine.current_state, GameOverState)
    assert engine.current_state.victory is True


def test_drifting_home_without_the_core_is_not_a_victory(monkeypatch):
    engine, strategic, home = _adrift_next_to_home(monkeypatch)
    engine.ship.cargo = [make_heal_item(), make_heal_item()]

    strategic._drift(engine)

    assert engine.galaxy.current_system == home
    assert engine.current_state is strategic


# ── 10. ranged enemies without a clear shot ───────────────────────────────────


def _glass_arena(gap_at: int | None) -> tuple[Engine, Entity, Entity]:
    """Player and a blaster-armed enemy either side of a window wall; *gap_at* opens a way round."""
    game_map = GameMap(12, 7)
    for x in range(1, 11):
        for y in range(1, 6):
            game_map.tiles[x, y] = tile_types.floor
    for y in range(1, 6):
        if y != gap_at:
            game_map.tiles[6, y] = tile_types.structure_window
    engine = Engine()
    player = Entity(x=3, y=3, char="@", name="Player", fighter=Fighter(10, 10, 0, 1))
    enemy = Entity(x=8, y=3, char="p", name="Pirate", fighter=Fighter(5, 5, 1, 3), ai=CreatureAI())
    enemy.ai_config = {"vision_radius": 8, "aggro_distance": 8, "memory_turns": 15, "move_speed": 4}
    enemy.ai_state = "hunting"
    enemy.inventory = [make_weapon(ammo=20, max_ammo=20)]
    game_map.entities += [player, enemy]
    engine.game_map = game_map
    engine.player = player
    game_map.update_fov(player.x, player.y)
    return engine, player, enemy


def _run_enemy(engine: Engine, enemy: Entity, turns: int) -> None:
    for _ in range(turns):
        engine.game_map.clear_fov_cache()
        enemy.ai.perform(enemy, engine)


def test_enemy_blocked_shot_does_not_log_player_warnings():
    engine, player, enemy = _glass_arena(gap_at=None)

    consumed = RangedAction(player).perform(engine, enemy)

    assert consumed == 0
    assert _messages(engine) == []


def test_player_blocked_shot_still_warns():
    engine, player, enemy = _glass_arena(gap_at=None)
    player.inventory = [make_weapon()]

    consumed = RangedAction(enemy).perform(engine, player)

    assert consumed == 0
    assert _messages(engine) == ["No clear shot — path blocked."]


def test_ranged_enemy_behind_glass_walks_round_instead_of_freezing():
    engine, player, enemy = _glass_arena(gap_at=5)

    _run_enemy(engine, enemy, 8)

    assert enemy.inventory[0].item["ammo"] < 20
    assert player.fighter.hp < 10
    assert "No clear shot — path blocked." not in _messages(engine)


def test_ranged_enemy_sealed_behind_glass_counts_as_stuck():
    engine, _, enemy = _glass_arena(gap_at=None)

    _run_enemy(engine, enemy, 5)

    # It closes on the glass, then has nowhere to go: that must register as
    # stuck so the hunt can time out, and must not fill the player's log.
    assert (enemy.x, enemy.y) == (7, 3)
    assert enemy.ai_stuck_turns > 0
    assert enemy.inventory[0].item["ammo"] == 20
    assert _messages(engine) == []


def test_ranged_enemy_with_a_clear_shot_still_fires():
    engine, player, enemy = _glass_arena(gap_at=3)

    _run_enemy(engine, enemy, 1)

    assert enemy.inventory[0].item["ammo"] == 19
    assert player.fighter.hp < 10


# ── 11. over-long passwords are rejected cleanly ──────────────────────────────


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    asyncio.run(db.init_db())
    gm._sessions.clear()

    from web.auth import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    gm._sessions.clear()


def _register(client, username: str, password: str):
    return client.post("/api/register", json={"username": username, "password": password, "confirm": password})


def test_register_rejects_password_over_72_bytes(auth_client):
    response = _register(auth_client, "longpw_user", "p" * 73)

    assert response.status_code == 400
    assert "72" in response.json()["detail"]


def test_register_counts_bytes_not_characters(auth_client):
    response = _register(auth_client, "emoji_user", "é" * 40)  # 40 characters, 80 bytes

    assert response.status_code == 400


def test_register_accepts_password_of_exactly_72_bytes(auth_client):
    password = "p" * 72

    assert _register(auth_client, "edge_user", password).status_code == 201
    login = auth_client.post("/api/login", json={"username": "edge_user", "password": password})
    assert login.status_code == 200


def test_login_with_over_long_password_is_a_plain_401(auth_client):
    _register(auth_client, "normal_user", "q" * 12)

    for username in ("normal_user", "no_such_user"):
        response = auth_client.post("/api/login", json={"username": username, "password": "z" * 80})
        assert response.status_code == 401


def test_login_does_not_accept_a_72_byte_prefix_match(auth_client):
    password = "p" * 72
    _register(auth_client, "prefix_user", password)

    response = auth_client.post("/api/login", json={"username": "prefix_user", "password": password + "extra"})

    assert response.status_code == 401


# ── 12. venting your own ship is a real vacuum ────────────────────────────────


def _ship_with_suit() -> tuple[Engine, TacticalState]:
    engine, _ = _new_game(1)
    engine.suit = EVA_SUIT.copy()
    return engine, _enter_ship(engine)


def test_pressurised_ship_costs_no_oxygen():
    engine, state = _ship_with_suit()
    oxygen = engine.suit.current_pools["vacuum"]

    for _ in range(12):
        state._after_player_turn(engine)

    assert engine.suit.current_pools["vacuum"] == oxygen
    assert engine.player.fighter.hp == 10
    assert engine.game_map.get_hazards_at(engine.player.x, engine.player.y) == set()


def _vent_and_stand_in_airlock(engine: Engine) -> None:
    """Open one airlock to space before any hazard baseline exists, and put the player in its chamber."""
    game_map = engine.game_map
    airlock = game_map.airlocks[0]
    ix, iy = airlock["interior_door"]
    dx, dy = airlock["direction"]
    game_map.tiles[ix, iy] = tile_types.door_open
    game_map.tiles[airlock["exterior_door"]] = tile_types.airlock_ext_open
    game_map.invalidate_hazards()
    engine.player.x, engine.player.y = ix + dx, iy + dy
    game_map.invalidate_entity_index()


def test_vented_ship_drains_suit_oxygen():
    engine, state = _ship_with_suit()
    _vent_and_stand_in_airlock(engine)
    oxygen = engine.suit.current_pools["vacuum"]

    for _ in range(12):
        state._after_player_turn(engine)

    assert engine.player.drifting is False
    assert engine.suit.current_pools["vacuum"] == oxygen - 3


def test_vented_ship_hurts_once_oxygen_runs_out():
    engine, state = _ship_with_suit()
    _vent_and_stand_in_airlock(engine)
    engine.suit.current_pools["vacuum"] = 0

    for _ in range(3):
        state._after_player_turn(engine)

    assert engine.player.fighter.hp == 7


def test_exploring_the_ship_without_a_suit_issues_one():
    engine, _ = _new_game(1)
    assert engine.suit is None

    _enter_ship(engine)

    assert engine.suit is not None
    assert engine.suit.has_protection("vacuum")


# ── 13. starfield seeds are stable across processes ───────────────────────────


def _stable_seed_in_subprocess(hash_seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    code = "from game.helpers import stable_seed; print(stable_seed('Groombridge'))"
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_stable_seed_is_the_same_in_every_process():
    assert _stable_seed_in_subprocess("1") == _stable_seed_in_subprocess("2")


def test_stable_seed_is_a_32_bit_value_that_differs_by_name():
    from game.helpers import stable_seed

    assert stable_seed("Groombridge") == zlib.crc32(b"Groombridge")
    assert 0 <= stable_seed("Groombridge") <= 0xFFFFFFFF
    assert stable_seed("Groombridge") != stable_seed("Vega")


def test_mission_starfield_uses_the_stable_seed():
    from game.helpers import stable_seed

    engine, _ = _new_game()
    state = _enter_mission(engine)

    assert engine.game_map.space_seed == stable_seed(state.location.system_name)


def test_strategic_viewport_uses_the_stable_seed(monkeypatch):
    from game.helpers import stable_seed

    engine, strategic = _new_game()
    seeds: list[int] = []
    monkeypatch.setattr(
        "ui.viewport_renderer.render_viewport",
        lambda console, x, y, w, h, star_type, system_seed, **kwargs: seeds.append(system_seed),
    )

    strategic.on_render(_console(), engine)

    assert seeds == [stable_seed(engine.galaxy.current_system)]
