"""Tests for the quit confirmation flow."""

from types import SimpleNamespace

import pytest

from tests.conftest import make_engine
from ui.confirm_quit_state import ConfirmQuitState


def _key_event(sym, mod=0):
    return SimpleNamespace(sym=sym, mod=mod)


class TestConfirmQuitState:
    def test_y_raises_system_exit(self):
        import tcod.event

        engine = make_engine()
        state = ConfirmQuitState()
        engine.push_state(state)
        with pytest.raises(SystemExit):
            state.ev_key(engine, _key_event(tcod.event.KeySym.y))

    def test_n_pops_state(self):
        import tcod.event

        engine = make_engine()
        engine.push_state(ConfirmQuitState())
        state = engine.current_state
        state.ev_key(engine, _key_event(tcod.event.KeySym.n))
        assert not isinstance(engine.current_state, ConfirmQuitState)

    def test_escape_pops_state(self):
        import tcod.event

        engine = make_engine()
        engine.push_state(ConfirmQuitState())
        state = engine.current_state
        state.ev_key(engine, _key_event(tcod.event.KeySym.ESCAPE))
        assert not isinstance(engine.current_state, ConfirmQuitState)

    def test_other_keys_consumed(self):
        import tcod.event

        engine = make_engine()
        state = ConfirmQuitState()
        engine.push_state(state)
        result = state.ev_key(engine, _key_event(tcod.event.KeySym.a))
        assert result is True
        assert isinstance(engine.current_state, ConfirmQuitState)


class TestConfirmQuitAbandon:
    def test_y_with_abandon_switches_to_game_over(self):
        import tcod.event

        from ui.game_over_state import GameOverState

        engine = make_engine()
        state = ConfirmQuitState(abandon=True)
        engine.push_state(state)
        state.ev_key(engine, _key_event(tcod.event.KeySym.y))
        assert isinstance(engine.current_state, GameOverState)

    def test_abandon_game_over_shows_abandoned_message(self):
        import tcod.event

        from ui.game_over_state import GameOverState

        engine = make_engine()
        state = ConfirmQuitState(abandon=True)
        engine.push_state(state)
        state.ev_key(engine, _key_event(tcod.event.KeySym.y))
        go_state = engine.current_state
        assert isinstance(go_state, GameOverState)
        assert go_state.title == "MISSION ABANDONED"
        assert not go_state.victory

    def test_abandon_does_not_raise_system_exit(self):
        import tcod.event

        engine = make_engine()
        state = ConfirmQuitState(abandon=True)
        engine.push_state(state)
        # Should NOT raise SystemExit
        state.ev_key(engine, _key_event(tcod.event.KeySym.y))


class TestConfirmQuitDialogText:
    def test_default_dialog_text(self):
        state = ConfirmQuitState()
        assert state.title == "Quit game?"
        assert state.confirm_label == "[Y] Yes, exit"

    def test_abandon_dialog_text(self):
        state = ConfirmQuitState(abandon=True)
        assert state.title == "Abandon mission?"
        assert state.confirm_label == "[Y] Yes, abandon"


class TestTacticalQuitBinding:
    def test_shift_q_pushes_confirm_quit(self):
        import tcod.event

        from ui.tactical_state import TacticalState

        engine = make_engine()
        tac = TacticalState()
        engine.push_state(tac)
        # Manually set up what on_enter would provide
        tac._layout = SimpleNamespace(
            viewport_w=60,
            viewport_h=42,
            stats_x=60,
            stats_w=20,
            log_y=42,
            log_h=8,
            map_w=60,
            map_h=42,
        )
        engine.player.drifting = False

        # Shift+Q should open quit confirmation
        tac.ev_key(engine, _key_event(tcod.event.KeySym.q, tcod.event.Modifier.LSHIFT))
        assert isinstance(engine.current_state, ConfirmQuitState)

    def test_lowercase_q_does_not_push_confirm_quit(self):
        import tcod.event

        from ui.tactical_state import TacticalState

        engine = make_engine()
        tac = TacticalState()
        engine.push_state(tac)
        tac._layout = SimpleNamespace(
            viewport_w=60,
            viewport_h=42,
            stats_x=60,
            stats_w=20,
            log_y=42,
            log_h=8,
            map_w=60,
            map_h=42,
        )
        engine.player.drifting = False

        tac.ev_key(engine, _key_event(tcod.event.KeySym.q, mod=0))
        assert not isinstance(engine.current_state, ConfirmQuitState)
