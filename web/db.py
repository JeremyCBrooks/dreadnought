"""Async SQLite helpers for user accounts, sessions, and game saves."""

from __future__ import annotations

import json
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

DB_PATH = Path("dreadnought.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    pw_hash  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS game_saves (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id),
    state_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


@asynccontextmanager
async def _connect():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


async def init_db() -> None:
    async with _connect() as conn:
        await conn.executescript(_SCHEMA)
        await conn.commit()


async def create_user(username: str, pw_hash: str) -> int | None:
    try:
        async with _connect() as conn:
            cur = await conn.execute(
                "INSERT INTO users (username, pw_hash) VALUES (?, ?)",
                (username, pw_hash),
            )
            await conn.commit()
            return cur.lastrowid
    except aiosqlite.IntegrityError:
        return None


async def get_user_by_name(username: str) -> aiosqlite.Row | None:
    async with _connect() as conn:
        async with conn.execute(
            "SELECT id, username, pw_hash FROM users WHERE username = ?", (username,)
        ) as cur:
            return await cur.fetchone()


async def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    async with _connect() as conn:
        await conn.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, time.time()),
        )
        await conn.commit()
    return token


async def get_session_user(token: str) -> aiosqlite.Row | None:
    async with _connect() as conn:
        async with conn.execute(
            """
            SELECT u.id, u.username, u.pw_hash
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ) as cur:
            return await cur.fetchone()


async def delete_session(token: str) -> None:
    async with _connect() as conn:
        await conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        await conn.commit()


async def save_game(user_id: int, state_json: str) -> None:
    async with _connect() as conn:
        await conn.execute(
            """
            INSERT INTO game_saves (user_id, state_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET state_json = excluded.state_json,
                                               updated_at = excluded.updated_at
            """,
            (user_id, state_json, time.time()),
        )
        await conn.commit()


async def load_game(user_id: int) -> dict | None:
    async with _connect() as conn:
        async with conn.execute(
            "SELECT state_json FROM game_saves WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return json.loads(row["state_json"]) if row else None


async def delete_game(user_id: int) -> None:
    async with _connect() as conn:
        await conn.execute("DELETE FROM game_saves WHERE user_id = ?", (user_id,))
        await conn.commit()


async def get_game_meta(user_id: int) -> dict | None:
    """Return {updated_at} for the saved game, or None if no save exists."""
    async with _connect() as conn:
        async with conn.execute(
            "SELECT updated_at FROM game_saves WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return {"updated_at": row["updated_at"]} if row else None


async def has_game(user_id: int) -> bool:
    async with _connect() as conn:
        async with conn.execute(
            "SELECT 1 FROM game_saves WHERE user_id = ?", (user_id,)
        ) as cur:
            return await cur.fetchone() is not None
