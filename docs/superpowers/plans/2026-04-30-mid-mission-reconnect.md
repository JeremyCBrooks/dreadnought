# Mid-Mission Reconnect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the Engine object alive across WebSocket disconnects so players resume exactly where they left off, including mid-dungeon.

**Architecture:** `GameSession` gains `connected` and `idle_since` fields. On natural disconnect the session is kept in `game_manager` with `connected=False`; `engine_to_dict` saves strategic state as a fallback. On reconnect, `game_session()` finds the existing disconnected session and reattaches. A startup background task evicts sessions idle beyond 30 minutes.

**Tech Stack:** FastAPI, asyncio, Python 3.12, pytest, pytest-asyncio, starlette TestClient

---

### Task 1: Add `connected` and `idle_since` to `GameSession`

**Files:**
- Modify: `web/game_manager.py`
- Modify: `tests/test_game_manager.py`

- [ ] **Step 1: Write failing tests**

Add at the bottom of `tests/test_game_manager.py`:

```python
from datetime import datetime, timezone


def test_session_defaults_to_disconnected():
    import web.game_manager as gm

    gm._sessions.clear()
    session = gm.register("alice", make_engine())
    assert session.connected is False
    assert session.idle_since is None
    gm._sessions.clear()


def test_session_connected_flag_is_settable():
    import web.game_manager as gm

    gm._sessions.clear()
    session = gm.register("alice", make_engine())
    session.connected = True
    assert session.connected is True
    gm._sessions.clear()


def test_session_idle_since_is_settable():
    import web.game_manager as gm

    gm._sessions.clear()
    session = gm.register("alice", make_engine())
    now = datetime.now(timezone.utc)
    session.idle_since = now
    assert session.idle_since == now
    gm._sessions.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_game_manager.py::test_session_defaults_to_disconnected tests/test_game_manager.py::test_session_connected_flag_is_settable tests/test_game_manager.py::test_session_idle_since_is_settable -v
```

Expected: `AttributeError` — fields don't exist yet.

- [ ] **Step 3: Add fields and import to `web/game_manager.py`**

Add `datetime` import at the top of `web/game_manager.py`:

```python
from datetime import datetime
```

Add two fields to `GameSession` (after `_gather_task`):

```python
    connected: bool = False
    idle_since: datetime | None = None
```

Full `GameSession` dataclass after the change:

```python
@dataclass
class GameSession:
    engine: Engine
    username: str
    watcher_queues: list[asyncio.Queue] = field(default_factory=list)
    tile_state: dict[tuple[int, int], list[int]] = field(default_factory=dict)
    force_end: bool = False
    _gather_task: asyncio.Task | None = None
    connected: bool = False
    idle_since: datetime | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_game_manager.py::test_session_defaults_to_disconnected tests/test_game_manager.py::test_session_connected_flag_is_settable tests/test_game_manager.py::test_session_idle_since_is_settable -v
```

Expected: PASS

- [ ] **Step 5: Run full game_manager test suite for regressions**

```
pytest tests/test_game_manager.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```
git add web/game_manager.py tests/test_game_manager.py
git commit -m "feat: add connected and idle_since fields to GameSession"
```

---

### Task 2: Add `get_idle_usernames()` to `game_manager`

This function returns the usernames of sessions that have been disconnected longer than a given TTL. The idle cleanup task (Task 5) uses it.

**Files:**
- Modify: `web/game_manager.py`
- Modify: `tests/test_game_manager.py`

- [ ] **Step 1: Write failing tests**

Add at the bottom of `tests/test_game_manager.py`:

```python
def test_get_idle_usernames_excludes_connected():
    import web.game_manager as gm

    gm._sessions.clear()
    session = gm.register("alice", make_engine())
    session.connected = True
    result = gm.get_idle_usernames(ttl_seconds=0)
    assert "alice" not in result
    gm._sessions.clear()


def test_get_idle_usernames_excludes_no_idle_since():
    import web.game_manager as gm

    gm._sessions.clear()
    session = gm.register("alice", make_engine())
    session.connected = False
    session.idle_since = None
    result = gm.get_idle_usernames(ttl_seconds=0)
    assert "alice" not in result
    gm._sessions.clear()


def test_get_idle_usernames_excludes_recent_disconnect():
    import web.game_manager as gm
    from datetime import datetime, timezone

    gm._sessions.clear()
    session = gm.register("alice", make_engine())
    session.connected = False
    session.idle_since = datetime.now(timezone.utc)
    result = gm.get_idle_usernames(ttl_seconds=3600)
    assert "alice" not in result
    gm._sessions.clear()


