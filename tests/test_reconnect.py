"""Integration tests for mid-mission reconnect via in-memory engine persistence."""

from __future__ import annotations

import asyncio

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
        # TestClient raises WebSocketDisconnect on __enter__ when the server
        # sends close(1008) before accepting, so we wrap the whole with-block.
        try:
            with client.websocket_connect(f"/ws?token={token}") as ws2:
                ws2.receive_json()
                assert False, "Expected WebSocket to be closed"
        except Exception:
            pass  # expected: server rejected with close code 1008


@pytest.mark.asyncio
async def test_idle_eviction_mid_mission_saves_death(tmp_path, monkeypatch):
    """Idle-evicting a mid-mission session must write a death record."""
    import json
    from datetime import UTC, datetime, timedelta

    from ui.tactical_state import TacticalState
    from web.server import _evict_idle_sessions

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    await db.init_db()
    gm._sessions.clear()

    # Create a user and a game save
    from engine.game_state import Engine
    from web.save_load import engine_to_dict

    await db.create_user("bob", "hashed")
    user = await db.get_user_by_name("bob")
    engine = Engine()
    await db.save_game(user["id"], json.dumps(engine_to_dict(engine)))

    # Register a mid-mission session, already idle past TTL
    session = gm.register("bob", engine)
    session.engine._state_stack.append(TacticalState.__new__(TacticalState))
    session.connected = False
    session.idle_since = datetime.now(UTC) - timedelta(seconds=10)

    await _evict_idle_sessions(ttl_seconds=5)

    try:
        # Session must be unregistered
        assert gm.get("bob") is None

        # Save must be a death record
        saved = await db.load_game(user["id"])
        assert saved is not None
        assert saved.get("dead") is True
    finally:
        gm._sessions.clear()


@pytest.mark.asyncio
async def test_idle_eviction_strategic_does_not_overwrite_save(tmp_path, monkeypatch):
    """Idle-evicting a strategic (non-mission) session leaves the existing save."""
    import json
    from datetime import UTC, datetime, timedelta

    from ui.strategic_state import StrategicState
    from web.server import _evict_idle_sessions
    from world.galaxy import Galaxy

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    await db.init_db()
    gm._sessions.clear()

    from engine.game_state import Engine
    from web.save_load import engine_to_dict

    await db.create_user("carol", "hashed")
    user = await db.get_user_by_name("carol")
    engine = Engine()
    engine.galaxy = Galaxy(seed=42)
    engine.push_state(StrategicState(engine.galaxy))
    original_save = engine_to_dict(engine)
    await db.save_game(user["id"], json.dumps(original_save))

    session = gm.register("carol", engine)
    session.connected = False
    session.idle_since = datetime.now(UTC) - timedelta(seconds=10)

    await _evict_idle_sessions(ttl_seconds=5)

    try:
        assert gm.get("carol") is None

        # Save must NOT be a death record
        saved = await db.load_game(user["id"])
        assert saved is not None
        assert saved.get("dead") is not True
    finally:
        gm._sessions.clear()
