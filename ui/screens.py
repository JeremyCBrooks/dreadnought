"""Screens the game layer may ask for without importing the UI (see Engine.screen_request)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.game_state import Engine, State


def _trade(trader: Any) -> State:
    from ui.trade_state import TradeState

    return TradeState(trader)


# Screen name -> how to open it for the thing it is about.
SCREENS: dict[str, Callable[[Any], State]] = {
    "trade": _trade,
}


def open_requested_screen(engine: Engine) -> bool:
    """Open the screen the game asked for during the last action, if any. Returns True if one opened."""
    request = getattr(engine, "screen_request", None)
    if request is None:
        return False
    engine.screen_request = None
    name, subject = request
    engine.push_state(SCREENS[name](subject))
    return True