def test_get_idle_usernames_includes_expired():
    import web.game_manager as gm
    from datetime import datetime, timedelta, timezone

    gm._sessions.clear()
    session = gm.register("alice", make_engine())
    session.connected = False
    session.idle_since = datetime.now(timezone.utc) - timedelta(seconds=3601)
    result = gm.get_idle_usernames(ttl_seconds=3600)
    assert "alice" in result
    gm._sessions.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_game_manager.py::test_get_idle_usernames_excludes_connected tests/test_game_manager.py::test_get_idle_usernames_excludes_no_idle_since tests/test_game_manager.py::test_get_idle_usernames_excludes_recent_disconnect tests/test_game_manager.py::test_get_idle_usernames_includes_expired -v
```

Expected: `AttributeError` — function doesn't exist yet.

- [ ] **Step 3: Implement `get_idle_usernames()` in `web/game_manager.py`**

Add after the `list_active` function:

```python
def get_idle_usernames(ttl_seconds: float) -> list[str]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    result = []
    for username, session in _sessions.items():
        if session.connected or session.idle_since is None:
            continue
        if (now - session.idle_since).total_seconds() >= ttl_seconds:
            result.append(username)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_game_manager.py::test_get_idle_usernames_excludes_connected tests/test_game_manager.py::test_get_idle_usernames_excludes_no_idle_since tests/test_game_manager.py::test_get_idle_usernames_excludes_recent_disconnect tests/test_game_manager.py::test_get_idle_usernames_includes_expired -v
```

Expected: PASS

- [ ] **Step 5: Run full game_manager suite**

```
pytest tests/test_game_manager.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```
git add web/game_manager.py tests/test_game_manager.py
git commit -m "feat: add get_idle_usernames to game_manager"
```

---

### Task 3: Natural disconnect keeps session alive (no death penalty)

Changes the `finally` block in `game_session()`. On natural disconnect: mark `connected=False`, save engine state (no death), keep session registered. On `force_end`: unregister as before (auth.py already wrote the save).

**Files:**
- Create: `tests/test_reconnect.py`
- Modify: `web/server.py`

- [ ] **Step 1: Create test file with fixture and disconnect test**

Create `tests/test_reconnect.py`:

```python
"""Integration tests for mid-mission reconnect via in-memory engine persistence."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import web.db as db
import web.game_manager as gm


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    asyncio.run(db.init_db())
    gm._sessions.clear()
    from web.server import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    gm._sessions.clear()


def _register_and_new_game(client, username="alice", password="supersecret1") -> str:
    """Register user, log in, create new game. Returns session token."""
    client.post("/api/register", json={"username": username, "password": password, "confirm": password})
    client.post("/api/login", json={"username": username, "password": password})
    client.post("/api/new-game", json={})
    return client.cookies.get("session_token", "")


def test_natural_disconnect_keeps_session_registered(client):
    """After a natural WebSocket close, the session stays in game_manager."""
    token = _register_and_new_game(client)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # consume the initial full frame

    session = gm.get("alice")
    assert session is not None
    assert session.connected is False


def test_natural_disconnect_saves_without_death(client):
    """Natural disconnect must not write a death record, even mid-mission."""
    from ui.tactical_state import TacticalState

    token = _register_and_new_game(client)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        # Simulate mid-mission by pushing TacticalState directly onto the engine.
        session = gm.get("alice")
        session.engine._state_stack.append(TacticalState.__new__(TacticalState))

    user = asyncio.run(db.get_user_by_name("alice"))
    saved = asyncio.run(db.load_game(user["id"]))
    assert saved is not None
    assert saved.get("dead") is not True


def test_natural_disconnect_sets_idle_since(client):
    """idle_since is populated after natural disconnect."""
    token = _register_and_new_game(client)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()

    session = gm.get("alice")
    assert session.idle_since is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_reconnect.py::test_natural_disconnect_keeps_session_registered tests/test_reconnect.py::test_natural_disconnect_saves_without_death tests/test_reconnect.py::test_natural_disconnect_sets_idle_since -v
```

Expected: FAIL — current code calls `game_manager.unregister` and writes a death save.

- [ ] **Step 3: Rewrite the `finally` block in `game_session()` in `web/server.py`**

Replace the entire `finally` block:

```python
    # OLD:
    finally:
        game_manager.unregister(username)
        if not session.force_end:
            # Natural disconnect — notify watchers and save state
            for q in session.watcher_queues:
                await q.put(None)
            from web.save_load import is_mid_mission, make_death_save_dict

            if is_mid_mission(engine):
                # Mid-mission disconnect = death. Prevents the heal/inventory
                # exploit where players yank the websocket to escape danger.
                state_json = json.dumps(make_death_save_dict("Connection lost mid-mission"))
            else:
                state_json = json.dumps(engine_to_dict(engine))
            await db.save_game(user_id, state_json)
```

