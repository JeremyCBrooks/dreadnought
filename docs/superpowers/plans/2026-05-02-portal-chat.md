# Portal Public Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public chat sidebar to `portal.html`, visible only to logged-in players, backed by SQLite, polled every 5 s, with layered spam protection (per-user rate, per-IP rate, content scrub, duplicate guard).

**Architecture:** Two new REST endpoints (`GET /api/chat`, `POST /api/chat`) on the existing FastAPI app, one new SQLite table (`chat_messages`), an in-memory token-bucket rate limiter keyed by user_id, and a small client-side polling loop reused on the existing 5 s `setInterval` in `portal.js`. No new long-lived connections. Cleanup of messages older than 30 days runs on a once-a-day asyncio loop in the lifespan.

**Tech Stack:** Python 3.12+, FastAPI, aiosqlite, slowapi, vanilla JS, pytest + Starlette TestClient, ruff.

**Spec:** `docs/superpowers/specs/2026-05-02-portal-chat-design.md`

## File Structure

| File | Status | Responsibility |
|------|--------|---------------|
| `web/db.py` | Modify | Add `chat_messages` schema + 3 functions (insert/get/delete) |
| `web/chat.py` | Create | Router with `GET /api/chat`, `POST /api/chat`; `_scrub`, `_check_user_rate`, in-memory state |
| `web/server.py` | Modify | `include_router(chat_router)` + `_chat_cleanup_loop` in `_lifespan` |
| `web/static/portal.html` | Modify | Two-column flex layout; chat sidebar markup + CSS |
| `web/static/portal.js` | Modify | `refreshChat`, `sendChat`, counter wiring; reuse 5 s interval |
| `tests/test_chat_db.py` | Create | DB function tests |
| `tests/test_chat_api.py` | Create | API endpoint tests with TestClient |
| `tests/test_chat_cleanup.py` | Create | Retention cleanup test |

Tests live flat under `tests/` to match the existing project layout (`tests/test_auth.py`, `tests/test_rate_limit.py`, etc.) — no `tests/web/` subdir.

---

## Constants Reference

These appear in multiple tasks. Same values must be used everywhere.

```python
_MAX_BODY = 280              # max chars after trim
_USER_RATE_WINDOW_SEC = 30.0 # sliding window length
_USER_RATE_MAX = 5           # max sends per window
_HISTORY_LIMIT = 50          # messages returned on first load
_RETENTION_SECONDS = 30 * 86400  # 30 days
```

IP rate limit (slowapi): `10/minute` on `POST /api/chat`.
Cleanup loop interval: `24 * 3600` seconds.

---

## Task 1: Database schema and helpers

**Files:**
- Modify: `web/db.py`
- Test: `tests/test_chat_db.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chat_db.py`:

```python
"""Tests for chat_messages table helpers in web/db.py."""

import asyncio
import time

import pytest

import web.db as db


@pytest.fixture
def reset_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    asyncio.run(db.init_db())
    yield


async def _make_user(username: str = "alice") -> int:
    uid = await db.create_user(username, "dummyhash")
    assert uid is not None
    return uid


def test_insert_returns_increasing_ids(reset_db):
    async def _run():
        uid = await _make_user()
        a = await db.insert_chat_message(uid, "alice", "hello")
        b = await db.insert_chat_message(uid, "alice", "world")
        assert b > a

    asyncio.run(_run())


def test_get_messages_no_since_returns_last_n_ascending(reset_db):
    async def _run():
        uid = await _make_user()
        for i in range(60):
            await db.insert_chat_message(uid, "alice", f"msg{i}")
        rows = await db.get_chat_messages(since_id=None, limit=50)
        assert len(rows) == 50
        bodies = [r["body"] for r in rows]
        assert bodies[0] == "msg10"
        assert bodies[-1] == "msg59"

    asyncio.run(_run())


def test_get_messages_with_since_returns_only_newer(reset_db):
    async def _run():
        uid = await _make_user()
        ids = []
        for i in range(5):
            ids.append(await db.insert_chat_message(uid, "alice", f"msg{i}"))
        rows = await db.get_chat_messages(since_id=ids[2], limit=50)
        bodies = [r["body"] for r in rows]
        assert bodies == ["msg3", "msg4"]

    asyncio.run(_run())


def test_delete_old_messages_only_removes_old(reset_db):
    async def _run():
        uid = await _make_user()
        await db.insert_chat_message(uid, "alice", "fresh")
        # Backdate one row directly via SQL.
        async with db._connect() as conn:
            await conn.execute(
                "INSERT INTO chat_messages (user_id, username, body, created_at) VALUES (?, ?, ?, ?)",
                (uid, "alice", "stale", time.time() - 31 * 86400),
            )
            await conn.commit()
        deleted = await db.delete_old_chat_messages(30 * 86400)
        assert deleted == 1
        rows = await db.get_chat_messages(since_id=None, limit=50)
        bodies = [r["body"] for r in rows]
        assert bodies == ["fresh"]

    asyncio.run(_run())


def test_username_survives_user_deletion(reset_db):
    """Denormalized username column means deleted-user history still reads cleanly."""
    async def _run():
        uid = await _make_user("alice")
        await db.insert_chat_message(uid, "alice", "ghost message")
        # Hard-delete the user row.
        async with db._connect() as conn:
            await conn.execute("DELETE FROM users WHERE id = ?", (uid,))
            await conn.commit()
        rows = await db.get_chat_messages(since_id=None, limit=50)
        assert len(rows) == 1
        assert rows[0]["username"] == "alice"
        assert rows[0]["body"] == "ghost message"

    asyncio.run(_run())
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_chat_db.py -v
```

