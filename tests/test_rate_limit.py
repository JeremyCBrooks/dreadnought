"""Rate limiting tests for /api/login — slowapi + X-Forwarded-For key function."""

import asyncio

import pytest
from starlette.testclient import TestClient

import web.db as db
import web.game_manager as gm


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    asyncio.run(db.init_db())
    gm._sessions.clear()

    from web.server import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    gm._sessions.clear()


def _register(client, username="alice", password="supersecret1"):
    client.post(
        "/api/register",
        json={"username": username, "password": password, "confirm": password},
    )


_LIMIT = 10  # must match the limit set on /api/login


def test_login_rate_limited_after_threshold(client):
    """After _LIMIT failed attempts from the same IP, the endpoint returns 429."""
    _register(client)
    for _ in range(_LIMIT):
        r = client.post("/api/login", json={"username": "alice", "password": "wrongpassword"})
        assert r.status_code == 401

    r = client.post("/api/login", json={"username": "alice", "password": "wrongpassword"})
    assert r.status_code == 429


def test_x_forwarded_for_isolates_ip_buckets(client):
    """Two clients with different X-Forwarded-For IPs do not share a rate-limit bucket."""
    _register(client)

    # Exhaust the limit from IP-A.
    for _ in range(_LIMIT):
        client.post(
            "/api/login",
            json={"username": "alice", "password": "wrong"},
            headers={"X-Forwarded-For": "1.2.3.4"},
        )

    # IP-A is now rate-limited.
    r_a = client.post(
        "/api/login",
        json={"username": "alice", "password": "wrong"},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert r_a.status_code == 429

    # IP-B has a fresh bucket — should get 401, not 429.
    r_b = client.post(
        "/api/login",
        json={"username": "alice", "password": "wrong"},
        headers={"X-Forwarded-For": "5.6.7.8"},
    )
    assert r_b.status_code == 401


def test_x_forwarded_for_uses_first_entry(client):
    """When X-Forwarded-For has multiple IPs (proxy chain), only the first is used."""
    _register(client)

    # Exhaust the limit for the first IP in the chain.
    for _ in range(_LIMIT):
        client.post(
            "/api/login",
            json={"username": "alice", "password": "wrong"},
            headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.1, 10.0.0.2"},
        )

    # First IP is rate-limited; second entry is a proxy and must not be the key.
    r = client.post(
        "/api/login",
        json={"username": "alice", "password": "wrong"},
        headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.1"},
    )
    assert r.status_code == 429


def test_successful_login_counts_toward_limit(client):
    """Successful logins count toward the rate limit the same as failures."""
    _register(client)

    # Use up _LIMIT - 1 successful logins (each creates a new session).
    for _ in range(_LIMIT - 1):
        client.post("/api/login", json={"username": "alice", "password": "supersecret1"})

    # One more successful login should still work.
    r = client.post("/api/login", json={"username": "alice", "password": "supersecret1"})
    assert r.status_code == 200

    # Now over the limit.
    r2 = client.post("/api/login", json={"username": "alice", "password": "supersecret1"})
    assert r2.status_code == 429
