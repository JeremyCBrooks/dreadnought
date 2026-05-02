"""Active game session registry with watcher broadcast support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Engine

# Sentinel put into watcher queues when the game is force-ended via the portal.
# watch_session sends a "portal_redirect" message to the watcher client.
PORTAL_REDIRECT = object()


@dataclass
class GameSession:
    engine: Engine
    username: str
    watcher_queues: list[asyncio.Queue] = field(default_factory=list)
    # tile_state: (x, y) → [ch, fr, fg, fb, br, bg, bb]
    tile_state: dict[tuple[int, int], list[int]] = field(default_factory=dict)
    # Set True when end-game is force-called while session is active.
    force_end: bool = False
    # Task wrapping the engine.run_async + receive_loop gather; used for cancellation.
    _gather_task: asyncio.Task | None = None
    connected: bool = False
    idle_since: datetime | None = None

    async def broadcast(self, frame: dict) -> None:
        """Update tile_state from frame and fan out to all watcher queues."""
        for tile in frame.get("tiles", []):
            x, y = tile[0], tile[1]
            self.tile_state[(x, y)] = tile[2:]

        for q in self.watcher_queues:
            await q.put(frame)

    def make_full_frame(self, w: int, h: int) -> dict:
        """Return a full-frame snapshot of the current tile state for new watchers."""
        tiles = [[x, y, *data] for (x, y), data in self.tile_state.items()]
        return {"type": "full", "w": w, "h": h, "tiles": tiles}


# Module-level registry: username → GameSession
_sessions: dict[str, GameSession] = {}


def register(username: str, engine: Engine) -> GameSession:
    session = GameSession(engine=engine, username=username)
    _sessions[username] = session
    return session


def unregister(username: str) -> None:
    _sessions.pop(username, None)


def get(username: str) -> GameSession | None:
    return _sessions.get(username)


def list_active() -> list[str]:
    return list(_sessions.keys())


def get_idle_usernames(ttl_seconds: float) -> list[str]:
    now = datetime.now(UTC)
    result = []
    for username, session in _sessions.items():
        if session.connected or session.idle_since is None:
            continue
        if (now - session.idle_since).total_seconds() >= ttl_seconds:
            result.append(username)
    return result
