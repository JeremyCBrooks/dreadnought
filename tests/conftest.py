"""Pytest fixtures shared across all test modules."""
import pytest

from engine.game_state import Engine
from engine.message_log import MessageLog
from world.game_map import GameMap
from world import tile_types
from game.entity import Entity, Fighter
from game.suit import Suit
from game.loadout import Loadout
from game.ai import CreatureAI


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
        self.area_cache = {}
        self._state_stack = []
        self._saved_player = None
        self.ship = None
        self.scan_results = None
        self.scan_glow = None
        self.mission_loadout = []


# ---- Shared helpers for common entity creation ----

def make_weapon(name="Laser Pistol", weapon_class="ranged", value=3,
                ammo=5, max_ammo=5, range_=5):
    """Create a weapon Entity."""
    return Entity(
        char=")", color=(255, 200, 100), name=name,
        blocks_movement=False,
        item={"type": "weapon", "weapon_class": weapon_class, "value": value,
              "ammo": ammo, "max_ammo": max_ammo, "range": range_},
    )


def make_melee_weapon(name="Combat Knife", value=3):
    """Create a melee weapon Entity."""
    return Entity(
        char=")", color=(200, 200, 200), name=name,
        blocks_movement=False,
        item={"type": "weapon", "weapon_class": "melee", "value": value},
    )


def make_scanner(name="Scanner", tier=1, scan_range=8):
    """Create a scanner Entity."""
    return Entity(
        char="~", color=(100, 200, 255), name=name,
        blocks_movement=False,
        item={"type": "scanner", "scanner_tier": tier, "range": scan_range,
              "value": tier},
    )


def make_heal_item(name="Medkit", value=5):
    """Create a heal consumable Entity."""
    return Entity(
        char="+", color=(0, 255, 0), name=name,
        blocks_movement=False,
        item={"type": "heal", "value": value},
    )


DEFAULT_AI_CONFIG = {
    "ai_initial_state": "wandering",
    "aggro_distance": 8,
    "sleep_aggro_distance": 3,
    "can_open_doors": False,
    "flee_threshold": 0.0,
    "memory_turns": 15,
    "vision_radius": 8,
    "move_speed": 4,
}


def make_creature(x=3, y=3, hp=5, power=1, defense=0, name="Drone",
                  ai_config=None, ai_state="wandering", organic=True):
    """Create an enemy Entity with CreatureAI."""
    cfg = dict(DEFAULT_AI_CONFIG)
    if ai_config:
        cfg.update(ai_config)
    e = Entity(
        x=x, y=y, char="d", color=(255, 100, 100), name=name,
        blocks_movement=True,
        fighter=Fighter(hp=hp, max_hp=hp, defense=defense, power=power),
        ai=CreatureAI(),
        organic=organic,
    )
    e.ai_config = cfg
    e.ai_state = ai_state
    return e


class FakeEvent:
    """Minimal tcod event stand-in for UI state tests."""
    def __init__(self, sym, mod=0):
        self.sym = sym
        self.mod = mod
