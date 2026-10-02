"""End-to-end flows: a real Engine driven through real states, the way a player would."""

from __future__ import annotations

import json
from pathlib import Path

import tcod.console
import tcod.event

from engine.game_state import Engine
from game.entity import Entity
from tests.conftest import FakeEvent, enter_mission, free_step_from, key_for, new_game
from ui.game_over_state import GameOverState
from ui.strategic_state import StrategicState
from ui.title_state import TitleState
from web.save_load import dict_to_engine, engine_to_dict

K = tcod.event.KeySym
SAVE_FIXTURE = Path(__file__).parent / "fixtures" / "save_before_refactor.json"


def _leave_by_the_exit(engine, state) -> None:
    ex, ey = state.exit_pos
    dx, dy = free_step_from(engine, ex, ey)
    state.ev_key(engine, FakeEvent(key_for((dx, dy))))
    state.ev_key(engine, FakeEvent(key_for((-dx, -dy))))


def _reload(engine: Engine) -> Engine:
    loaded = Engine()
    dict_to_engine(json.loads(json.dumps(engine_to_dict(engine))), loaded)
    return loaded


def test_mission_round_trip_converts_salvage_and_keeps_the_rest():
    engine, strategic = new_game()
    state = enter_mission(engine)
    core = Entity(name="Reactor Core", blocks_movement=False, item={"type": "reactor_core", "value": 5})
    medkit = Entity(name="Med-kit", blocks_movement=False, item={"type": "heal", "value": 5})
    engine.player.inventory += [core, medkit]
    fuel_before = engine.ship.fuel

    _leave_by_the_exit(engine, state)

    assert engine.current_state is strategic
    assert engine.ship.fuel == min(engine.ship.max_fuel, fuel_before + 5)
    assert engine._saved_player["inventory"] == [medkit]
    assert engine.game_map is None and engine.player is None


def test_leaving_and_reentering_a_mission_keeps_the_player_record():
    engine, _ = new_game()
    state = enter_mission(engine)
    engine.player.fighter.hp = 6
    medkit = Entity(name="Med-kit", blocks_movement=False, item={"type": "heal", "value": 5})
    engine.player.inventory.append(medkit)
    _leave_by_the_exit(engine, state)

    enter_mission(engine)

    assert engine.player.fighter.hp == 6
    assert engine.player.inventory == [medkit]


def test_same_seed_and_same_keys_play_out_identically():
    def play() -> tuple[list, list[str], int]:
        engine, _ = new_game(seed=3)
        state = enter_mission(engine, "derelict")
        for _ in range(20):
            if engine.current_state is not state:
                break
            state.ev_key(engine, FakeEvent(K.PERIOD))
        creatures = sorted((e.name, e.x, e.y, e.fighter.hp) for e in engine.game_map.entities if e.fighter)
        return creatures, [text for text, _ in engine.message_log.messages], engine.turn_counter

    first, second = play(), play()

    assert first == second
    assert first[2] == 20


def test_strategic_travel_survives_a_save_and_reload():
    engine, strategic = new_game()
    strategic.focus = "navigation"
    direction, destination = next(iter(strategic._connection_by_direction().items()))
    strategic.ev_key(engine, FakeEvent(key_for(direction)))
    assert engine.galaxy.current_system == destination

    loaded = _reload(engine)

    assert isinstance(loaded.current_state, StrategicState)
    assert loaded.galaxy.current_system == destination
    assert loaded.ship.fuel == engine.ship.fuel
    assert set(loaded.galaxy.systems) == set(engine.galaxy.systems)


def test_death_runs_through_game_over_to_a_new_game():
    engine, _ = new_game()
    state = enter_mission(engine)
    engine.player.fighter.hp = 0
    state.ev_key(engine, FakeEvent(K.PERIOD))
    assert state._death_cause is not None

    state._death_fade_start -= 5
    state.on_render(tcod.console.Console(Engine.CONSOLE_WIDTH, Engine.CONSOLE_HEIGHT, order="F"), engine)
    assert isinstance(engine.current_state, GameOverState)

    engine.current_state._fade_start -= 5
    engine.current_state.ev_key(engine, FakeEvent(K.RETURN))
    assert isinstance(engine.current_state, TitleState)
    assert engine.galaxy is None

    engine.current_state.ev_key(engine, FakeEvent(K.RETURN))
    assert isinstance(engine.current_state, StrategicState)
    assert engine.galaxy is not None


def test_a_save_written_before_the_refactor_still_loads_and_plays():
    loaded = Engine()
    dict_to_engine(json.loads(SAVE_FIXTURE.read_text(encoding="utf-8")), loaded)

    assert isinstance(loaded.current_state, StrategicState)
    assert loaded.galaxy.current_system != loaded.galaxy.home_system
    assert loaded.ship.fuel == 3
    record = loaded._saved_player
    assert record["hp"] == 7
    assert [item.name for item in record["inventory"]] == ["Combat Knife", "Medkit"]

    enter_mission(loaded)

    assert loaded.player.fighter.hp == 7
    # Base power 1 plus the knife's 3: only true if the knife came back equipped.
    assert loaded.player.fighter.power == 4
