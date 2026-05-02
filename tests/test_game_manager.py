"""Tests for web/game_manager.py — active session registry."""

import asyncio
from datetime import UTC, datetime

import pytest

from engine.game_state import Engine


def make_engine() -> Engine:
    return Engine()


# ── register / unregister / get ───────────────────────────────────────────────


def test_register_returns_session():
    import web.game_manager as gm

    gm._sessions.clear()
    engine = make_engine()
    session = gm.register("alice", engine)
    assert session.engine is engine
    assert session.username == "alice"
    assert session.watcher_queues == []
    assert session.tile_state == {}
    gm._sessions.clear()


def test_get_returns_registered_session():
    import web.game_manager as gm

    gm._sessions.clear()
    engine = make_engine()
    gm.register("bob", engine)
    session = gm.get("bob")
    assert session is not None
    assert session.username == "bob"
    gm._sessions.clear()


def test_get_missing_returns_none():
    import web.game_manager as gm

    gm._sessions.clear()
    assert gm.get("nobody") is None


def test_unregister_removes_session():
    import web.game_manager as gm

    gm._sessions.clear()
    engine = make_engine()
    gm.register("carol", engine)
    gm.unregister("carol")
    assert gm.get("carol") is None


def test_list_active():
    import web.game_manager as gm

    gm._sessions.clear()
    gm.register("dave", make_engine())
    gm.register("eve", make_engine())
    active = gm.list_active()
    assert set(active) == {"dave", "eve"}
    gm._sessions.clear()


def test_list_active_empty():
    import web.game_manager as gm

    gm._sessions.clear()
    assert gm.list_active() == []


# ── frame broadcast ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_updates_tile_state():
    import web.game_manager as gm

    gm._sessions.clear()
    engine = make_engine()
    session = gm.register("frank", engine)

    frame = {"type": "full", "w": 10, "h": 5, "tiles": [[0, 0, 65, 255, 255, 255, 0, 0, 0]]}
    await session.broadcast(frame)

    assert session.tile_state == {(0, 0): [65, 255, 255, 255, 0, 0, 0]}
    gm._sessions.clear()


@pytest.mark.asyncio
async def test_broadcast_sends_to_watcher_queues():
    import web.game_manager as gm

    gm._sessions.clear()
    engine = make_engine()
    session = gm.register("grace", engine)

    q: asyncio.Queue = asyncio.Queue()
    session.watcher_queues.append(q)

    frame = {"type": "frame", "w": 10, "h": 5, "tiles": []}
    await session.broadcast(frame)

    assert not q.empty()
    sent = await q.get()
    assert sent == frame
    gm._sessions.clear()


@pytest.mark.asyncio
async def test_broadcast_multiple_watchers():
    import web.game_manager as gm

    gm._sessions.clear()
    engine = make_engine()
    session = gm.register("hank", engine)

    q1: asyncio.Queue = asyncio.Queue()
    q2: asyncio.Queue = asyncio.Queue()
    session.watcher_queues.extend([q1, q2])

    frame = {"type": "frame", "tiles": []}
    await session.broadcast(frame)

    assert not q1.empty()
    assert not q2.empty()
    gm._sessions.clear()


# ── initial snapshot for new watchers ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_make_full_frame_empty_when_no_tiles():
    import web.game_manager as gm

    gm._sessions.clear()
    engine = make_engine()
    session = gm.register("iris", engine)

    frame = session.make_full_frame(160, 50)
    assert frame["type"] == "full"
    assert frame["w"] == 160
    assert frame["h"] == 50
    assert frame["tiles"] == []
    gm._sessions.clear()


@pytest.mark.asyncio
async def test_make_full_frame_returns_accumulated_tiles():
    import web.game_manager as gm

    gm._sessions.clear()
    engine = make_engine()
    session = gm.register("jack", engine)

    # Simulate two frames building up tile_state
    await session.broadcast({"type": "full", "w": 5, "h": 5, "tiles": [[1, 2, 65, 255, 0, 0, 0, 0, 0]]})
    await session.broadcast({"type": "frame", "w": 5, "h": 5, "tiles": [[3, 4, 66, 0, 255, 0, 0, 0, 0]]})

    frame = session.make_full_frame(5, 5)
    assert frame["type"] == "full"
    coords = {(t[0], t[1]) for t in frame["tiles"]}
    assert (1, 2) in coords
    assert (3, 4) in coords
    gm._sessions.clear()


# ── connected / idle_since fields ────────────────────────────────────────────


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
    now = datetime.now(UTC)
    session.idle_since = now
    assert session.idle_since == now
    gm._sessions.clear()


# ── get_idle_usernames ────────────────────────────────────────────────────────


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

    gm._sessions.clear()
    session = gm.register("alice", make_engine())
    session.connected = False
    session.idle_since = datetime.now(UTC)
    result = gm.get_idle_usernames(ttl_seconds=3600)
    assert "alice" not in result
    gm._sessions.clear()


def test_get_idle_usernames_includes_expired():
    from datetime import timedelta

    import web.game_manager as gm

    gm._sessions.clear()
    session = gm.register("alice", make_engine())
    session.connected = False
    session.idle_since = datetime.now(UTC) - timedelta(seconds=3601)
    result = gm.get_idle_usernames(ttl_seconds=3600)
    assert "alice" in result
    gm._sessions.clear()


def test_get_idle_usernames_multiple_sessions():
    from datetime import UTC, datetime, timedelta

    import web.game_manager as gm

    gm._sessions.clear()

    # connected — must not be evicted
    s1 = gm.register("connected_user", make_engine())
    s1.connected = True

    # disconnected but recent — must not be evicted
    s2 = gm.register("recent_user", make_engine())
    s2.connected = False
    s2.idle_since = datetime.now(UTC) - timedelta(seconds=100)

    # disconnected and expired — must be evicted
    s3 = gm.register("idle_user", make_engine())
    s3.connected = False
    s3.idle_since = datetime.now(UTC) - timedelta(seconds=1801)

    result = gm.get_idle_usernames(ttl_seconds=1800)
    assert "connected_user" not in result
    assert "recent_user" not in result
    assert "idle_user" in result
    gm._sessions.clear()
