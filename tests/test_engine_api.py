"""The engine and map expose what other modules need, so nothing reaches into privates."""

from engine.game_state import Engine, State
from tests.conftest import make_arena
from world import tile_types


class _Still(State):
    pass


class _Animated(State):
    needs_animation = True


def test_has_state_finds_a_buried_state_and_respects_subclassing():
    class _StillChild(_Still):
        pass

    engine = Engine()
    engine.push_state(_StillChild())
    engine.push_state(_Animated())

    assert engine.has_state(_Still) is True
    assert engine.has_state(_StillChild) is True
    engine.pop_state()
    engine.pop_state()
    assert engine.has_state(_Still) is False


def test_state_below_returns_the_state_under_a_given_one():
    engine = Engine()
    bottom, top = _Still(), _Animated()
    engine.push_state(bottom)
    engine.push_state(top)

    assert engine.state_below(top) is bottom
    assert engine.state_below(bottom) is None
    assert engine.state_below(_Still()) is None


def test_engine_animates_for_the_state_the_map_or_a_scan_glow():
    engine = Engine()
    assert engine.needs_animation() is False
    engine.push_state(_Still())
    assert engine.needs_animation() is False

    engine.scan_glow = {"cx": 0, "cy": 0, "radius": 1, "start_time": 0.0}
    assert engine.needs_animation() is True
    engine.scan_glow = None

    engine.game_map = make_arena()
    engine.game_map.has_space = True
    assert engine.needs_animation() is True
    engine.game_map = None

    engine.push_state(_Animated())
    assert engine.needs_animation() is True


def test_engine_animates_for_a_flickering_light_only():
    engine = Engine()
    engine.game_map = make_arena()
    engine.game_map.has_space = False
    engine.game_map.add_light_source(3, 3, radius=4, color=(255, 200, 100), flicker=False)
    assert engine.needs_animation() is False

    engine.game_map.add_light_source(5, 5, radius=4, color=(255, 200, 100), flicker=True)
    assert engine.needs_animation() is True


def test_map_fov_respects_walls_and_is_recomputed_after_the_cache_is_cleared():
    game_map = make_arena()
    assert game_map.fov_from(5, 5, 8)[2, 5]

    for y in range(1, 9):
        game_map.tiles[4, y] = tile_types.wall
    assert game_map.fov_from(5, 5, 8)[2, 5], "same turn: the cached view is reused"

    game_map.clear_fov_cache()
    assert not game_map.fov_from(5, 5, 8)[2, 5]
