"""Pytest fixtures shared across all test modules."""
import pytest

from engine.game_state import Engine
from engine.message_log import MessageLog
from world.game_map import GameMap
from world import tile_types
from game.entity import Entity, Fighter
from game.suit import Suit


@pytest.fixture(autouse=True)
def _reset_debug_flags():
    """Reset all debug flags before each test so dev toggles don't break the suite."""
    import debug
    debug.GOD_MODE = False
    debug.DISABLE_OXYGEN = False
    debug.DISABLE_HAZARDS = False
    debug.DISABLE_ENEMY_AI = False
    debug.ONE_HIT_KILL = False


@pytest.fixture
def engine():
    """Engine instance for testing (no tcod window)."""
    return Engine()


def make_arena(w=10, h=10):
    """Create a GameMap with floor tiles surrounded by walls."""
    gm = GameMap(w, h)
    for x in range(1, w - 1):
        for y in range(1, h - 1):
            gm.tiles[x, y] = tile_types.floor
    return gm


def make_engine(env=None, suit=None):
    """Create an Engine with a 10x10 arena, player at (5,5), optional env/suit."""
    engine = Engine()
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine.game_map = gm
    engine.player = player
    engine.environment = env
    engine.suit = suit
    return engine


class MockEngine:
    """Minimal engine stand-in for tests that don't need the full Engine."""

    def __init__(self, game_map, player, suit=None, environment=None):
        self.game_map = game_map
        self.player = player
        self.message_log = MessageLog()
        self.suit = suit
        self.environment = environment
        self.active_effects = []