Expected: All 5 tests FAIL with "no such table: chat_messages" or "module 'web.db' has no attribute 'insert_chat_message'".

- [ ] **Step 3: Add schema and helpers to `web/db.py`**

Add to the `_SCHEMA` string (just before the closing `"""`):

```sql

CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    username   TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_created_at ON chat_messages(created_at);
```

Note: no `REFERENCES users(id)` — we want history to survive user deletion.

Append these functions to the end of `web/db.py`:

```python
async def insert_chat_message(user_id: int, username: str, body: str) -> int:
    async with _connect() as conn:
        cur = await conn.execute(
            "INSERT INTO chat_messages (user_id, username, body, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, body, time.time()),
        )
        await conn.commit()
        return cur.lastrowid


async def get_chat_messages(since_id: int | None, limit: int) -> list[aiosqlite.Row]:
    async with _connect() as conn:
        if since_id is None:
            async with conn.execute(
                """
                SELECT id, username, body, created_at FROM chat_messages
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
            return list(reversed(rows))
        async with conn.execute(
            """
            SELECT id, username, body, created_at FROM chat_messages
            WHERE id > ? ORDER BY id ASC LIMIT ?
            """,
            (since_id, limit),
        ) as cur:
            return list(await cur.fetchall())


async def delete_old_chat_messages(max_age_seconds: float) -> int:
    cutoff = time.time() - max_age_seconds
    async with _connect() as conn:
        cur = await conn.execute("DELETE FROM chat_messages WHERE created_at < ?", (cutoff,))
        await conn.commit()
        return cur.rowcount or 0
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_chat_db.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run ruff**

```
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe check web/db.py tests/test_chat_db.py
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe format web/db.py tests/test_chat_db.py
```

Expected: no errors; format reports "0 files reformatted" or reformats them cleanly.

- [ ] **Step 6: Commit**

```
git add web/db.py tests/test_chat_db.py
git commit -m "feat(chat): add chat_messages table and DB helpers"
```

---

## Task 2: Chat router scaffold (auth + GET endpoint, no spam protection yet)

**Files:**
- Create: `web/chat.py`
- Test: `tests/test_chat_api.py`

This task gets the GET endpoint working end-to-end so polling functions before we layer on rate limits.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chat_api.py`:

```python
"""Tests for /api/chat endpoints (web/chat.py)."""

import asyncio

import pytest
from starlette.testclient import TestClient

import web.chat as chat
import web.db as db
import web.game_manager as gm


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    asyncio.run(db.init_db())
    gm._sessions.clear()
    chat._user_buckets.clear()
    chat._last_body_by_user.clear()

    from web.server import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    gm._sessions.clear()


def _register_and_login(client, username="alice", password="supersecret1"):
    client.post(
        "/api/register",
        json={"username": username, "password": password, "confirm": password},
    )
    r = client.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r


def test_get_chat_unauth_returns_401(client):
    r = client.get("/api/chat")
    assert r.status_code == 401


def test_get_chat_authed_empty_returns_empty_list(client):
    _register_and_login(client)
    r = client.get("/api/chat")
    assert r.status_code == 200
    body = r.json()
    assert body["messages"] == []
    assert body["latest_id"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_chat_api.py -v
```

