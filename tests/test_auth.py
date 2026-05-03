"""Tests for web/auth.py — FastAPI auth router."""

import asyncio

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import web.db as db
import web.game_manager as gm


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    asyncio.run(db.init_db())
    gm._sessions.clear()

    from web.auth import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    gm._sessions.clear()


def _register(client, username="alice", password="supersecret1", confirm=None):
    return client.post(
        "/api/register",
        json={"username": username, "password": password, "confirm": confirm or password},
    )


def _login(client, username="alice", password="supersecret1"):
    return client.post("/api/login", json={"username": username, "password": password})


# ── Register ──────────────────────────────────────────────────────────────────


def test_register_success(client):
    r = _register(client)
    assert r.status_code == 201


def test_register_duplicate_username(client):
    _register(client)
    r = _register(client)
    assert r.status_code == 409


def test_register_invalid_username_special_chars(client):
    r = _register(client, username="alice!")
    assert r.status_code == 400


def test_register_invalid_username_too_long(client):
    r = _register(client, username="a" * 31)
    assert r.status_code == 400


def test_register_invalid_username_too_short(client):
    r = _register(client, username="abcd")
    assert r.status_code == 400


def test_register_username_minimum_5_chars(client):
    r = _register(client, username="abcde")
    assert r.status_code == 201


def test_register_password_too_short(client):
    r = _register(client, password="short", confirm="short")
    assert r.status_code == 400


def test_register_password_mismatch(client):
    r = _register(client, password="supersecret1", confirm="different123")
    assert r.status_code == 400


# ── Login ─────────────────────────────────────────────────────────────────────


def test_login_success(client):
    _register(client)
    r = _login(client)
    assert r.status_code == 200
    assert r.json()["username"] == "alice"
    assert "session_token" in r.cookies


