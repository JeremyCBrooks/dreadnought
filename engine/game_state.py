"""State machine: base State class and Engine with push/pop/switch."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from engine.message_log import MessageLog

if TYPE_CHECKING:
    import tcod.console
    import tcod.context
    import tcod.event
    from world.game_map import GameMap
    from game.entity import Entity
    from game.suit import Suit


class State:
    """Base class for all game states. Subclass and override methods."""

    def on_enter(self, engine: Engine) -> None:
        pass

    def on_exit(self, engine: Engine) -> None:
        pass

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        """Handle keydown. Return True if the event was consumed."""
        return False

    def on_render(self, console: tcod.console.Console, engine: Engine) -> None:
        pass


class Engine:
    """Owns the state stack, message log, and delegates input/render."""

    CONSOLE_WIDTH = 160
    CONSOLE_HEIGHT = 50

    def __init__(self) -> None:
        self._state_stack: List[State] = []
        self._context: Optional[tcod.context.Context] = None
        self._root_console: Optional[tcod.console.Console] = None
        self.message_log: MessageLog = MessageLog()
        self.game_map: Optional[GameMap] = None
        self.player: Optional[Entity] = None
        # Phase 3: environment hazards and suit resources
        self.environment: Optional[dict] = None  # {hazard_type: severity}
        self.suit: Optional[Suit] = None
        self.active_effects: List[dict] = []
        self.ship = None  # game.ship.Ship instance, created on new game
        self._pending_loadout = None  # Loadout instance from LoadoutState
        # Persist player stats between areas
        self._saved_player: Optional[dict] = None
        # Persisted areas: (location_name, depth) -> {game_map, rooms, exit_pos, seed}
        self.area_cache: Dict[Tuple[str, int], dict] = {}

    @property
    def current_state(self) -> Optional[State]:
        return self._state_stack[-1] if self._state_stack else None

    def push_state(self, state: State) -> None:
        """Push a new state on top. The previous state stays on the stack (suspended, no on_exit)."""
        self._state_stack.append(state)
        state.on_enter(self)

    def pop_state(self) -> None:
        """Pop the current state (calls on_exit). The state below resumes (no on_enter)."""
        if not self._state_stack:
            return
        top = self._state_stack.pop()
        top.on_exit(self)

    def switch_state(self, state: State) -> None:
        if self._state_stack:
            self._state_stack.pop().on_exit(self)
        self._state_stack.append(state)
        state.on_enter(self)

    def run(self) -> None:
        """Main loop: open window, run state machine until quit."""
        import tcod.context
        import tcod.console
        import tcod.event

        from engine.font import load_tileset

        tileset = load_tileset()
        with tcod.context.new(
            columns=self.CONSOLE_WIDTH,
            rows=self.CONSOLE_HEIGHT,
            tileset=tileset,
            title="Dreadnought",
        ) as self._context:
            self._root_console = tcod.console.Console(
                self.CONSOLE_WIDTH, self.CONSOLE_HEIGHT, order="F"
            )
            while True:
                self._root_console.clear()
                if self.current_state:
                    self.current_state.on_render(self._root_console, self)
                self._context.present(self._root_console)
                for event in tcod.event.wait():
                    if isinstance(event, tcod.event.Quit):
                        return
                    if isinstance(event, tcod.event.KeyDown):
                        if self.current_state:
                            handled = self.current_state.ev_keydown(self, event)
                            if not handled and event.sym == tcod.event.KeySym.ESCAPE:
                                return
                        else:
                            return
