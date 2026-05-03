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