Expected: import error (`web.chat` doesn't exist) — that's a collection failure, fine.

- [ ] **Step 3: Create `web/chat.py` skeleton**

```python
"""FastAPI chat router: public portal chat for logged-in users."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Cookie, HTTPException, Request

from web import db
from web.auth import _require_auth, limiter

_MAX_BODY = 280
_USER_RATE_WINDOW_SEC = 30.0
_USER_RATE_MAX = 5
_HISTORY_LIMIT = 50

# In-memory state — resets on server restart. That's fine: at worst an attacker
# gets one extra burst of _USER_RATE_MAX after a restart, and slowapi's IP limit
# still applies.
_user_buckets: dict[int, deque[float]] = defaultdict(deque)
_last_body_by_user: dict[int, str] = {}

router = APIRouter(prefix="/api")


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "body": row["body"],
        "created_at": row["created_at"],
    }


@router.get("/chat")
async def get_chat(since: int | None = None, session_token: str | None = Cookie(default=None)):
    await _require_auth(session_token)
    rows = await db.get_chat_messages(since_id=since, limit=_HISTORY_LIMIT)
    messages = [_row_to_dict(r) for r in rows]
    latest_id = messages[-1]["id"] if messages else (since or 0)
    return {"messages": messages, "latest_id": latest_id}
```

- [ ] **Step 4: Wire the router into `web/server.py`**

In `web/server.py`, find the existing `app.include_router(auth_router)` line and add the chat router right after:

```python
from web.auth import router as auth_router
from web.chat import router as chat_router
```

```python
app.include_router(auth_router)
app.include_router(chat_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_chat_api.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Run ruff**

```
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe check web/chat.py web/server.py tests/test_chat_api.py
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe format web/chat.py web/server.py tests/test_chat_api.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```
git add web/chat.py web/server.py tests/test_chat_api.py
git commit -m "feat(chat): add /api/chat GET endpoint (auth-gated)"
```

---

## Task 3: POST endpoint with content scrub

**Files:**
- Modify: `web/chat.py`
- Modify: `tests/test_chat_api.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_chat_api.py`:

```python
def test_post_chat_unauth_returns_401(client):
    r = client.post("/api/chat", json={"body": "hi"})
    assert r.status_code == 401


def test_post_chat_simple_message(client):
    _register_and_login(client)
    r = client.post("/api/chat", json={"body": "hello world"})
    assert r.status_code == 200
    assert "id" in r.json()
    # Confirm visible via GET.
    rows = client.get("/api/chat").json()["messages"]
    assert len(rows) == 1
    assert rows[0]["body"] == "hello world"
    assert rows[0]["username"] == "alice"


def test_post_chat_empty_body_400(client):
    _register_and_login(client)
    r = client.post("/api/chat", json={"body": ""})
    assert r.status_code == 400
    assert r.json()["detail"] == "Empty message"


def test_post_chat_whitespace_only_400(client):
    _register_and_login(client)
    r = client.post("/api/chat", json={"body": "   \t  "})
    assert r.status_code == 400
    assert r.json()["detail"] == "Empty message"


def test_post_chat_too_long_400(client):
    _register_and_login(client)
    r = client.post("/api/chat", json={"body": "x" * 281})
    assert r.status_code == 400
    assert r.json()["detail"] == "Message too long"


def test_post_chat_strips_control_chars(client):
    _register_and_login(client)
    r = client.post("/api/chat", json={"body": "hi\x01\x07there\x00"})
    assert r.status_code == 200
    rows = client.get("/api/chat").json()["messages"]
    assert rows[-1]["body"] == "hithere"


def test_post_chat_collapses_whitespace(client):
    _register_and_login(client)
    r = client.post("/api/chat", json={"body": "hi   \t  there"})
    assert r.status_code == 200
    rows = client.get("/api/chat").json()["messages"]
    assert rows[-1]["body"] == "hi there"


def test_post_chat_strips_newlines(client):
    """Chat is single-line; newlines are control chars and get stripped."""
    _register_and_login(client)
    r = client.post("/api/chat", json={"body": "line1\nline2"})
    assert r.status_code == 200
    rows = client.get("/api/chat").json()["messages"]
    assert rows[-1]["body"] == "line1line2"


def test_get_chat_with_since_returns_only_new(client):
    _register_and_login(client)
    r1 = client.post("/api/chat", json={"body": "first"})
    first_id = r1.json()["id"]
    client.post("/api/chat", json={"body": "second"})

    r = client.get(f"/api/chat?since={first_id}")
    msgs = r.json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["body"] == "second"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_chat_api.py -v
```

Expected: the 9 new tests FAIL (no POST handler yet).

- [ ] **Step 3: Implement scrub + POST handler**

Add to `web/chat.py` (after `_row_to_dict`, before the GET handler):

```python
def _scrub(body: str) -> tuple[str, str | None]:
    """Return (cleaned, error). error is None on success."""
    # Strip control chars (anything < 0x20, including \n \r \t).
    stripped = "".join(ch for ch in body if ord(ch) >= 0x20)
    # Collapse runs of whitespace to a single space.
    parts = stripped.split()
    cleaned = " ".join(parts)
    if not cleaned:
        return "", "Empty message"
    if len(cleaned) > _MAX_BODY:
        return "", "Message too long"
    return cleaned, None
```

Add the POST handler (after the existing GET handler):

```python
@router.post("/chat")
async def post_chat(body: dict, session_token: str | None = Cookie(default=None)):
    user = await _require_auth(session_token)
    raw = str(body.get("body", ""))

    # Pre-scrub length check so a 10000-char dump returns "Message too long"
    # rather than being silently truncated to empty by whitespace collapse.
    if len(raw.strip()) > _MAX_BODY:
        raise HTTPException(400, "Message too long")

    cleaned, err = _scrub(raw)
    if err:
        raise HTTPException(400, err)

    new_id = await db.insert_chat_message(user["id"], user["username"], cleaned)
    return {"id": new_id}
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_chat_api.py -v
```

Expected: 11 passed (2 from Task 2 + 9 new).

- [ ] **Step 5: Run ruff**

```
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe check web/chat.py tests/test_chat_api.py
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe format web/chat.py tests/test_chat_api.py
```

- [ ] **Step 6: Commit**

```
git add web/chat.py tests/test_chat_api.py
git commit -m "feat(chat): add POST /api/chat with content scrub"
```

---

## Task 4: Per-user rate limit and duplicate guard

**Files:**
- Modify: `web/chat.py`
- Modify: `tests/test_chat_api.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_chat_api.py`:

```python
def test_post_chat_user_rate_limit(client):
    _register_and_login(client)
    # Need distinct bodies to bypass the duplicate guard.
    for i in range(5):
        r = client.post("/api/chat", json={"body": f"msg{i}"})
        assert r.status_code == 200, f"msg{i} failed: {r.text}"
    r = client.post("/api/chat", json={"body": "msg5"})
    assert r.status_code == 429
    assert "Slow down" in r.json()["detail"]


def test_post_chat_duplicate_guard_blocks_immediate_repeat(client):
    _register_and_login(client)
    r1 = client.post("/api/chat", json={"body": "hi"})
    assert r1.status_code == 200
    r2 = client.post("/api/chat", json={"body": "hi"})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "Duplicate message"


def test_post_chat_duplicate_after_different_message_allowed(client):
    """Guard is 'vs immediately previous', not 'ever sent before'."""
    _register_and_login(client)
    assert client.post("/api/chat", json={"body": "hi"}).status_code == 200
    assert client.post("/api/chat", json={"body": "there"}).status_code == 200
    assert client.post("/api/chat", json={"body": "hi"}).status_code == 200


def test_post_chat_duplicate_check_uses_scrubbed_body(client):
    """`hi` and `  hi  ` both scrub to `hi`; second should be flagged duplicate."""
    _register_and_login(client)
    assert client.post("/api/chat", json={"body": "hi"}).status_code == 200
    r = client.post("/api/chat", json={"body": "  hi  "})
    assert r.status_code == 400
    assert r.json()["detail"] == "Duplicate message"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_chat_api.py -v
```

Expected: the 4 new tests FAIL.

- [ ] **Step 3: Implement rate limit and duplicate guard**

Add helper to `web/chat.py` (after `_scrub`):

```python
def _check_user_rate(user_id: int) -> bool:
    """Return True if the user is under the per-user rate limit (sliding window)."""
    now = time.monotonic()
    bucket = _user_buckets[user_id]
    cutoff = now - _USER_RATE_WINDOW_SEC
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _USER_RATE_MAX:
        return False
    bucket.append(now)
    return True
```

Update the POST handler to insert checks 4 and 5 of the pipeline. Replace the body of `post_chat` with:

```python
@router.post("/chat")
async def post_chat(body: dict, session_token: str | None = Cookie(default=None)):
    user = await _require_auth(session_token)
    raw = str(body.get("body", ""))

    if len(raw.strip()) > _MAX_BODY:
        raise HTTPException(400, "Message too long")

    cleaned, err = _scrub(raw)
    if err:
        raise HTTPException(400, err)

    if not _check_user_rate(user["id"]):
        raise HTTPException(429, "Slow down — too many messages")

    if cleaned == _last_body_by_user.get(user["id"]):
        raise HTTPException(400, "Duplicate message")

    new_id = await db.insert_chat_message(user["id"], user["username"], cleaned)
    _last_body_by_user[user["id"]] = cleaned
    return {"id": new_id}
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_chat_api.py -v
```

Expected: 15 passed.

- [ ] **Step 5: Run ruff**

```
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe check web/chat.py tests/test_chat_api.py
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe format web/chat.py tests/test_chat_api.py
```

- [ ] **Step 6: Commit**

```
git add web/chat.py tests/test_chat_api.py
git commit -m "feat(chat): per-user rate limit and duplicate-message guard"
```

---

## Task 5: Per-IP rate limit (slowapi)

**Files:**
- Modify: `web/chat.py`
- Modify: `tests/test_chat_api.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_chat_api.py`:

```python
def test_post_chat_ip_rate_limit(client):
    """slowapi caps POST /api/chat at 10/minute per IP, across users."""
    # Register 12 users so per-user limit (5) doesn't trip first.
    for i in range(12):
        client.post(
            "/api/register",
            json={"username": f"user{i:02d}", "password": "supersecret1", "confirm": "supersecret1"},
        )

    accepted = 0
    rate_limited = False
    for i in range(12):
        # Login as this user to get their session cookie.
        client.cookies.clear()
        client.post("/api/login", json={"username": f"user{i:02d}", "password": "supersecret1"})
        r = client.post(
            "/api/chat",
            json={"body": f"msg from user{i:02d}"},
            headers={"X-Forwarded-For": "9.9.9.9"},
        )
        if r.status_code == 200:
            accepted += 1
        elif r.status_code == 429:
            rate_limited = True
            break
    assert accepted <= 10
    assert rate_limited, "expected 11th POST to hit slowapi 10/minute IP limit"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_chat_api.py::test_post_chat_ip_rate_limit -v
```

Expected: FAIL — no IP limit yet, all 12 POSTs accepted.

- [ ] **Step 3: Apply slowapi decorator to POST handler**

In `web/chat.py`, the `post_chat` function needs the slowapi limiter. slowapi's `@limiter.limit(...)` decorator requires the FastAPI request object as a parameter. Update the signature and decorate:

```python
@router.post("/chat")
@limiter.limit("10/minute")
async def post_chat(request: Request, body: dict, session_token: str | None = Cookie(default=None)):
    user = await _require_auth(session_token)
    raw = str(body.get("body", ""))

    if len(raw.strip()) > _MAX_BODY:
        raise HTTPException(400, "Message too long")

    cleaned, err = _scrub(raw)
    if err:
        raise HTTPException(400, err)

    if not _check_user_rate(user["id"]):
        raise HTTPException(429, "Slow down — too many messages")

    if cleaned == _last_body_by_user.get(user["id"]):
        raise HTTPException(400, "Duplicate message")

    new_id = await db.insert_chat_message(user["id"], user["username"], cleaned)
    _last_body_by_user[user["id"]] = cleaned
    return {"id": new_id}
```

(The `Request` import was already added in Task 2's skeleton.)

- [ ] **Step 4: Run all chat API tests**

```
pytest tests/test_chat_api.py -v
```

Expected: 16 passed.

If `test_post_chat_user_rate_limit` now flakes because slowapi's IP limit also resets between tests via the `_reset_rate_limiter` autouse fixture in `tests/conftest.py` — confirm `limiter.reset()` is being called. (It already is for `web.auth.limiter`, which is the same shared limiter.)

- [ ] **Step 5: Run ruff**

```
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe check web/chat.py tests/test_chat_api.py
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe format web/chat.py tests/test_chat_api.py
```

- [ ] **Step 6: Commit**

```
git add web/chat.py tests/test_chat_api.py
git commit -m "feat(chat): per-IP rate limit on POST /api/chat (10/min)"
```

---

## Task 6: 30-day retention cleanup loop

**Files:**
- Modify: `web/server.py`
- Create: `tests/test_chat_cleanup.py`

The cleanup function itself was tested in Task 1. This task wires it into the lifespan loop pattern used by `_idle_cleanup_loop` and `_session_cleanup_loop`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_chat_cleanup.py`:

```python
"""Tests for the chat cleanup loop wiring."""

import asyncio
import time

import pytest

import web.db as db


@pytest.fixture
def reset_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    asyncio.run(db.init_db())
    yield


def test_chat_cleanup_loop_function_exists():
    """The loop function must be importable so lifespan can schedule it."""
    from web.server import _chat_cleanup_loop

    assert callable(_chat_cleanup_loop)


def test_delete_old_chat_messages_uses_30_day_default(reset_db):
    """Verify the cleanup deletes only rows older than 30 days."""
    async def _run():
        uid = await db.create_user("alice", "h")
        await db.insert_chat_message(uid, "alice", "fresh")
        async with db._connect() as conn:
            await conn.execute(
                "INSERT INTO chat_messages (user_id, username, body, created_at) VALUES (?, ?, ?, ?)",
                (uid, "alice", "old", time.time() - 31 * 86400),
            )
            await conn.commit()
        deleted = await db.delete_old_chat_messages(30 * 86400)
        assert deleted == 1
        rows = await db.get_chat_messages(since_id=None, limit=50)
        assert [r["body"] for r in rows] == ["fresh"]

    asyncio.run(_run())
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_chat_cleanup.py -v
```

Expected: `test_chat_cleanup_loop_function_exists` FAILS with ImportError; the second test PASSES (the underlying function exists from Task 1).

- [ ] **Step 3: Add the cleanup loop to `web/server.py`**

Find the existing constants block at the top of `web/server.py`:

```python
_IDLE_TTL_SECONDS = 12 * 60 * 60  # 12 hours
_IDLE_CHECK_INTERVAL = 5 * 60  # 5 minutes
_SESSION_CLEANUP_INTERVAL = 24 * 60 * 60  # 1 day
```

Add below it:

```python
_CHAT_CLEANUP_INTERVAL = 24 * 60 * 60  # 1 day
_CHAT_RETENTION_SECONDS = 30 * 24 * 60 * 60  # 30 days
```

Add a new loop function alongside `_idle_cleanup_loop` and `_session_cleanup_loop`:

```python
async def _chat_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(_CHAT_CLEANUP_INTERVAL)
        await db.delete_old_chat_messages(_CHAT_RETENTION_SECONDS)
```

Update `_lifespan` to schedule and cancel it:

```python
@asynccontextmanager
async def _lifespan(app: FastAPI):
    await db.init_db()
    idle_task = asyncio.create_task(_idle_cleanup_loop())
    session_task = asyncio.create_task(_session_cleanup_loop())
    chat_task = asyncio.create_task(_chat_cleanup_loop())
    yield
    for t in (idle_task, session_task, chat_task):
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_chat_cleanup.py tests/test_chat_db.py tests/test_chat_api.py -v
```

Expected: all pass (2 + 5 + 16 = 23).

- [ ] **Step 5: Run ruff**

```
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe check web/server.py tests/test_chat_cleanup.py
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe format web/server.py tests/test_chat_cleanup.py
```

- [ ] **Step 6: Commit**

```
git add web/server.py tests/test_chat_cleanup.py
git commit -m "feat(chat): 30-day retention cleanup loop in lifespan"
```

---

## Task 7: Sidebar markup and CSS in portal.html

**Files:**
- Modify: `web/static/portal.html`

This is a layout change with no Python tests. Verify visually at the end.

- [ ] **Step 1: Restructure body to two-column flex**

In `web/static/portal.html`, replace the existing `<body>` opening (line 138 area) and the structure inside it. Keep the `<header>`, `<section>`s, and the trailing `<script>` blocks. Wrap the existing main content in a flex container and add the chat sidebar.

Find:

```html
<body>
  <header>
    ...
  </header>

  <section>
    <h2>My Game</h2>
    ...
  </section>

  <section>
    <h2>Active Players</h2>
    ...
  </section>

  <script src="portal.js"></script>
```

Replace with:

```html
<body>
  <div id="layout">
    <main id="main-col">
      <header>
        <h1>Dreadnought</h1>
        <div class="user-bar">
          <span id="username-display"></span>
          <button onclick="logout()">Logout</button>
        </div>
      </header>

      <section>
        <h2>My Game</h2>
        <div id="my-game-section"></div>
        <div class="msg" id="game-msg"></div>
      </section>

      <section>
        <h2>Active Players</h2>
        <table>
          <thead><tr><th>Player</th><th>Watchers</th><th></th></tr></thead>
          <tbody id="active-players"></tbody>
        </table>
      </section>
    </main>

    <aside id="chat-sidebar">
      <h2>Public Chat</h2>
      <div id="chat-log"></div>
      <form id="chat-form" onsubmit="sendChat(event)">
        <textarea id="chat-input" maxlength="280" rows="2" placeholder="Say something…"></textarea>
        <div id="chat-meta">
          <span id="chat-count">0/280</span>
          <span id="chat-error"></span>
        </div>
        <button type="submit">Send</button>
      </form>
    </aside>
  </div>

  <script src="portal.js"></script>
```

Remove the original `<header>` and two `<section>` blocks at the body root (now moved inside `<main id="main-col">`).

- [ ] **Step 2: Add CSS for the layout and sidebar**

Inside the existing `<style>` block in `portal.html` (after the existing rules, before `</style>`), append:

```css
#layout {
  display: flex;
  gap: 2rem;
  align-items: flex-start;
  position: relative;
  z-index: 1;
}
#main-col {
  flex: 1;
  min-width: 0;
}
#chat-sidebar {
  width: 320px;
  flex-shrink: 0;
  background: rgba(0, 0, 0, 0.55);
  border: 1px solid #222;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  height: calc(100vh - 4rem);
  position: sticky;
  top: 2rem;
}
#chat-sidebar h2 {
  margin-bottom: 0.5rem;
}
#chat-log {
  flex: 1;
  overflow-y: auto;
  background: #050505;
  border: 1px solid #1a1a1a;
  padding: 0.5rem;
  font-size: 0.8rem;
  color: #bbb;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.chat-msg {
  overflow-wrap: anywhere;
  line-height: 1.35;
}
.chat-msg time {
  color: #555;
  margin-right: 0.4rem;
  font-size: 0.7rem;
}
.chat-msg strong {
  color: #6af;
  margin-right: 0.3rem;
}
.chat-empty {
  color: #444;
  font-style: italic;
}
#chat-form {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
#chat-input {
  background: #050505;
  border: 1px solid #333;
  color: #ccc;
  font-family: monospace;
  font-size: 0.85rem;
  padding: 0.4rem;
  resize: none;
}
#chat-input:focus {
  outline: none;
  border-color: #6af;
}
#chat-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.7rem;
  color: #555;
  min-height: 1rem;
}
#chat-count.warn {
  color: #f66;
}
#chat-error {
  color: #f66;
}
@media (max-width: 900px) {
  #layout { flex-direction: column; }
  #chat-sidebar { width: 100%; height: auto; max-height: 50vh; position: static; }
}
```

- [ ] **Step 3: Verify HTML renders without breaking the existing sections**

Activate the venv and start the server:

```
.venv\Scripts\Activate.ps1
uvicorn web.server:app --reload --port 8000
```

Open http://localhost:8000/portal.html in a browser (after registering/logging in via the index page). Confirm:
- My Game and Active Players sections still render in the left column.
- A chat sidebar is visible on the right with placeholder textarea and counter "0/280".
- The chat log is empty (we haven't wired JS yet).

Stop the server (Ctrl+C).

- [ ] **Step 4: Commit**

```
git add web/static/portal.html
git commit -m "feat(chat): two-column portal layout with chat sidebar markup"
```

---

## Task 8: Client-side chat polling, send, and counter

**Files:**
- Modify: `web/static/portal.js`

- [ ] **Step 1: Add `escHtml` extension and chat state**

The existing `escHtml` in `portal.js` only handles `& < >`. We also need `"` and `'` for safety in attributes (we don't use them yet, but it's a one-line addition that prevents future foot-guns). Update `escHtml`:

