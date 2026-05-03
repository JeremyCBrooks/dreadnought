"""Security tests for the web stack: cookies, WS auth, sessions, headers, rate limits."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient


def _make_client(tmp_path, monkeypatch, *, secure: bool):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    if secure:
        monkeypatch.setenv("COOKIE_SECURE", "1")
    else:
        monkeypatch.delenv("COOKIE_SECURE", raising=False)
        monkeypatch.delenv("FLY_APP_NAME", raising=False)

    import importlib

    from web import auth, db, server

    importlib.reload(db)
    importlib.reload(auth)
    importlib.reload(server)

    asyncio.new_event_loop().run_until_complete(db.init_db())
    return TestClient(server.app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Default test client: HTTP-style cookies so the cookie jar round-trips."""
    with _make_client(tmp_path, monkeypatch, secure=False) as c:
        yield c


@pytest.fixture
def secure_client(tmp_path, monkeypatch):
    """Test client with COOKIE_SECURE=1 — only used to assert the Secure flag/HSTS."""
    with _make_client(tmp_path, monkeypatch, secure=True) as c:
        yield c


def _register_and_login(client: TestClient, user="alice", pw="hunter2hunter2") -> str:
    client.post("/api/register", json={"username": user, "password": pw, "confirm": pw})
    r = client.post("/api/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return r.cookies.get("session_token")


# ── Cookie Secure flag ────────────────────────────────────────────────────────


def test_login_cookie_marked_secure_in_prod(secure_client):
    r = secure_client.post(
        "/api/register",
        json={"username": "bobby", "password": "longpassword1", "confirm": "longpassword1"},
    )
    assert r.status_code == 201
    r = secure_client.post("/api/login", json={"username": "bobby", "password": "longpassword1"})
    assert r.status_code == 200
    set_cookies = [v for k, v in r.headers.items() if k.lower() == "set-cookie"]
    assert any("session_token=" in c and "Secure" in c for c in set_cookies)


def test_login_cookie_not_secure_when_env_unset(client):
    client.post(
        "/api/register",
        json={"username": "xander", "password": "longpassword1", "confirm": "longpassword1"},
    )
    r = client.post("/api/login", json={"username": "xander", "password": "longpassword1"})
    set_cookies = [v for k, v in r.headers.items() if k.lower() == "set-cookie"]
    assert any("session_token=" in c for c in set_cookies)
    assert not any("session_token=" in c and "Secure" in c for c in set_cookies)


# ── Session TTL ───────────────────────────────────────────────────────────────


def test_expired_session_rejected(client, monkeypatch):
    from web import auth, db

    # Force tiny TTL.
    monkeypatch.setattr(db, "SESSION_TTL_SECONDS", 0.1, raising=False)
    monkeypatch.setattr(auth, "SESSION_TTL_SECONDS", 0.1, raising=False)

    client.post(
        "/api/register",
        json={"username": "carol", "password": "longpassword1", "confirm": "longpassword1"},
    )
    r = client.post("/api/login", json={"username": "carol", "password": "longpassword1"})
    assert r.status_code == 200

    time.sleep(0.2)
    r2 = client.get("/api/me")
    assert r2.status_code == 401


def test_active_session_accepted(client):
    client.post(
        "/api/register",
        json={"username": "danny", "password": "longpassword1", "confirm": "longpassword1"},
    )
    client.post("/api/login", json={"username": "danny", "password": "longpassword1"})
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["username"] == "danny"


# ── Username case-insensitive ────────────────────────────────────────────────


def test_username_case_collision_rejected(client):
    r = client.post(
        "/api/register",
        json={"username": "EveTwo", "password": "longpassword1", "confirm": "longpassword1"},
    )
    assert r.status_code == 201
    r2 = client.post(
        "/api/register",
        json={"username": "evetwo", "password": "longpassword1", "confirm": "longpassword1"},
    )
    assert r2.status_code == 409


def test_login_case_insensitive(client):
    client.post(
        "/api/register",
        json={"username": "Frank", "password": "longpassword1", "confirm": "longpassword1"},
    )
    r = client.post("/api/login", json={"username": "FRANK", "password": "longpassword1"})
    assert r.status_code == 200


# ── Constant-time login ──────────────────────────────────────────────────────


def test_login_runs_bcrypt_for_unknown_user(client, monkeypatch):
    """If user does not exist, bcrypt.checkpw must still run (timing-safe)."""
    import bcrypt

    calls = []
    real_checkpw = bcrypt.checkpw

    def spy(pw, h):
        calls.append((pw, h))
        return real_checkpw(pw, h)

    monkeypatch.setattr("web.auth._bcrypt_lib.checkpw", spy)

    r = client.post("/api/login", json={"username": "ghost", "password": "irrelevant1"})
    assert r.status_code == 401
    assert len(calls) == 1


# ── Register rate limit ──────────────────────────────────────────────────────


def test_register_rate_limited(client):
    """After many register attempts, slowapi should 429."""
    last = None
    for i in range(30):
        last = client.post(
            "/api/register",
            json={"username": f"u{i}", "password": "longpassword1", "confirm": "longpassword1"},
        )
        if last.status_code == 429:
            break
    assert last.status_code == 429


# ── Fly-Client-IP rate-limit key ─────────────────────────────────────────────


def test_real_ip_prefers_fly_client_ip():
    from unittest.mock import MagicMock

    from web.auth import _real_ip

    req = MagicMock()
    req.headers = {"Fly-Client-IP": "1.2.3.4", "X-Forwarded-For": "9.9.9.9, 8.8.8.8"}
    req.client.host = "127.0.0.1"
    assert _real_ip(req) == "1.2.3.4"


def test_real_ip_falls_back_to_xff():
    from unittest.mock import MagicMock

    from web.auth import _real_ip

    req = MagicMock()
    req.headers = {"X-Forwarded-For": "9.9.9.9, 8.8.8.8"}
    req.client.host = "127.0.0.1"
    assert _real_ip(req) == "9.9.9.9"


def test_real_ip_falls_back_to_client():
    from unittest.mock import MagicMock

    from web.auth import _real_ip

    req = MagicMock()
    req.headers = {}
    req.client.host = "127.0.0.1"
    assert _real_ip(req) == "127.0.0.1"


# ── Security headers ─────────────────────────────────────────────────────────


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    assert r.headers.get("X-Frame-Options") == "DENY"


def test_hsts_header_in_prod(secure_client):
    r = secure_client.get("/health")
    assert "max-age=" in r.headers.get("Strict-Transport-Security", "")


def test_hsts_absent_in_dev(client):
    r = client.get("/health")
    assert "Strict-Transport-Security" not in r.headers


# ── WebSocket auth via cookie ────────────────────────────────────────────────


def test_websocket_auth_via_cookie(client):
    _register_and_login(client, "wsuser", "longpassword1")
    # Create a save so the WS opens; otherwise it will close with portal_redirect.
    r = client.post("/api/new-game", json={})
    assert r.status_code == 201

    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        # Connection authenticated successfully — we got a frame, not a 1008 close.
        assert "type" in msg


def test_websocket_rejects_without_cookie(client):
    """No session cookie ⇒ close 1008."""
    # Use a fresh client with no cookie jar to ensure no auth.
    from starlette.testclient import WebSocketDenialResponse  # noqa: F401

    base_url = client.base_url
    fresh = TestClient(client.app, base_url=str(base_url))
    fresh.cookies.clear()
    with pytest.raises(Exception):
        with fresh.websocket_connect("/ws"):
            pass
