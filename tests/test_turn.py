"""World turn resolution, independent of any UI state."""

from game.turn import advance_turn
from tests.conftest import make_creature, make_engine
from world import tile_types


def test_a_survivable_turn_returns_none_and_ticks_the_counter():
    engine = make_engine()
    engine.game_map.entities.append(make_creature(x=6, y=5, power=3, ai_state="hunting"))

    assert advance_turn(engine) is None
    assert engine.turn_counter == 1
    assert engine.player.fighter.hp == 7


def test_death_by_enemy_reports_overwhelmed():
    engine = make_engine()
    engine.game_map.entities.append(make_creature(x=6, y=5, power=50, ai_state="hunting"))

    assert advance_turn(engine) == "Overwhelmed by hostiles."
    assert engine.message_log.messages[-1][0] == "You died."


def test_drifting_off_the_map_is_lost_to_the_void():
    engine = make_engine()
    engine.game_map.tiles[:] = tile_types.space
    engine.player.x, engine.player.y = 9, 5
    engine.player.drifting = True
    engine.player.drift_direction = (1, 0)

    assert advance_turn(engine) == "Lost to the void."
    assert engine.player.fighter.hp == 0


def test_drifting_into_a_hull_is_fatal():
    engine = make_engine()
    engine.game_map.tiles[5, 5] = tile_types.space
    engine.player.drifting = True
    engine.player.drift_direction = (1, 0)

    assert advance_turn(engine) == "Slammed into the hull."


def test_active_dot_effect_death_reports_the_environment_before_enemies_act():
    engine = make_engine()
    engine.active_effects.append({"type": "radiation", "dot": 99, "remaining": 2})
    enemy = make_creature(x=8, y=8, ai_state="wandering")
    engine.game_map.entities.append(enemy)

    assert advance_turn(engine) == "Succumbed to the environment."
    assert (enemy.x, enemy.y) == (8, 8)