Find:

```js
function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
```

Replace with:

```js
function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
```

- [ ] **Step 2: Add chat module to `portal.js`**

Append the following to the end of `portal.js` (before the trailing `init();` line):

```js
// ── Chat ──────────────────────────────────────────────────────────────────────

let chatLatestId = 0;

function formatChatTime(epochSeconds) {
  const d = new Date(epochSeconds * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function isChatPinnedToBottom(log) {
  return log.scrollHeight - log.scrollTop - log.clientHeight < 30;
}

function renderChatMessages(messages, append) {
  const log = document.getElementById("chat-log");
  if (!append) {
    log.innerHTML = "";
  }
  if (!append && messages.length === 0) {
    log.innerHTML = '<div class="chat-empty">No messages yet</div>';
    return;
  }
  // Remove placeholder if present.
  const empty = log.querySelector(".chat-empty");
  if (empty) empty.remove();

  const wasPinned = append ? isChatPinnedToBottom(log) : true;
  const frag = document.createDocumentFragment();
  for (const m of messages) {
    const row = document.createElement("div");
    row.className = "chat-msg";
    row.innerHTML =
      "<time>" + escHtml(formatChatTime(m.created_at)) + "</time>" +
      "<strong>" + escHtml(m.username) + "</strong>" +
      escHtml(m.body);
    frag.appendChild(row);
  }
  log.appendChild(frag);
  if (wasPinned) log.scrollTop = log.scrollHeight;
}

async function refreshChat() {
  const url = chatLatestId > 0 ? "/api/chat?since=" + chatLatestId : "/api/chat";
  const r = await api("GET", url);
  if (!r || !r.ok) return;
  const data = await r.json();
  const append = chatLatestId > 0;
  if (data.messages.length > 0) {
    renderChatMessages(data.messages, append);
  } else if (!append) {
    renderChatMessages([], false);
  }
  if (data.latest_id > chatLatestId) chatLatestId = data.latest_id;
}

let chatErrorTimer = null;

function showChatError(msg) {
  const el = document.getElementById("chat-error");
  el.textContent = msg;
  if (chatErrorTimer) clearTimeout(chatErrorTimer);
  chatErrorTimer = setTimeout(() => { el.textContent = ""; }, 5000);
}

async function sendChat(e) {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const body = input.value;
  if (!body.trim()) return;
  let r;
  try {
    r = await api("POST", "/api/chat", { body });
  } catch (_err) {
    showChatError("Send failed — try again");
    return;
  }
  if (!r) return;  // 401 — api() already redirected
  if (r.ok) {
    input.value = "";
    updateChatCount();
    // Pull immediately so the user sees their own message without waiting up to 5s.
    refreshChat();
  } else {
    const d = await r.json().catch(() => ({}));
    showChatError(d.detail || "Send failed");
  }
}

function updateChatCount() {
  const input = document.getElementById("chat-input");
  const count = document.getElementById("chat-count");
  const len = input.value.length;
  count.textContent = len + "/280";
  count.classList.toggle("warn", len >= 260);
}

function initChat() {
  document.getElementById("chat-input").addEventListener("input", updateChatCount);
  // Submit on Enter; Shift+Enter inserts newline (which the server strips).
  document.getElementById("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      document.getElementById("chat-form").requestSubmit();
    }
  });
  refreshChat();
}
```

