"""Tests for the quit confirmation flow."""
import pytest
from types import SimpleNamespace

from ui.confirm_quit_state import ConfirmQuitState
from tests.conftest import make_engine


def _key_event(sym, mod=0):
    return SimpleNamespace(sym=sym, mod=mod)


class TestConfirmQuitState:
    def test_y_raises_system_exit(self):
        import tcod.event
        engine = make_engine()
        state = ConfirmQuitState()
        engine.push_state(state)
        with pytest.raises(SystemExit):
            state.ev_keydown(engine, _key_event(tcod.event.KeySym.y))

    def test_n_pops_state(self):
        import tcod.event
        engine = make_engine()
        engine.push_state(ConfirmQuitState())
        state = engine.current_state
        state.ev_keydown(engine, _key_event(tcod.event.KeySym.n))
        assert not isinstance(engine.current_state, ConfirmQuitState)

    def test_escape_pops_state(self):
        import tcod.event
        engine = make_engine()
        engine.push_state(ConfirmQuitState())
        state = engine.current_state
        state.ev_keydown(engine, _key_event(tcod.event.KeySym.ESCAPE))
        assert not isinstance(engine.current_state, ConfirmQuitState)

    def test_other_keys_consumed(self):
        import tcod.event
        engine = make_engine()
        state = ConfirmQuitState()
        engine.push_state(state)
        result = state.ev_keydown(engine, _key_event(tcod.event.KeySym.a))
        assert result is True
        assert isinstance(engine.current_state, ConfirmQuitState)


class TestTacticalQuitBinding:
    def test_shift_q_pushes_confirm_quit(self):
        import tcod.event
        from ui.tactical_state import TacticalState

        engine = make_engine()
        tac = TacticalState()
        engine.push_state(tac)
        # Manually set up what on_enter would provide
        tac._layout = SimpleNamespace(
            viewport_w=60, viewport_h=42, stats_x=60, stats_w=20,
            log_y=42, log_h=8, map_w=60, map_h=42,
        )
        engine.player.drifting = False

        # Shift+Q should open quit confirmation
        tac.ev_keydown(engine, _key_event(tcod.event.KeySym.q, tcod.event.Modifier.LSHIFT))
        assert isinstance(engine.current_state, ConfirmQuitState)

    def test_lowercase_q_does_not_push_confirm_quit(self):
        import tcod.event
        from ui.tactical_state import TacticalState

        engine = make_engine()
        tac = TacticalState()
        engine.push_state(tac)
        tac._layout = SimpleNamespace(
            viewport_w=60, viewport_h=42, stats_x=60, stats_w=20,
            log_y=42, log_h=8, map_w=60, map_h=42,
        )
        engine.player.drifting = False

        tac.ev_keydown(engine, _key_event(tcod.event.KeySym.q, mod=0))
        assert not isinstance(engine.current_state, ConfirmQuitState)
