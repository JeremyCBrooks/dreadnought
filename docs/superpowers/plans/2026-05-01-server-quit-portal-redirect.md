# Server Quit → Portal Redirect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a server-game player confirms quit (Esc → Y), end their session, delete their save, and redirect the browser to `/portal.html`.

**Architecture:** Add a `QuitToPortal` exception and an `on_quit: Callable | None` field to `Engine`. `ConfirmQuitState` calls `engine.on_quit()` when set (server path) or raises `SystemExit` (desktop path, unchanged). The WebSocket handler wires `engine.on_quit` to raise `QuitToPortal`, catches it after the game loop, deletes the DB save, and sends `{"type": "portal_redirect"}` to the client.

**Tech Stack:** Python 3.12, FastAPI/Starlette, asyncio, pytest

---

### Task 1: Add `QuitToPortal` exception and `on_quit` field to `Engine`

**Files:**
- Modify: `engine/game_state.py`
- Test: `tests/test_confirm_quit.py`

- [ ] **Step 1: Write two failing tests**

Add this class to `tests/test_confirm_quit.py` after the existing `TestConfirmQuitDialogText` class:

```python
class TestOnQuit:
    def test_y_calls_on_quit_when_set(self):
        """When engine.on_quit is set, pressing Y calls it instead of raising SystemExit."""
        import tcod.event

        engine = make_engine()
        called = []
        engine.on_quit = lambda: called.append(True)
        state = ConfirmQuitState()
        engine.push_state(state)
        state.ev_key(engine, _key_event(tcod.event.KeySym.y))
        assert called == [True]

    def test_y_raises_system_exit_when_on_quit_is_none(self):
        """When engine.on_quit is None, pressing Y still raises SystemExit."""
        import tcod.event

        engine = make_engine()
        assert engine.on_quit is None
        state = ConfirmQuitState()
        engine.push_state(state)
        with pytest.raises(SystemExit):
            state.ev_key(engine, _key_event(tcod.event.KeySym.y))
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_confirm_quit.py::TestOnQuit -v
```

Expected: `FAILED` — `Engine` has no `on_quit` attribute.

- [ ] **Step 3: Add `QuitToPortal` and `on_quit` to `engine/game_state.py`**

Insert `QuitToPortal` before `_ANIM_TIMEOUT = 0.1` (after the import block):

```python
class QuitToPortal(Exception):
    """Raised by engine.on_quit to signal a server session should end and redirect."""
```

In `Engine.__init__`, add after `self.turn_counter: int = 0`:

```python
        self.on_quit: Callable[[], None] | None = None
```

`Callable` is already imported from `collections.abc` at line 6 — no new import needed.

- [ ] **Step 4: Run tests to verify they still fail (for the right reason)**

```
pytest tests/test_confirm_quit.py::TestOnQuit -v
```

Expected: `test_y_calls_on_quit_when_set` still fails — `ConfirmQuitState` raises `SystemExit` unconditionally and never calls the callback.

- [ ] **Step 5: Commit skeleton**

```
git add engine/game_state.py tests/test_confirm_quit.py
git commit -m "feat: add QuitToPortal exception and Engine.on_quit field"
```

---

### Task 2: Update `ConfirmQuitState` to use `on_quit`

**Files:**
- Modify: `ui/confirm_quit_state.py`
- Test: `tests/test_confirm_quit.py` (tests written in Task 1)

- [ ] **Step 1: Replace `raise SystemExit` in `ConfirmQuitState.ev_key`**

In `ui/confirm_quit_state.py`, change the `key == K.y` branch from:

```python
        if key == K.y:
            if self.abandon:
                from ui.game_over_state import GameOverState

                engine.switch_state(GameOverState(victory=False, title="MISSION ABANDONED"))
                return True
            raise SystemExit
```

to:

```python
        if key == K.y:
            if self.abandon:
                from ui.game_over_state import GameOverState

                engine.switch_state(GameOverState(victory=False, title="MISSION ABANDONED"))
                return True
            if engine.on_quit:
                engine.on_quit()
                return True
            raise SystemExit
```

- [ ] **Step 2: Run `TestOnQuit` to verify both tests pass**

```
pytest tests/test_confirm_quit.py::TestOnQuit -v
```

Expected: both `PASSED`.

- [ ] **Step 3: Run the full confirm-quit test file to check no regressions**