- [ ] **Step 3: Wire chat into `init()` and the polling interval**

Find the existing `init()` function:

```js
async function init() {
  const r = await api("GET", "/api/me");
  if (!r || !r.ok) { location.href = "/"; return; }
  const { username } = await r.json();
  document.getElementById("username-display").textContent = username;
  await refreshMyGame();
  await refreshActivePlayers();
  setInterval(refreshActivePlayers, 5000);
}
```

Replace with:

```js
async function init() {
  const r = await api("GET", "/api/me");
  if (!r || !r.ok) { location.href = "/"; return; }
  const { username } = await r.json();
  document.getElementById("username-display").textContent = username;
  await refreshMyGame();
  await refreshActivePlayers();
  initChat();
  setInterval(() => {
    refreshActivePlayers();
    refreshChat();
  }, 5000);
}
```

- [ ] **Step 4: Manual smoke test**

```
.venv\Scripts\Activate.ps1
uvicorn web.server:app --reload --port 8000
```

In one browser:
1. Register a user, log in, go to portal.
2. Confirm chat sidebar shows "No messages yet".
3. Type "hello" → press Enter. Within ≤5 s (or immediately, since `sendChat` calls `refreshChat()`) the message appears with timestamp, username "alice", and the textarea clears.
4. Type the same "hello" → press Enter. Confirm "Duplicate message" appears in `#chat-error` for ~5 s.
5. Send 5 distinct messages quickly. The 6th attempt within 30 s should show "Slow down — too many messages".
6. Type 281 characters (paste a long string). Server returns "Message too long".
7. Live counter shows correct char count and turns red at 260+.

