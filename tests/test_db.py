"""Tests for web/db.py — async SQLite helpers."""

from pathlib import Path

import pytest

# Run all tests in this module with asyncio
pytestmark = pytest.mark.asyncio


@pytest.fixture
def db_module(tmp_path, monkeypatch):
    """Return the db module pointing at a temp database file."""
    import web.db as db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    return db


async def test_init_db_creates_tables(db_module):
    await db_module.init_db()
    async with db_module._connect() as conn:
        async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
            tables = {row[0] async for row in cur}
    assert {"users", "sessions", "game_saves"} <= tables


async def test_create_user_returns_id(db_module):
    await db_module.init_db()
    uid = await db_module.create_user("alice", "hash123")
    assert isinstance(uid, int) and uid > 0


async def test_create_user_duplicate_returns_none(db_module):
    await db_module.init_db()
    await db_module.create_user("alice", "hash1")
    uid2 = await db_module.create_user("alice", "hash2")
    assert uid2 is None


async def test_get_user_by_name(db_module):
    await db_module.init_db()
    await db_module.create_user("bob", "myhash")
    user = await db_module.get_user_by_name("bob")
    assert user is not None
    assert user["username"] == "bob"
    assert user["pw_hash"] == "myhash"


async def test_get_user_by_name_missing(db_module):
    await db_module.init_db()
    assert await db_module.get_user_by_name("nobody") is None


async def test_create_session_returns_token(db_module):
    await db_module.init_db()
    uid = await db_module.create_user("carol", "h")
    token = await db_module.create_session(uid)
    assert isinstance(token, str) and len(token) > 10


async def test_get_session_user(db_module):
    await db_module.init_db()
    uid = await db_module.create_user("dave", "h")
    token = await db_module.create_session(uid)
    user = await db_module.get_session_user(token)
    assert user is not None
    assert user["username"] == "dave"
    assert user["id"] == uid


async def test_get_session_user_invalid_token(db_module):
    await db_module.init_db()
    assert await db_module.get_session_user("bogus-token") is None


async def test_delete_session(db_module):
    await db_module.init_db()
    uid = await db_module.create_user("eve", "h")
    token = await db_module.create_session(uid)
    await db_module.delete_session(token)
    assert await db_module.get_session_user(token) is None


async def test_save_and_load_game(db_module):
    await db_module.init_db()
    uid = await db_module.create_user("frank", "h")
    await db_module.save_game(uid, '{"seed": 42}')
    data = await db_module.load_game(uid)
    assert data == {"seed": 42}


async def test_load_game_missing(db_module):
    await db_module.init_db()
    uid = await db_module.create_user("grace", "h")
    assert await db_module.load_game(uid) is None


async def test_save_game_overwrites(db_module):
    await db_module.init_db()
    uid = await db_module.create_user("hank", "h")
    await db_module.save_game(uid, '{"v": 1}')
    await db_module.save_game(uid, '{"v": 2}')
    data = await db_module.load_game(uid)
    assert data["v"] == 2


async def test_delete_game(db_module):
    await db_module.init_db()
    uid = await db_module.create_user("iris", "h")
    await db_module.save_game(uid, '{"x": 1}')
    await db_module.delete_game(uid)
    assert await db_module.load_game(uid) is None


async def test_has_game(db_module):
    await db_module.init_db()
    uid = await db_module.create_user("jack", "h")
    assert not await db_module.has_game(uid)
    await db_module.save_game(uid, "{}")
    assert await db_module.has_game(uid)


def test_db_path_default_is_dreadnought_db():
    import importlib
    import sys

    sys.modules.pop("web.db", None)
    fresh = importlib.import_module("web.db")
    assert fresh.DB_PATH == Path("dreadnought.db")
    sys.modules.pop("web.db", None)
    importlib.import_module("web.db")  # restore cached module


def test_db_path_reads_from_env(monkeypatch, tmp_path):
    import importlib
    import sys
    db_path = str(tmp_path / "custom.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    sys.modules.pop("web.db", None)
    fresh = importlib.import_module("web.db")
    assert fresh.DB_PATH == Path(db_path)
    sys.modules.pop("web.db", None)
    importlib.import_module("web.db")  # restore cached module