```
pytest tests/test_confirm_quit.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 4: Commit**

```
git add ui/confirm_quit_state.py
git commit -m "feat: ConfirmQuitState calls engine.on_quit when set"
```

---

### Task 3: Wire the server WebSocket handler

**Files:**
- Modify: `web/server.py`
- Test: `tests/test_server.py`

`QuitToPortal` is raised synchronously from within `ev_key` → `engine.run_async()` → `asyncio.gather()` → the gather task. The outer `await session._gather_task` re-raises it, where we catch it to delete the save and redirect.

- [ ] **Step 1: Write two failing tests**

Add to `tests/test_server.py` after the existing helper functions:

```python
def test_server_wires_on_quit_to_raise_quit_to_portal(client):
    """After connecting, engine.on_quit is set and raises QuitToPortal when called."""
    import time

    from engine.game_state import QuitToPortal

    token = _create_game(client, "alice")

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # first frame — engine is now running
        session = gm.get("alice")
        assert session is not None
        assert callable(session.engine.on_quit), "server must set engine.on_quit"
        with pytest.raises(QuitToPortal):
            session.engine.on_quit()


def test_server_wires_on_quit_on_reconnect(client):
    """engine.on_quit is wired on reconnect (reused in-memory engine) too."""
    import time

    from engine.game_state import QuitToPortal

    token = _create_game(client, "alice")

    # First connection — disconnect immediately
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()

    time.sleep(0.1)

    # Reconnect — engine is reused from in-memory session
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        session = gm.get("alice")
        assert session is not None
        assert callable(session.engine.on_quit)
        with pytest.raises(QuitToPortal):
            session.engine.on_quit()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_server.py::test_server_wires_on_quit_to_raise_quit_to_portal tests/test_server.py::test_server_wires_on_quit_on_reconnect -v
```

Expected: both `FAILED` — `session.engine.on_quit` is `None`.

- [ ] **Step 3: Import `QuitToPortal` and wire `engine.on_quit` in `web/server.py`**

Add to the imports at the top of `web/server.py` (after `from web.key_map import ...`):

```python
from engine.game_state import QuitToPortal
```

In the `game_session` WebSocket handler, both the reconnect branch and the new-connection branch converge before `await ws.accept()`. Add the callback there (right before `await ws.accept()`):

```python
    def _quit_to_portal() -> None:
        raise QuitToPortal()

    engine.on_quit = _quit_to_portal

    await ws.accept()
```

- [ ] **Step 4: Run wiring tests to verify they pass**

```
pytest tests/test_server.py::test_server_wires_on_quit_to_raise_quit_to_portal tests/test_server.py::test_server_wires_on_quit_on_reconnect -v
```

Expected: both `PASSED`.

- [ ] **Step 5: Add `except QuitToPortal` to the task-await block in `web/server.py`**

The current block (after `session._gather_task = asyncio.create_task(_run())`):

```python
    try:
        await session._gather_task
    except asyncio.CancelledError:
        pass
    finally:
        if session.force_end:
            game_manager.unregister(username)
        else:
            from datetime import UTC, datetime

            from web.save_load import engine_to_dict

            session.connected = False
            session.idle_since = datetime.now(UTC)
            for q in session.watcher_queues:
                await q.put(None)
            state_json = json.dumps(engine_to_dict(engine))
            await db.save_game(user_id, state_json)
```

Replace with:

```python
    try:
        await session._gather_task
    except asyncio.CancelledError:
        pass
    except QuitToPortal:
        await db.delete_game(user_id)
        try:
            await ws.send_json({"type": "portal_redirect"})
        except Exception:
            pass
        session.force_end = True  # skip auto-save in finally
    finally:
        if session.force_end:
            game_manager.unregister(username)
        else:
            from datetime import UTC, datetime

            from web.save_load import engine_to_dict

            session.connected = False
            session.idle_since = datetime.now(UTC)
            for q in session.watcher_queues:
                await q.put(None)
            state_json = json.dumps(engine_to_dict(engine))
            await db.save_game(user_id, state_json)
```

- [ ] **Step 6: Run full server test suite**

```
pytest tests/test_server.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 7: Run the full test suite**

```
pytest
```

Expected: all tests pass, no regressions.

- [ ] **Step 8: Commit**

```
git add web/server.py tests/test_server.py
git commit -m "feat: catch QuitToPortal in WebSocket handler, delete save, redirect to portal"
```

---

### Task 4: Lint and final check

**Files:** `engine/game_state.py`, `ui/confirm_quit_state.py`, `web/server.py`

- [ ] **Step 1: Run ruff on changed files**

```
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe check engine/game_state.py ui/confirm_quit_state.py web/server.py
```

Expected: no errors. Fix any reported issues.

- [ ] **Step 2: Run ruff format**

```
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe format engine/game_state.py ui/confirm_quit_state.py web/server.py
```

- [ ] **Step 3: Run full test suite**

```
pytest
```

Expected: all pass.

- [ ] **Step 4: Commit if any lint fixes were made**

```
git add engine/game_state.py ui/confirm_quit_state.py web/server.py
git commit -m "style: ruff fixes for server quit portal redirect"
```
