"""Tests for the force-end-as-death mid-mission flow.

Closes the heal/inventory exploits: a player who disconnects (or hits
``/api/end-game``) while a TacticalState is on the stack must not be allowed
to resume back on the ship at full HP. Their save is converted to a death
record, so reconnect lands them in GameOverState.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import web.db as db
import web.game_manager as gm
from engine.game_state import Engine
from ui.game_over_state import GameOverState


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


def _register_login(client, user="alice", pw="supersecret1"):
    client.post("/api/register", json={"username": user, "password": pw, "confirm": pw})
    client.post("/api/login", json={"username": user, "password": pw})


# ── is_mid_mission ────────────────────────────────────────────────────────────


def test_is_mid_mission_false_when_stack_empty():
    from web.save_load import is_mid_mission

    engine = Engine()
    assert is_mid_mission(engine) is False


def test_is_mid_mission_false_for_strategic_state():
    from ui.strategic_state import StrategicState
    from web.save_load import is_mid_mission
    from world.galaxy import Galaxy

    engine = Engine()
    engine.galaxy = Galaxy(seed=1)
    engine.push_state(StrategicState(engine.galaxy))
    assert is_mid_mission(engine) is False


def test_is_mid_mission_true_when_tactical_on_stack():
    """The mid-mission marker must trigger even when a modal (e.g. inventory) is on top."""
    from ui.inventory_state import InventoryState
    from ui.tactical_state import TacticalState
    from web.save_load import is_mid_mission

    engine = Engine()
    # Build a stack as it would exist mid-mission with the inventory open.
    engine._state_stack.append(TacticalState.__new__(TacticalState))
    engine._state_stack.append(InventoryState())
    assert is_mid_mission(engine) is True


# ── Death save round-trip ────────────────────────────────────────────────────


def test_death_save_dict_loads_into_game_over_state():
    from web.save_load import dict_to_engine, make_death_save_dict

    save = make_death_save_dict(cause="Mission abandoned")
    parsed = json.loads(json.dumps(save))  # ensure JSON-safe

    new_engine = Engine()
    dict_to_engine(parsed, new_engine)

    assert isinstance(new_engine.current_state, GameOverState)
    assert new_engine.current_state.cause == "Mission abandoned"
    assert new_engine.current_state.victory is False


# ── /api/end-game force-end-as-death ─────────────────────────────────────────


def test_end_game_mid_mission_marks_save_as_dead(client):
    """/api/end-game while a TacticalState is on the active session's stack
    must NOT delete the save — it must rewrite it as a death record so the
    player sees GameOverState on next login (closes the heal exploit)."""
    from ui.tactical_state import TacticalState

    _register_login(client)
    client.post("/api/new-game", json={})

    # Simulate an active game session whose engine is mid-mission.
    engine = Engine()
    engine._state_stack.append(TacticalState.__new__(TacticalState))
    gm.register("alice", engine)

    r = client.post("/api/end-game")
    assert r.status_code == 200

    # Save must still exist (death record), not be deleted.
    r2 = client.get("/api/my-game")
    assert r2.json()["exists"] is True

    # Loading it must put the player in GameOverState, not StrategicState.
    user = asyncio.run(db.get_user_by_name("alice"))
    saved = asyncio.run(db.load_game(user["id"]))
    assert saved.get("dead") is True


def test_end_game_strategic_still_deletes_save(client):
    """When NOT mid-mission, /api/end-game continues to delete the save."""
    from ui.strategic_state import StrategicState
    from world.galaxy import Galaxy

    _register_login(client)
    client.post("/api/new-game", json={})

    engine = Engine()
    engine.galaxy = Galaxy(seed=1)
    engine.push_state(StrategicState(engine.galaxy))
    gm.register("alice", engine)

    r = client.post("/api/end-game")
    assert r.status_code == 200

    r2 = client.get("/api/my-game")
    assert r2.json()["exists"] is False


def test_end_game_no_active_session_deletes_save(client):
    """No active session — just delete (current behavior)."""
    _register_login(client)
    client.post("/api/new-game", json={})

    r = client.post("/api/end-game")
    assert r.status_code == 200

    r2 = client.get("/api/my-game")
    assert r2.json()["exists"] is False


# ── Race condition: end-game must wait for websocket cleanup ─────────────────


def test_end_game_awaits_session_cancellation_before_returning(client):
    """Reproduces the bug where create→end→create-again 409s.

    /api/end-game cancels the websocket's gather_task. The websocket's
    finally block (which calls game_manager.unregister) runs asynchronously
    AFTER the cancel. If /api/end-game returns before that finally completes,
    an immediately-following /api/new-game still sees the session and 409s.

    The fix: end-game must `await` the cancelled task so unregister has run
    by the time the response is sent.
    """
    from ui.strategic_state import StrategicState
    from world.galaxy import Galaxy

    _register_login(client)
    client.post("/api/new-game", json={})

    engine = Engine()
    engine.galaxy = Galaxy(seed=1)
    engine.push_state(StrategicState(engine.galaxy))

    session = gm.register("alice", engine)

    # Mimic the real websocket loop: a long-blocking task whose finally
    # block calls game_manager.unregister, exactly like web/server.py.
    cleanup_done = asyncio.Event()

    async def fake_websocket_loop():
        try:
            await asyncio.sleep(3600)
        finally:
            gm.unregister("alice")
            cleanup_done.set()

    # Schedule the task on the same event loop the TestClient uses.
    async def _attach_task():
        session._gather_task = asyncio.create_task(fake_websocket_loop())
        # Give the task one tick to actually start.
        await asyncio.sleep(0)

    asyncio.run(_attach_task())

    # Need to use the same loop the task was created on. Easiest path:
    # run end-game and the verification in a single event loop.
    async def _drive():
        # Re-attach the task on this loop
        session._gather_task = asyncio.create_task(fake_websocket_loop())
        await asyncio.sleep(0)
        # Call end-game via the test client (sync) — but we need to run the
        # async cancel/await path in the same loop. Use a starlette async test.
        from httpx import ASGITransport, AsyncClient

        from web.auth import router

        app = FastAPI()
        app.include_router(router)
        # Copy session cookies from the sync TestClient into the async client.
        cookies = {k: v for k, v in client.cookies.items()}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies=cookies) as ac:
            r = await ac.post("/api/end-game")
            return r.status_code

    status = asyncio.run(_drive())
    assert status == 200

    # The bug: without `await session._gather_task` after cancel, the session
    # stays registered → /api/new-game would 409. The fix makes end-game wait
    # for the websocket's finally block, so the session is gone by return time.
    assert gm.get("alice") is None, "Session should be unregistered when end-game returns"
    assert cleanup_done.is_set(), "Websocket finally block must have run"
