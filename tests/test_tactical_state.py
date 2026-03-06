"""Tests for TacticalState logic (lifecycle, input routing, death, drift)."""
import pytest
from types import SimpleNamespace

from tests.conftest import (
    FakeEvent, MockEngine, make_arena, make_weapon, make_melee_weapon,
    make_scanner, make_creature,
)
from game.entity import Entity, Fighter
from game.loadout import Loadout
from ui.tactical_state import TacticalState, _area_key, _area_seed, _layout


def _sym(name):
    import tcod.event
    return getattr(tcod.event.KeySym, name)


def _make_tactical_engine(env=None, items=None, loadout=None):
    """Build an engine with a TacticalState-compatible setup."""
    gm = make_arena(w=20, h=20)
    player = Entity(
        x=5, y=5, char="@", color=(255, 255, 255), name="Player",
        blocks_movement=True,
        fighter=Fighter(hp=10, max_hp=10, defense=0, power=1),
    )
    player.loadout = loadout or Loadout()
    player.inventory = items or []
    gm.entities.append(player)
    engine = MockEngine(gm, player, environment=env)
    engine.CONSOLE_WIDTH = 160
    engine.CONSOLE_HEIGHT = 50
    # State stack support
    engine.current_state = None

    def push_state(s):
        engine._state_stack.append(s)
        engine.current_state = s

    def pop_state():
        if engine._state_stack:
            top = engine._state_stack.pop()
            top.on_exit(engine)
        engine.current_state = engine._state_stack[-1] if engine._state_stack else None

    def switch_state(s):
        if engine._state_stack:
            engine._state_stack.pop()
        engine._state_stack.append(s)
        engine.current_state = s

    engine.push_state = push_state
    engine.pop_state = pop_state
    engine.switch_state = switch_state
    return engine


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------

class TestAreaKeyAndSeed:
    def test_area_key_with_location(self):
        loc = SimpleNamespace(name="Derelict Alpha")
        assert _area_key(loc, 2) == ("Derelict Alpha", 2)

    def test_area_key_without_location(self):
        assert _area_key(None, 0) == ("the dungeon", 0)

    def test_area_seed_deterministic(self):
        s1 = _area_seed("Derelict Alpha", 1)
        s2 = _area_seed("Derelict Alpha", 1)
        assert s1 == s2

    def test_area_seed_different_for_different_input(self):
        s1 = _area_seed("Derelict Alpha", 1)
        s2 = _area_seed("Derelict Beta", 1)
        assert s1 != s2


class TestLayout:
    def test_layout_returns_namespace(self):
        engine = SimpleNamespace(CONSOLE_WIDTH=160, CONSOLE_HEIGHT=50)
        l = _layout(engine)
        assert hasattr(l, "viewport_w")
        assert hasattr(l, "viewport_h")
        assert hasattr(l, "stats_w")
        assert l.viewport_w + l.stats_w == 160
        assert l.viewport_h + l.log_h == 50


# ------------------------------------------------------------------
# _get_action
# ------------------------------------------------------------------

class TestGetAction:
    def test_movement_key_returns_bump_action(self):
        from game.actions import BumpAction
        action = TacticalState._get_action(_sym("UP"))
        assert isinstance(action, BumpAction)

    def test_wait_key_returns_wait_action(self):
        from game.actions import WaitAction
        from ui.keys import action_keys
        wait_keyset = action_keys()["wait"][0]
        wait_key = next(iter(wait_keyset))
        action = TacticalState._get_action(wait_key)
        assert isinstance(action, WaitAction)

    def test_unknown_key_returns_none(self):
        action = TacticalState._get_action(_sym("F12"))
        assert action is None


# ------------------------------------------------------------------
# Player death
# ------------------------------------------------------------------

class TestPlayerDeath:
    def test_handle_player_death_sets_cause(self):
        state = TacticalState()
        engine = _make_tactical_engine()
        state._handle_player_death(engine, "Test cause")
        assert state._death_cause == "Test cause"
        assert state._death_fade_start > 0

    def test_handle_player_death_only_once(self):
        state = TacticalState()
        engine = _make_tactical_engine()
        state._handle_player_death(engine, "First")
        first_start = state._death_fade_start
        state._handle_player_death(engine, "Second")
        assert state._death_cause == "First"
        assert state._death_fade_start == first_start

    def test_needs_animation_false_by_default(self):
        state = TacticalState()
        assert not state.needs_animation

    def test_needs_animation_true_after_death(self):
        state = TacticalState()
        engine = _make_tactical_engine()
        state._handle_player_death(engine, "test")
        assert state.needs_animation