In a second browser (incognito) with a different account:
8. Send a message; confirm it appears in the first browser within ≤5 s.

Stop the server.

- [ ] **Step 5: Commit**

```
git add web/static/portal.js
git commit -m "feat(chat): client-side polling, send, counter, error display"
```

---

## Task 9: Full test suite + lint sweep

**Files:** none modified — verification only.

- [ ] **Step 1: Run the full chat test suite**

```
pytest tests/test_chat_db.py tests/test_chat_api.py tests/test_chat_cleanup.py -v
```

Expected: 23 passed.

- [ ] **Step 2: Run the full project test suite**

```
pytest
```

Expected: all tests pass; chat tests don't break existing auth/server/rate-limit tests. Pay attention to:
- `test_rate_limit.py` — the autouse `_reset_rate_limiter` fixture in `conftest.py` should keep slowapi state isolated.
- `test_auth.py` — should not be affected (router is independent).

If any pre-existing test breaks, the most likely cause is the new `chat_router` raising at import; check that `web/chat.py` imports cleanly.

- [ ] **Step 3: Lint and format the entire patch**

```
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe check web tests
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe format web tests
```

Expected: no errors. If `ruff format` reformats anything, commit the change.

- [ ] **Step 4: Commit any final formatting fixes (if needed)**

