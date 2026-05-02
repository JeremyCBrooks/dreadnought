# Design: Server Game Quit → Portal Redirect

**Date:** 2026-05-01  
**Status:** Approved

## Problem

When a player presses Esc and confirms quit during a server (web) game session, the engine currently raises `SystemExit`. In the server context this crashes the async game loop rather than cleanly ending the session and returning the player to the portal.

## Goal

When a server-game player quits via Esc → confirm Y:
- Their DB save is deleted (same outcome as "End Game" on the portal)
- The browser navigates to `/portal.html`
- The desktop game is unaffected

## Design

### New exception — `engine/game_state.py`

```python
class QuitToPortal(Exception):
    """Raised by engine.on_quit to signal a server session should end."""
```

### Engine field — `Engine.__init__`

```python
self.on_quit: Callable[[], None] | None = None
```

Defaults to `None`. Only the server wires this up; the desktop never touches it.

### `ConfirmQuitState` change

Replace `raise SystemExit` in the confirm-Y branch with:

```python
if engine.on_quit:
    engine.on_quit()
else:
    raise SystemExit
```

Desktop behavior is identical — `on_quit` is `None`, `SystemExit` fires as before.

### Server wiring — `web/server.py` WebSocket handler

After the engine is loaded (new game or reconnect), set the callback:

```python
def _quit_to_portal() -> None:
    raise QuitToPortal()

engine.on_quit = _quit_to_portal
```

Wrap the `run_async` call to catch the new exception:

```python
try:
    await engine.run_async(send_frame, input_queue)
except QuitToPortal:
    await db.delete_game(user["id"])
    await ws.send_json({"type": "portal_redirect"})
```

The existing on-disconnect auto-save block must **not** run after `QuitToPortal` (the save was already deleted). Structure the handler so `QuitToPortal` skips the save path.

## Affected Files

| File | Change |
|------|--------|
| `engine/game_state.py` | Add `QuitToPortal` exception; add `on_quit` field to `Engine` |
| `ui/confirm_quit_state.py` | Replace `raise SystemExit` with `on_quit` callback or fallback |
| `web/server.py` | Wire `engine.on_quit`; catch `QuitToPortal` in WebSocket handler |

## What is NOT changing

- Desktop quit flow (`SystemExit`) — unchanged
- Mid-mission Esc behavior (consumed, must use Shift+Q) — unchanged
- Portal "End Game" button path — unchanged
- Watcher redirect logic — unchanged

## Testing

- Unit test: `ConfirmQuitState` calls `engine.on_quit` when set, does not raise `SystemExit`
- Unit test: `ConfirmQuitState` raises `SystemExit` when `on_quit` is `None`
- Integration test: server WebSocket handler catches `QuitToPortal`, deletes save, sends `portal_redirect`
