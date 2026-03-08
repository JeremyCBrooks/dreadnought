"""Tests for ranged targeting: auto-target closest, up/down cycling, no free cursor."""
import tcod.event
from types import SimpleNamespace

from game.ai import HostileAI
from game.entity import Entity, Fighter
from game.loadout import Loadout
from tests.conftest import make_engine
from ui.tactical_state import TacticalState


def _ranged_weapon(ammo=5, range_=5, value=3):
    return Entity(
        name="Blaster",
        item={
            "type": "weapon", "weapon_class": "ranged",
            "value": value, "range": range_, "ammo": ammo, "max_ammo": 20,
        },
    )


def _add_enemy(engine, x, y, name="Bot", hp=5):
    e = Entity(x=x, y=y, name=name, fighter=Fighter(hp, hp, 0, 0),
               blocks_movement=True, ai=HostileAI(), char="B", color=(255, 0, 0))
    engine.game_map.entities.append(e)
    engine.game_map.visible[x, y] = True
    return e


# --- Auto-target closest enemy on enter ---

def test_enter_ranged_targets_closest_enemy():
    """Pressing fire should auto-target the closest visible enemy."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    far = _add_enemy(engine, 8, 5, "Far")   # distance 3
    close = _add_enemy(engine, 6, 5, "Close")  # distance 1
    state = TacticalState()
    state._enter_ranged(engine)
    assert state._ranged_cursor == (close.x, close.y)


def test_enter_ranged_no_enemies_shows_message():
    """If no visible enemies, entering ranged mode should show a message and not activate cursor."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    state = TacticalState()
    state._enter_ranged(engine)
    # No enemies -> cursor should not activate
    assert state._ranged_cursor is None
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("no visible" in m.lower() or "no target" in m.lower() for m in msgs)


# --- Up/Down cycling ---

def test_up_down_cycles_enemies():
    """Up/Down keys should cycle through visible enemies sorted by distance."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    close = _add_enemy(engine, 6, 5, "Close")   # distance 1
    mid = _add_enemy(engine, 7, 5, "Mid")        # distance 2
    far = _add_enemy(engine, 8, 5, "Far")        # distance 3
    state = TacticalState()
    state._enter_ranged(engine)
    # Should start on closest
    assert state._ranged_cursor == (close.x, close.y)
    # Down -> next farther
    state._handle_ranged_input(engine, tcod.event.KeySym.DOWN)
    assert state._ranged_cursor == (mid.x, mid.y)
    # Down again -> farthest
    state._handle_ranged_input(engine, tcod.event.KeySym.DOWN)
    assert state._ranged_cursor == (far.x, far.y)
    # Down wraps to closest
    state._handle_ranged_input(engine, tcod.event.KeySym.DOWN)
    assert state._ranged_cursor == (close.x, close.y)


def test_up_cycles_reverse():
    """Up key should cycle in reverse order (toward closer enemies)."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    close = _add_enemy(engine, 6, 5, "Close")   # distance 1
    far = _add_enemy(engine, 8, 5, "Far")        # distance 3
    state = TacticalState()
    state._enter_ranged(engine)
    assert state._ranged_cursor == (close.x, close.y)
    # Up wraps to farthest
    state._handle_ranged_input(engine, tcod.event.KeySym.UP)
    assert state._ranged_cursor == (far.x, far.y)
    # Up again -> back to closest
    state._handle_ranged_input(engine, tcod.event.KeySym.UP)
    assert state._ranged_cursor == (close.x, close.y)


# --- Arrow keys no longer move cursor freely ---

def test_left_right_do_not_move_cursor():
    """Left/Right arrow keys should NOT move the cursor freely."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    enemy = _add_enemy(engine, 7, 5, "Bot")
    state = TacticalState()
    state._enter_ranged(engine)
    original = state._ranged_cursor
    state._handle_ranged_input(engine, tcod.event.KeySym.LEFT)
    assert state._ranged_cursor == original
    state._handle_ranged_input(engine, tcod.event.KeySym.RIGHT)
    assert state._ranged_cursor == original


# --- Confirm still fires ---

def test_confirm_fires_at_targeted_enemy():
    """Enter should fire at the currently targeted enemy."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    enemy = _add_enemy(engine, 7, 5, "Bot")
    state = TacticalState()
    state._enter_ranged(engine)
    state._handle_ranged_input(engine, tcod.event.KeySym.RETURN)
    assert enemy.fighter.hp < 5


# --- Escape cancels ---

def test_escape_cancels_targeting():
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    _add_enemy(engine, 7, 5, "Bot")
    state = TacticalState()
    state._enter_ranged(engine)
    assert state._ranged_cursor is not None
    state._handle_ranged_input(engine, tcod.event.KeySym.ESCAPE)
    assert state._ranged_cursor is None


# --- NEARBY list shows target marker ---

def _mock_console():
    calls = []

    class Console:
        def print(self, *, x, y, string, fg=(255, 255, 255)):
            calls.append({"x": x, "y": y, "string": string, "fg": fg})

    return Console(), calls


def _find_prints(calls, substring):
    return [c for c in calls if substring in c["string"]]


def test_nearby_marks_targeted_enemy():
    """The targeted enemy in the NEARBY list should be prefixed with '>' and white."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    enemy = _add_enemy(engine, 7, 5, "Bot")
    state = TacticalState()
    state._enter_ranged(engine)
    console, calls = _mock_console()
    layout = SimpleNamespace(stats_x=60, stats_w=20, viewport_h=50)
    state._render_stats(console, engine, layout)
    # Find the NEARBY entry for the targeted enemy
    bot_entries = _find_prints(calls, "Bot")
    targeted = [c for c in bot_entries if c["string"].startswith(">")]
    assert len(targeted) == 1
    assert targeted[0]["fg"] == (255, 255, 255)


def test_nearby_no_marker_when_not_targeting():
    """Without targeting, NEARBY entries should NOT have '>' prefix."""
    engine = make_engine()
    _add_enemy(engine, 7, 5, "Bot")
    state = TacticalState()
    console, calls = _mock_console()
    layout = SimpleNamespace(stats_x=60, stats_w=20, viewport_h=50)
    state._render_stats(console, engine, layout)
    bot_entries = _find_prints(calls, "Bot")
    targeted = [c for c in bot_entries if c["string"].startswith(">")]
    assert len(targeted) == 0


def test_targeting_keeps_underfoot_text():
    """Entering targeting should NOT change the UNDERFOOT ground text."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    _add_enemy(engine, 7, 5, "Bot")
    state = TacticalState()
    state.on_enter(engine)
    ground_before = list(state._ground_lines)
    state._enter_ranged(engine)
    assert state._ground_lines == ground_before
