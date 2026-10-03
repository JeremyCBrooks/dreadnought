"""State machine: base State class and Engine with push/pop/switch."""

from __future__ import annotations

import asyncio
import hashlib
import random
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from engine.message_log import MessageLog

if TYPE_CHECKING:
    import tcod.console
    import tcod.context
    import tcod.event

    from game.entity import Entity
    from game.scanner import ScanResults
    from game.ship import Ship
    from game.suit import Suit
    from world.galaxy import Galaxy
    from world.game_map import GameMap


class QuitToPortal(Exception):
    """Raised by engine.on_quit to signal a server session should end and redirect."""


_ANIM_TIMEOUT = 0.1


def seeded_rng(seed: int, turn: int, salt: str) -> random.Random:
    """A Random seeded from (seed, turn, salt): the same three always give the same stream."""
    digest = hashlib.sha256(f"{seed}:{turn}:{salt}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "little"))


class State:
    """Base class for all game states. Subclass and override methods."""

    needs_animation: bool = False

    def on_enter(self, engine: Engine) -> None:
        pass

    def on_exit(self, engine: Engine) -> None:
        pass

    def ev_key(self, engine: Engine, event: Any) -> bool:
        """Handle a key event. Return True if the event was consumed."""
        return False

    @staticmethod
    def _handle_log_scroll(engine: Engine, key: int) -> bool:
        """Handle PageUp/PageDown for message log scrolling. Returns True if consumed."""
        import tcod.event

        if key == tcod.event.KeySym.PAGEUP:
            engine.message_log.scroll(1)
            return True
        if key == tcod.event.KeySym.PAGEDOWN:
            engine.message_log.scroll(-1)
            return True
        return False

    def on_render(self, console: tcod.console.Console, engine: Engine) -> None:
        pass


class Engine:
    """Owns the state stack, message log, and delegates input/render."""

    CONSOLE_WIDTH = 160
    CONSOLE_HEIGHT = 50

    def __init__(self) -> None:
        self._state_stack: list[State] = []
        self._context: tcod.context.Context | None = None
        self._root_console: tcod.console.Console | None = None
        self.message_log: MessageLog = MessageLog()
        self.game_map: GameMap | None = None
        self.player: Entity | None = None
        # Phase 3: environment hazards and suit resources
        self.environment: dict[str, int] | None = None
        self.suit: Suit | None = None
        self.active_effects: list[dict] = []
        self.ship: Ship | None = None
        # Persist player stats between areas
        self.saved_player: dict | None = None
        # Persisted areas: (location_name, depth) -> {game_map, rooms, exit_pos, seed}
        self.area_cache: dict[tuple[str, int], dict] = {}
        self.scan_results: ScanResults | None = None
        self.scan_glow: dict | None = None
        self.mission_loadout: list[Entity] = []
        # (screen name, subject) the game asked the UI to open after the current action.
        self.screen_request: tuple[str, object] | None = None
        self.galaxy: Galaxy | None = None
        # Monotonic counter for deterministic RNG: bumped per game-time tick.
        self.turn_counter: int = 0
        self.on_quit: Callable[[], None] | None = None

    def rng(self, salt: str) -> random.Random:
        """Return a Random seeded from (galaxy.seed, turn_counter, salt).

        Per-call salting prevents two independent rolls in the same turn from
        sharing draws. Same engine state + same salt always reproduces the
        same stream - that's what makes save/load resistant to RNG savescum.
        """
        return seeded_rng(self.galaxy.seed if self.galaxy is not None else 0, self.turn_counter, salt)

    @property
    def states(self) -> tuple[State, ...]:
        """The state stack, bottom to top."""
        return tuple(self._state_stack)

    def has_state(self, state_type: type[State]) -> bool:
        """True if a state of *state_type* is anywhere on the stack."""
        return any(isinstance(state, state_type) for state in self._state_stack)

    def state_below(self, state: State) -> State | None:
        """The state directly under *state*, or None if it is at the bottom or not on the stack."""
        if state not in self._state_stack:
            return None
        index = self._state_stack.index(state)
        return self._state_stack[index - 1] if index > 0 else None

    def needs_animation(self) -> bool:
        """True while something on screen changes without input: starfield, flicker, scan glow, fades."""
        game_map = self.game_map
        map_animates = game_map is not None and (game_map.has_space or game_map.has_flickering_lights)
        state = self.current_state
        return bool(map_animates or self.scan_glow or (state is not None and state.needs_animation))

    @property
    def current_state(self) -> State | None:
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
        """Replace the current state (calls on_exit on old, on_enter on new)."""
        if self._state_stack:
            self._state_stack.pop().on_exit(self)
        self._state_stack.append(state)
        state.on_enter(self)

    def reset_to_state(self, state: State) -> None:
        """Clear the entire state stack and start fresh with *state*."""
        while self._state_stack:
            self._state_stack.pop().on_exit(self)
        self._state_stack.append(state)
        state.on_enter(self)

    async def run_async(
        self,
        send_frame: Callable[[dict], Awaitable[None]],
        input_queue: asyncio.Queue,
    ) -> None:
        """WebSocket game loop. Renders to an in-memory console and streams frames."""
        import tcod.console

        from engine.console_serializer import serialize_delta

        console = tcod.console.Console(self.CONSOLE_WIDTH, self.CONSOLE_HEIGHT, order="F")
        prev_tiles = None

        while True:
            console.clear()
            state_before = self.current_state
            if self.current_state:
                self.current_state.on_render(console, self)

            is_first = prev_tiles is None
            tiles, prev_tiles = serialize_delta(console, prev_tiles)
            msg_type = "full" if is_first else "frame"
            msg: dict = {"type": msg_type, "w": self.CONSOLE_WIDTH, "h": self.CONSOLE_HEIGHT, "tiles": tiles}
            if is_first and self.galaxy is not None:
                msg["seed"] = self.galaxy.seed
            await send_frame(msg)

            # Re-render immediately when state changed during render (e.g. drift death).
            # Reset prev_tiles so next frame is sent as a full frame.
            if self.current_state is not state_before:
                prev_tiles = None
                continue

            timeout = _ANIM_TIMEOUT if self.needs_animation() else None

            try:
                event = await asyncio.wait_for(input_queue.get(), timeout=timeout)
                if event is None:  # sentinel: client disconnected
                    return
                # Mirror run() routing: move keys fire on keydown, all others on keyup.
                from engine.keys import is_move_key as _is_move

                is_move = _is_move(event.sym)
                is_down = event.type == "keydown"
                if (is_move and is_down) or (not is_move and not is_down):
                    if self.current_state:
                        self.current_state.ev_key(self, event)
            except TimeoutError:
                pass  # animation tick - loop and re-render

    def run(self) -> None:
        """Main loop: open window, run state machine until quit."""
        import tcod.console
        import tcod.context
        import tcod.event

        from engine.font import load_tileset
        from engine.keys import is_move_key

        tileset = load_tileset()
        with tcod.context.new(
            columns=self.CONSOLE_WIDTH,
            rows=self.CONSOLE_HEIGHT,
            tileset=tileset,
            title="Dreadnought",
        ) as self._context:
            self._root_console = tcod.console.Console(self.CONSOLE_WIDTH, self.CONSOLE_HEIGHT, order="F")
            while True:
                self._root_console.clear()
                state_before = self.current_state
                if self.current_state:
                    self.current_state.on_render(self._root_console, self)
                self._context.present(self._root_console)
                # If state changed during render (e.g. drift death), immediately
                # re-render the new state instead of blocking for input.
                if self.current_state is not state_before:
                    continue
                # Short timeout when animation is needed; None (blocking) otherwise
                timeout = _ANIM_TIMEOUT if self.needs_animation() else None
                for event in tcod.event.wait(timeout=timeout):
                    if isinstance(event, tcod.event.Quit):
                        return
                    if isinstance(event, tcod.event.KeyDown):
                        if not is_move_key(event.sym):
                            continue
                        if self.current_state:
                            self.current_state.ev_key(self, event)
                        else:
                            return
                    elif isinstance(event, tcod.event.KeyUp):
                        if is_move_key(event.sym):
                            continue
                        if self.current_state:
                            handled = self.current_state.ev_key(self, event)
                            if not handled and event.sym == tcod.event.KeySym.ESCAPE:
                                return
                        else:
                            return