def test_login_wrong_password(client):
    _register(client)
    r = client.post("/api/login", json={"username": "alice", "password": "wrongpassword"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = _login(client, username="nobody")
    assert r.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────


def test_logout_clears_cookies(client):
    _register(client)
    _login(client)
    r = client.post("/api/logout")
    assert r.status_code == 200
    # After logout, /me should return 401
    r2 = client.get("/api/me")
    assert r2.status_code == 401


def test_logout_without_session_ok(client):
    r = client.post("/api/logout")
    assert r.status_code == 200


# ── /me ───────────────────────────────────────────────────────────────────────


def test_me_returns_username(client):
    _register(client)
    _login(client)
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_me_unauthenticated(client):
    r = client.get("/api/me")
    assert r.status_code == 401


# ── /my-game ──────────────────────────────────────────────────────────────────


def test_my_game_no_save(client):
    _register(client)
    _login(client)
    r = client.get("/api/my-game")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is False
    assert data["updated_at"] is None


def test_my_game_with_save(client):
    _register(client)
    _login(client)
    client.post("/api/new-game", json={})
    r = client.get("/api/my-game")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["updated_at"] is not None


def test_my_game_unauthenticated(client):
    r = client.get("/api/my-game")
    assert r.status_code == 401


# ── /new-game ─────────────────────────────────────────────────────────────────


def test_new_game_creates_save(client):
    _register(client)
    _login(client)
    r = client.post("/api/new-game", json={})
    assert r.status_code == 201


def test_new_game_with_seed(client):
    _register(client)
    _login(client)
    r = client.post("/api/new-game", json={"seed": 42})
    assert r.status_code == 201


def test_new_game_invalid_seed(client):
    _register(client)
    _login(client)
    r = client.post("/api/new-game", json={"seed": "notanint"})
    assert r.status_code == 400


def test_new_game_duplicate_rejected(client):
    _register(client)
    _login(client)
    client.post("/api/new-game", json={})
    r = client.post("/api/new-game", json={})
    assert r.status_code == 409


def test_new_game_unauthenticated(client):
    r = client.post("/api/new-game", json={})
    assert r.status_code == 401


def test_new_game_generates_ship_map(client, monkeypatch):
    """POST /api/new-game calls generate_player_ship and populates all three Ship fields."""
    from world import dungeon_gen
    from world.game_map import GameMap

    call_log: list[dict] = []
    _orig = dungeon_gen.generate_player_ship

    def _spy(seed, **kwargs):
        result = _orig(seed, **kwargs)
        call_log.append({"seed": seed, "map": result[0]})
        return result

    monkeypatch.setattr(dungeon_gen, "generate_player_ship", _spy)

    _register(client)
    _login(client)
    r = client.post("/api/new-game", json={"seed": 42})
    assert r.status_code == 201
    assert len(call_log) == 1
    assert call_log[0]["seed"] == 42
    assert isinstance(call_log[0]["map"], GameMap)
    assert call_log[0]["map"].hull_breaches == []


# ── /end-game ─────────────────────────────────────────────────────────────────


def test_end_game_removes_save(client):
    _register(client)
    _login(client)
    client.post("/api/new-game", json={})
    r = client.post("/api/end-game")
    assert r.status_code == 200
    # Save should be gone
    r2 = client.get("/api/my-game")
    assert r2.json()["exists"] is False


def test_end_game_no_save_ok(client):
    _register(client)
    _login(client)
    r = client.post("/api/end-game")
    assert r.status_code == 200


def test_end_game_unauthenticated(client):
    r = client.post("/api/end-game")
    assert r.status_code == 401


def _inject_idle_session(username: str) -> None:
    """Register a disconnected session in game_manager, as exists after a player
    navigates away from play.html (task is done, connected=False)."""
    from unittest.mock import MagicMock

    from engine.game_state import Engine

    session = gm.register(username, Engine())
    session.connected = False
    task = MagicMock()
    task.done.return_value = True
    session._gather_task = task


def test_end_game_removes_session_from_registry_when_task_done(client):
    """end-game must unregister the session even when _gather_task is already done.

    Regression: if a player disconnects (navigates to portal) and then clicks
    End Game, the _gather_task is already done so the cancel path is skipped.
    game_manager.unregister was never called, leaving the session in the
    registry and blocking any subsequent /api/new-game with 409.
    """
    _register(client)
    _login(client)
    client.post("/api/new-game", json={})
    _inject_idle_session("alice")

    r = client.post("/api/end-game")
    assert r.status_code == 200

    assert gm.get("alice") is None, "session must be removed from registry after end-game"


def test_new_game_allowed_after_end_game_with_idle_session(client):
    """After end-game cleans up an idle session, new-game must succeed (not 409)."""
    _register(client)
    _login(client)
    client.post("/api/new-game", json={})
    _inject_idle_session("alice")

    client.post("/api/end-game")
    r = client.post("/api/new-game", json={})
    assert r.status_code == 201, f"new-game after end-game should succeed: {r.json()}"


# ── /active-games ─────────────────────────────────────────────────────────────


def test_active_games_empty(client):
    _register(client)
    _login(client)
    r = client.get("/api/active-games")
    assert r.status_code == 200
    assert r.json() == []


def test_active_games_shows_sessions(client):
    _register(client, username="alice")
    _register(client, username="bobby")
    _login(client)
    from engine.game_state import Engine

    gm.register("bobby", Engine())
    r = client.get("/api/active-games")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["username"] == "bobby"
    assert data[0]["watching_count"] == 0
    gm._sessions.clear()


def test_active_games_excludes_own_session(client):
    _register(client)
    _login(client)
    from engine.game_state import Engine

    gm.register("alice", Engine())
    r = client.get("/api/active-games")
    assert r.status_code == 200
    usernames = [p["username"] for p in r.json()]
    assert "alice" not in usernames
    gm._sessions.clear()


def test_active_games_shows_others_not_self(client):
    _register(client)
    _register(client, username="bobby")
    _login(client)
    from engine.game_state import Engine

    gm.register("alice", Engine())
    gm.register("bobby", Engine())
    r = client.get("/api/active-games")
    assert r.status_code == 200
    usernames = [p["username"] for p in r.json()]
    assert "bobby" in usernames
    assert "alice" not in usernames
    gm._sessions.clear()


def test_active_games_unauthenticated(client):
    r = client.get("/api/active-games")
    assert r.status_code == 401
