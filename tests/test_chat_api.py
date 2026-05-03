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


def test_post_chat_unauth_returns_401(client):
    r = client.post("/api/chat", json={"body": "hi"})
    assert r.status_code == 401


def test_post_chat_simple_message(client):
    _register_and_login(client)
    r = client.post("/api/chat", json={"body": "hello world"})
    assert r.status_code == 200
    assert "id" in r.json()
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


def test_post_chat_long_with_collapsible_whitespace_accepted(client):
    """A message that scrubs to <=280 chars must be accepted even if raw is >280 chars."""
    _register_and_login(client)
    raw = "hello  " * 41  # 287 raw chars; scrubs to 245 chars ("hello hello ... hello")
    r = client.post("/api/chat", json={"body": raw})
    assert r.status_code == 200, r.text
    rows = client.get("/api/chat").json()["messages"]
    # Verify it was actually scrubbed and stored.
    assert len(rows[-1]["body"]) <= 280
    assert rows[-1]["body"].count("hello") == 41


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