With:

```python
    finally:
        if session.force_end:
            # auth.py already wrote the save; just clean up the registry.
            game_manager.unregister(username)
        else:
            from datetime import datetime, timezone

            from web.save_load import engine_to_dict

            session.connected = False
            session.idle_since = datetime.now(timezone.utc)
            for q in session.watcher_queues:
                await q.put(None)
            state_json = json.dumps(engine_to_dict(engine))
            await db.save_game(user_id, state_json)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_reconnect.py::test_natural_disconnect_keeps_session_registered tests/test_reconnect.py::test_natural_disconnect_saves_without_death tests/test_reconnect.py::test_natural_disconnect_sets_idle_since -v
```

Expected: PASS

- [ ] **Step 5: Verify force_end tests still pass**

```
pytest tests/test_force_end_death.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```
git add web/server.py tests/test_reconnect.py
git commit -m "feat: natural disconnect keeps session alive without death penalty"
```

---

### Task 4: Reconnect reuses existing engine

Changes the top of `game_session()` to detect an existing disconnected session and reuse its engine instead of loading from DB.

**Files:**
- Modify: `tests/test_reconnect.py`
- Modify: `web/server.py`

- [ ] **Step 1: Write failing reconnect tests**

Add to `tests/test_reconnect.py`:

```python
def test_reconnect_reuses_engine_object(client):
    """Reconnecting attaches to the same Engine instance, not a new one."""
    token = _register_and_new_game(client)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        first_engine_id = id(gm.get("alice").engine)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        second_engine_id = id(gm.get("alice").engine)

    assert first_engine_id == second_engine_id


def test_reconnect_marks_session_connected(client):
    """After reconnecting, session.connected is True again."""
    token = _register_and_new_game(client)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()

    # Session is disconnected now.
    assert gm.get("alice").connected is False

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        assert gm.get("alice").connected is True


def test_reconnect_clears_idle_since(client):
    """idle_since is cleared when the player reconnects."""
    token = _register_and_new_game(client)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()

    assert gm.get("alice").idle_since is not None

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        assert gm.get("alice").idle_since is None


def test_duplicate_connected_session_rejected(client):
    """A second connection while already connected must be rejected (1008)."""
    token = _register_and_new_game(client)

    with client.websocket_connect(f"/ws?token={token}") as ws1:
        ws1.receive_json()
        # Second connection while first is still open.
        with client.websocket_connect(f"/ws?token={token}") as ws2:
            # The server closes it immediately; receive will raise or return close.
            try:
                ws2.receive_json()
                assert False, "Expected WebSocket to be closed"
            except Exception:
                pass  # expected: server rejected with close code 1008
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_reconnect.py::test_reconnect_reuses_engine_object tests/test_reconnect.py::test_reconnect_marks_session_connected tests/test_reconnect.py::test_reconnect_clears_idle_since tests/test_reconnect.py::test_duplicate_connected_session_rejected -v
```

Expected: FAIL — `test_reconnect_reuses_engine_object` fails because current code reloads from DB (new engine); `test_duplicate_connected_session_rejected` may pass accidentally (current guard rejects any duplicate session, connected or not).

- [ ] **Step 3: Rewrite the connection setup in `game_session()` in `web/server.py`**

Replace the section from after the duplicate-connection guard through `engine = Engine()` / `dict_to_engine(...)` / `session = game_manager.register(...)`:

Current code (lines roughly 43–61):

```python
    # Reject duplicate connections
    if game_manager.get(username) is not None:
        await ws.close(code=1008)
        return

    # Load or skip (portal guarantees save exists, but be safe)
    saved = await db.load_game(user_id)
    if saved is None:
        await ws.close(code=1008)
        return

    from engine.game_state import Engine
    from web.save_load import dict_to_engine, engine_to_dict

    engine = Engine()
    dict_to_engine(saved, engine)

    session = game_manager.register(username, engine)
    await ws.accept()
```

Replace with:

```python
    existing = game_manager.get(username)
    if existing is not None:
        if existing.connected:
            # Genuine duplicate — already playing.
            await ws.close(code=1008)
            return
        # Reconnect: reuse the in-memory engine.
        engine = existing.engine
        session = existing
        session.connected = True
        session.idle_since = None
    else:
        # New connection: load save from DB.
        saved = await db.load_game(user_id)
        if saved is None:
            await ws.close(code=1008)
            return

        from engine.game_state import Engine
        from web.save_load import dict_to_engine

        engine = Engine()
        dict_to_engine(saved, engine)
        session = game_manager.register(username, engine)
        session.connected = True

    await ws.accept()
