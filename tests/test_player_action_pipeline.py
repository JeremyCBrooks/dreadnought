"""Every input mode resolves a consumed action through the same pipeline."""

import tcod.event

from game.entity import Entity, Fighter
from tests.conftest import (
    FakeEvent,
    enter_mission,
    free_step_from,
    key_for,
    make_heal_item,
    make_scanner,
    make_weapon,
    new_game,
)

K = tcod.event.KeySym


def _lethal_crate(x: int, y: int) -> Entity:
    hazard = {"type": "explosive", "damage": 99, "equipment_damage": False, "dot": 0, "duration": 0}
    return Entity(
        x=x,
        y=y,
        char="=",
        name="Crate",
        blocks_movement=False,
        interactable={"kind": "crate", "hazard": hazard, "loot": None},
    )


def _mission_off_the_exit():
    engine, _ = new_game()
    state = enter_mission(engine)
    dx, dy = free_step_from(engine, engine.player.x, engine.player.y)
    state.ev_key(engine, FakeEvent(key_for((dx, dy))))
    assert engine.current_state is state
    return engine, state


def test_hazard_death_through_the_direction_prompt_is_killed_in_action():
    engine, state = _mission_off_the_exit()
    dx, dy = free_step_from(engine, engine.player.x, engine.player.y)
    engine.game_map.entities.append(_lethal_crate(engine.player.x + dx, engine.player.y + dy))
    engine.game_map.invalidate_entity_index()
    turn_before = engine.turn_counter
    state._interact_pending = True

    state.ev_key(engine, FakeEvent(key_for((dx, dy))))

    assert state._death_cause == "Killed in action."
    assert engine.turn_counter == turn_before


def test_hazard_death_through_the_single_target_shortcut_matches():
    engine, state = _mission_off_the_exit()
    dx, dy = free_step_from(engine, engine.player.x, engine.player.y)
    engine.game_map.entities.append(_lethal_crate(engine.player.x + dx, engine.player.y + dy))
    engine.game_map.invalidate_entity_index()
    assert len(state._adjacent_interact_dirs(engine)) == 1

    state.ev_key(engine, FakeEvent(K.E))

    assert state._death_cause == "Killed in action."


def test_scan_chosen_from_the_scanner_prompt_costs_one_turn():
    engine, _ = new_game()
    engine.mission_loadout = [make_scanner(name="A"), make_scanner(name="B")]
    state = enter_mission(engine)
    # Auto-equip only takes the first scanner; the prompt needs both equipped.
    engine.player.loadout.equip(engine.player.inventory[1])
    state.ev_key(engine, FakeEvent(K.S))
    assert state._scan_pending is not None
    turn_before = engine.turn_counter

    state.ev_key(engine, FakeEvent(K.N1))

    assert engine.turn_counter == turn_before + 1
    assert engine.current_state is state


def test_firing_costs_one_turn_and_clears_the_targeting_cursor():
    engine, state = _mission_off_the_exit()
    engine.player.inventory.append(make_weapon())
    engine.player.loadout.equip(engine.player.inventory[-1])
    dx, dy = free_step_from(engine, engine.player.x, engine.player.y)
    target = Entity(x=engine.player.x + dx, y=engine.player.y + dy, char="r", name="Rat")
    target.fighter = Fighter(hp=50, max_hp=50, defense=0, power=0)
    engine.game_map.entities.append(target)
    engine.game_map.invalidate_entity_index()
    state._ranged_cursor = (target.x, target.y)
    turn_before = engine.turn_counter

    state.ev_key(engine, FakeEvent(K.RETURN))

    assert engine.turn_counter == turn_before + 1
    assert state._ranged_cursor is None
    assert target.fighter.hp == 47


def test_an_action_that_achieves_nothing_costs_no_turn():
    engine, state = _mission_off_the_exit()
    assert engine.game_map.get_items_at(engine.player.x, engine.player.y) == []
    turn_before = engine.turn_counter

    state.ev_key(engine, FakeEvent(K.G))

    assert engine.turn_counter == turn_before
    assert engine.message_log.messages[-1][0] == "Nothing to pick up."


def test_ground_text_refreshes_when_the_world_turn_moves_the_player():
    engine, state = _mission_off_the_exit()
    player = engine.player
    dx, dy = free_step_from(engine, player.x, player.y)
    medkit = make_heal_item(name="Medkit")
    medkit.x, medkit.y = player.x + dx, player.y + dy
    engine.game_map.entities.append(medkit)
    engine.game_map.invalidate_entity_index()
    # Waiting does not move the player; the decompression pull in the world turn does.
    engine.game_map.pull_directions = {(player.x, player.y): (dx, dy)}
    player.decompression_moves = 1

    state.ev_key(engine, FakeEvent(K.PERIOD))

    assert (player.x, player.y) == (medkit.x, medkit.y)
    assert any(text == "You see Medkit (+) here." for text, _ in state._ground_lines)