```
git status
# If anything changed:
git add -u
git commit -m "chore(chat): ruff format pass"
```

---

## Self-Review Notes

**Spec coverage:**
- ✅ Schema, denormalized username, indexes — Task 1.
- ✅ `_scrub` with `(cleaned, error)` tuple — Task 3.
- ✅ Per-user rate (5/30 s sliding window) — Task 4.
- ✅ Per-IP rate (10/min via slowapi) — Task 5.
- ✅ Duplicate guard against immediately-previous scrubbed body — Task 4.
- ✅ Last-50 GET, since-id GET — Task 1 (DB) + Task 2 (endpoint).
- ✅ 30-day retention, 24 h cleanup loop — Task 6.
- ✅ Right sidebar layout, scrollable log, textarea + counter, mobile fallback — Task 7.
- ✅ Polling on existing 5 s interval, immediate self-pull after send, scroll-pin behaviour — Task 8.
- ✅ XSS via `escHtml` (extended to cover quotes) — Task 8.
- ✅ All constants from spec match (280, 5, 30, 50, 30 days, 10/min).

**Type/name consistency:**
- `_scrub` returns `tuple[str, str | None]` consistently in spec, Task 3, Task 4.
- `chatLatestId` (camelCase JS variable) used consistently in Task 8.
- Function names match: `insert_chat_message`, `get_chat_messages`, `delete_old_chat_messages`, `_check_user_rate`, `refreshChat`, `sendChat`, `updateChatCount`, `initChat`.

**No placeholders:** All test bodies, implementation code, file paths, and commands are concrete.