```

- [ ] **Step 4: Run reconnect tests to verify they pass**

```
pytest tests/test_reconnect.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full test suite to check for regressions**

```
pytest tests/test_force_end_death.py tests/test_game_manager.py tests/test_reconnect.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```
git add web/server.py tests/test_reconnect.py
git commit -m "feat: reconnect reuses in-memory engine across WebSocket disconnects"
```

---

### Task 5: Idle cleanup background task

After 30 minutes idle, a session is evicted from `game_manager` (save already written on disconnect). Runs as an asyncio background task started on app startup.

**Files:**
- Modify: `tests/test_game_manager.py`
- Modify: `web/server.py`

- [ ] **Step 1: Write failing idle-eviction test**

Add to `tests/test_game_manager.py`:

```python
def test_get_idle_usernames_multiple_sessions():
    import web.game_manager as gm
    from datetime import datetime, timedelta, timezone

    gm._sessions.clear()

    # connected — must not be evicted
    s1 = gm.register("connected_user", make_engine())
    s1.connected = True

    # disconnected but recent — must not be evicted
    s2 = gm.register("recent_user", make_engine())
    s2.connected = False
    s2.idle_since = datetime.now(timezone.utc) - timedelta(seconds=100)

    # disconnected and expired — must be evicted
    s3 = gm.register("idle_user", make_engine())
    s3.connected = False
    s3.idle_since = datetime.now(timezone.utc) - timedelta(seconds=1801)

    result = gm.get_idle_usernames(ttl_seconds=1800)
    assert "connected_user" not in result
    assert "recent_user" not in result
    assert "idle_user" in result
    gm._sessions.clear()
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_game_manager.py::test_get_idle_usernames_multiple_sessions -v
```

Expected: FAIL (function exists from Task 2, but this test is new — it may pass or fail depending on implementation; run to confirm behaviour is correct).

- [ ] **Step 3: Add idle cleanup loop to `web/server.py`**

Add constants and functions before the `@app.on_event("startup")` handler:

```python
_IDLE_TTL_SECONDS = 30 * 60      # 30 minutes
_IDLE_CHECK_INTERVAL = 5 * 60    # 5 minutes


async def _idle_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(_IDLE_CHECK_INTERVAL)
        for username in game_manager.get_idle_usernames(_IDLE_TTL_SECONDS):
            game_manager.unregister(username)
```

Update the startup event to start the cleanup task:

```python
@app.on_event("startup")
async def startup() -> None:
    await db.init_db()
    asyncio.create_task(_idle_cleanup_loop())
```

- [ ] **Step 4: Run idle eviction test to verify it passes**

```
pytest tests/test_game_manager.py::test_get_idle_usernames_multiple_sessions -v
```

Expected: PASS

- [ ] **Step 5: Run the full test suite**

```
pytest tests/test_reconnect.py tests/test_force_end_death.py tests/test_game_manager.py -v
```

Expected: all pass.

- [ ] **Step 6: Run the full project test suite**

```
pytest
```

Expected: all pass (or at minimum no new failures compared to before this feature branch).

- [ ] **Step 7: Commit**

```
git add web/server.py tests/test_game_manager.py
git commit -m "feat: idle cleanup evicts disconnected sessions after 30 minutes"
```

---

## Self-Review

**Spec coverage:**
- ✅ `connected` + `idle_since` fields on `GameSession` — Task 1
- ✅ Natural disconnect: mark disconnected, save without death — Task 3
- ✅ Reconnect: duplicate guard updated, reuse engine — Task 4
- ✅ `/api/end-game` force_end path unchanged — preserved in Task 3 finally block
- ✅ `is_mid_mission` removed from natural disconnect — Task 3
- ✅ Idle cleanup background task, 5-min interval, 30-min TTL — Task 5
- ✅ On eviction: unregister (save already written on disconnect) — Task 5

**Type consistency:**
- `session.connected: bool` — set in Task 1, read/written in Tasks 3 and 4 ✅
- `session.idle_since: datetime | None` — set in Task 1, written in Task 3, cleared in Task 4, read by `get_idle_usernames` from Task 2 ✅
- `game_manager.get_idle_usernames(ttl_seconds: float) -> list[str]` — defined Task 2, called Task 5 ✅
- `engine` variable on reconnect path assigned from `existing.engine` before `await ws.accept()` ✅
