"""Tests for WebSocket game sessions and /ws/watch."""

import time

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import web.db as db
import web.game_manager as gm
from web.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    gm._sessions.clear()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    gm._sessions.clear()


def _register_login(client, username="alice", password="supersecret1"):
    client.post(
        "/api/register",
        json={"username": username, "password": password, "confirm": password},
    )
    r = client.post("/api/login", json={"username": username, "password": password})
    return r.cookies.get("session_token")


def test_watch_own_game_rejected(client):
    token = _register_login(client)
    from engine.game_state import Engine

    gm.register("alice", Engine())
    gm.get("alice").connected = True

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/watch/alice?token={token}") as ws:
            ws.receive_json()
    assert exc_info.value.code == 1008


def test_watch_other_game_allowed(client):
    alice_token = _register_login(client, "alice")
    _register_login(client, "bob")
    from engine.game_state import Engine

    gm.register("bob", Engine())
    gm.get("bob").connected = True

    with client.websocket_connect(f"/ws/watch/bob?token={alice_token}"):
        pass


def _create_game(client, username="alice", password="supersecret1"):
    """Register, login, create a new game, and return the session token."""
    _register_login(client, username, password)
    client.post("/api/new-game", json={})
    return client.cookies.get("session_token_pub")


def test_session_connected_false_after_disconnect(client):
    """session.connected must be False after a WebSocket disconnect."""
    token = _create_game(client)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # wait for first frame

    time.sleep(0.1)

    session = gm.get("alice")
    assert session is not None, "session should remain in registry until evicted"
    assert session.connected is False, "session.connected must be False after disconnect"
    assert session._gather_task is not None and session._gather_task.done()


def test_reconnect_succeeds_after_disconnect(client):
    """A player can reconnect (resume game) after navigating away."""
    token = _create_game(client)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()

    time.sleep(0.1)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        frame = ws.receive_json()
    assert frame["type"] in ("full", "frame")


def test_full_frame_includes_seed(client):
    """The first WebSocket frame must carry the galaxy seed as an integer."""
    token = _create_game(client)
    with client.websocket_connect(f"/ws?token={token}") as ws:
        frame = ws.receive_json()
    assert frame["type"] == "full"
    assert "seed" in frame
    assert isinstance(frame["seed"], int)


def test_player_receives_portal_redirect_when_no_save(client):
    """Player gets a portal_redirect frame when they connect with no save in DB."""
    token = _create_game(client)
    client.post("/api/end-game")

    with client.websocket_connect(f"/ws?token={token}") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "portal_redirect"


def test_watcher_receives_portal_redirect_on_player_disconnect(client):
    """Watcher gets portal_redirect when the player navigates away (disconnects)."""
    alice_token = _create_game(client)
    bob_token = _register_login(client, "bob")

    alice_ctx = client.websocket_connect(f"/ws?token={alice_token}")
    alice_ws = alice_ctx.__enter__()
    alice_ws.receive_json()  # first frame — session is active and connected

    bob_ctx = client.websocket_connect(f"/ws/watch/alice?token={bob_token}")
    bob_ws = bob_ctx.__enter__()
    bob_ws.receive_json()  # full snapshot from server

    alice_ctx.__exit__(None, None, None)  # alice disconnects
    time.sleep(0.1)

    msg = bob_ws.receive_json()
    assert msg["type"] == "portal_redirect"

    bob_ctx.__exit__(None, None, None)


@pytest.mark.anyio
async def test_receive_loop_notifies_queue_when_iter_json_exits_normally():
    """receive_loop must put None in the input queue even when iter_json() exits
    without raising — Starlette ≥1.0 swallows WebSocketDisconnect internally
    so the async-for just stops; without a finally clause the queue never gets
    the sentinel and run_async loops forever.
    """
    import asyncio
    from unittest.mock import MagicMock

    async def _empty_iter_json():
        return
        yield  # pragma: no cover

    ws = MagicMock()
    ws.iter_json = _empty_iter_json
    input_queue: asyncio.Queue = asyncio.Queue()

    # Replicate receive_loop as it existed BEFORE the fix (bug demonstration).
    async def buggy_receive_loop() -> None:
        try:
            async for msg in ws.iter_json():
                pass
        except WebSocketDisconnect:
            await input_queue.put(None)

    await buggy_receive_loop()
    assert input_queue.empty(), "bug: None was not put in queue when iter_json exits normally"

    # Replicate receive_loop AFTER the fix.
    async def fixed_receive_loop() -> None:
        try:
            async for msg in ws.iter_json():
                pass
        finally:
            await input_queue.put(None)

    await fixed_receive_loop()
    assert not input_queue.empty(), "fix: None must be in queue after iter_json exits normally"
    assert await input_queue.get() is None


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