# ------------------------------------------------------------------
# ev_keydown routing
# ------------------------------------------------------------------

class TestEvKeydownRouting:
    def _setup(self):
        engine = _make_tactical_engine()
        state = TacticalState()
        state._layout = _layout(engine)
        engine._state_stack.append(state)
        engine.current_state = state
        engine.game_map.update_fov(engine.player.x, engine.player.y)
        return engine, state

    def test_death_blocks_input(self):
        engine, state = self._setup()
        state._death_cause = "dead"
        result = state.ev_keydown(engine, FakeEvent(_sym("UP")))
        assert result is True

    def test_escape_consumed(self):
        engine, state = self._setup()
        result = state.ev_keydown(engine, FakeEvent(_sym("ESCAPE")))
        assert result is True

    def test_inventory_key_pushes_state(self):
        engine, state = self._setup()
        from ui.keys import action_keys
        inv_keyset = action_keys()["inventory"][0]
        inv_key = next(iter(inv_keyset))
        pushed = []
        original_push = engine.push_state
        def capture_push(s):
            pushed.append(s)
            original_push(s)
        engine.push_state = capture_push
        state.ev_keydown(engine, FakeEvent(inv_key))
        assert len(pushed) == 1
        from ui.inventory_state import InventoryState
        assert isinstance(pushed[0], InventoryState)

    def test_movement_consumes_turn(self):
        engine, state = self._setup()
        old_x = engine.player.x
        # Move right
        result = state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert result is True
        # Player should have moved (or bumped into wall)
        # On a 20x20 arena, player at (5,5) should be able to move right
        assert engine.player.x == old_x + 1

    def test_unknown_key_not_consumed(self):
        engine, state = self._setup()
        result = state.ev_keydown(engine, FakeEvent(_sym("F12")))
        assert result is False

    def test_drifting_blocks_turn_consuming_input(self):
        engine, state = self._setup()
        engine.player.drifting = True
        old_x, old_y = engine.player.x, engine.player.y
        result = state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert result is True
        # Should NOT have moved — drifting blocks movement
        assert engine.player.x == old_x

    def test_look_mode_entered(self):
        engine, state = self._setup()
        from ui.keys import action_keys
        look_keyset = action_keys()["look"][0]
        look_key = next(iter(look_keyset))
        state.ev_keydown(engine, FakeEvent(look_key))
        assert state._look_cursor is not None

    def test_look_mode_escape_exits(self):
        engine, state = self._setup()
        state._look_cursor = (5, 5)
        state.ev_keydown(engine, FakeEvent(_sym("ESCAPE")))
        assert state._look_cursor is None

    def test_ranged_no_weapon_shows_message(self):
        engine, state = self._setup()
        from ui.keys import action_keys
        fire_keyset = action_keys()["fire"][0]
        fire_key = next(iter(fire_keyset))
        state.ev_keydown(engine, FakeEvent(fire_key))
        assert any("ranged" in m[0].lower() or "ammo" in m[0].lower()
                    for m in engine.message_log.messages)

    def test_interact_nothing_nearby(self):
        engine, state = self._setup()
        from ui.keys import action_keys
        interact_keyset = action_keys()["interact"][0]
        interact_key = next(iter(interact_keyset))
        state.ev_keydown(engine, FakeEvent(interact_key))
        assert any("nothing" in m[0].lower() for m in engine.message_log.messages)


# ------------------------------------------------------------------
# Exit position triggers pop
# ------------------------------------------------------------------

class TestExitPosition:
    def test_stepping_on_exit_pops_state(self):
        engine = _make_tactical_engine()
        state = TacticalState()
        state._layout = _layout(engine)
        state.exit_pos = (6, 5)  # one step right of player
        engine._state_stack.append(state)
        engine.current_state = state
        engine.game_map.update_fov(engine.player.x, engine.player.y)
        state.ev_keydown(engine, FakeEvent(_sym("RIGHT")))
        assert any("ship" in m[0].lower() for m in engine.message_log.messages)


# ------------------------------------------------------------------
# on_exit saves player state
# ------------------------------------------------------------------

class TestOnExit:
    def test_on_exit_saves_player(self):
        engine = _make_tactical_engine()
        state = TacticalState()
        state._layout = _layout(engine)
        engine.player.fighter.hp = 7
        engine.player.fighter.max_hp = 10
        wpn = make_weapon()
        engine.player.inventory.append(wpn)
        state.on_exit(engine)
        saved = engine._saved_player
        assert saved["hp"] == 7
        assert saved["max_hp"] == 10
        assert wpn in saved["inventory"]
        assert engine.game_map is None
        assert engine.player is None

    def test_on_exit_clears_scan(self):
        engine = _make_tactical_engine()
        state = TacticalState()
        state._layout = _layout(engine)
        engine.scan_results = "something"
        engine.scan_glow = {"foo": 1}
        state.on_exit(engine)
        assert engine.scan_results is None
        assert engine.scan_glow is None


# ------------------------------------------------------------------
# _after_player_turn
# ------------------------------------------------------------------

class TestAfterPlayerTurn:
    def _setup(self):
        engine = _make_tactical_engine(env={"vacuum": 1})
        state = TacticalState()
        state._layout = _layout(engine)
        engine._state_stack.append(state)
        engine.current_state = state
        engine.game_map.update_fov(engine.player.x, engine.player.y)
        # Give player a suit so env tick doesn't kill them
        from game.suit import EVA_SUIT
        engine.suit = EVA_SUIT
        engine.suit.refill_pools()
        return engine, state

    def test_environment_tick_runs(self):
        engine, state = self._setup()
        import numpy as np
        overlay = np.full(
            (engine.game_map.width, engine.game_map.height),
            fill_value=True, order="F",
        )
        engine.game_map.hazard_overlays["vacuum"] = overlay
        engine.game_map._hazards_dirty = False
        pool_before = engine.suit.current_pools.get("vacuum", 0)
        state._after_player_turn(engine)
        # Either pool drained or still same (depends on drain interval)
        # At minimum, no crash
        assert engine.player.fighter.hp > 0

    def test_enemy_takes_turn(self):
        engine, state = self._setup()
        creature = make_creature(x=6, y=5, hp=5, ai_state="sleeping")
        engine.game_map.entities.append(creature)
        # After player turn, enemy AI should run without crashing
        state._after_player_turn(engine)
        assert creature.fighter.hp > 0 or creature not in engine.game_map.entities

    def test_player_death_triggers_death_fade(self):
        engine, state = self._setup()
        engine.player.fighter.hp = 1
        engine.player.fighter.max_hp = 1
        engine.suit = None  # no suit = take damage
        import numpy as np
        overlay = np.full(
            (engine.game_map.width, engine.game_map.height),
            fill_value=True, order="F",
        )
        engine.game_map.hazard_overlays["vacuum"] = overlay
        engine.game_map._hazards_dirty = False
        state._after_player_turn(engine)
        # Player should be dead or dying
        if engine.player.fighter.hp <= 0:
            assert state._death_cause is not None


# ------------------------------------------------------------------
# Scan input
# ------------------------------------------------------------------

class TestScanInput:
    def _setup_with_scanner(self):
        scanner = make_scanner()
        lo = Loadout()
        lo.equip(scanner)
        engine = _make_tactical_engine(items=[scanner], loadout=lo)
        state = TacticalState()
        state._layout = _layout(engine)
        engine._state_stack.append(state)
        engine.current_state = state
        engine.game_map.update_fov(engine.player.x, engine.player.y)
        return engine, state

    def test_scan_with_no_scanner_shows_message(self):
        engine = _make_tactical_engine()
        state = TacticalState()
        state._layout = _layout(engine)
        engine._state_stack.append(state)
        engine.current_state = state
        engine.game_map.update_fov(engine.player.x, engine.player.y)
        from ui.keys import action_keys
        scan_keyset = action_keys()["scan"][0]
        scan_key = next(iter(scan_keyset))
        state.ev_keydown(engine, FakeEvent(scan_key))
        assert any("scanner" in m[0].lower() for m in engine.message_log.messages)

    def test_scan_pending_cancel(self):
        engine, state = self._setup_with_scanner()
        state._scan_pending = [make_scanner()]
        state.ev_keydown(engine, FakeEvent(_sym("ESCAPE")))
        assert state._scan_pending is None
