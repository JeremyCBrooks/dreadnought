"""FastAPI chat router: public portal chat for logged-in users."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import (
    APIRouter,
    Cookie,
    HTTPException,
    Request,
)

from web import db
from web.auth import _require_auth, limiter

_MAX_BODY = 280
_USER_RATE_WINDOW_SEC = 30.0
_USER_RATE_MAX = 5
_HISTORY_LIMIT = 50

# In-memory state — resets on server restart. That's fine: at worst an attacker
# gets one extra burst of _USER_RATE_MAX after a restart, and slowapi's IP limit
# still applies.
_user_buckets: dict[int, deque[float]] = defaultdict(deque)
_last_body_by_user: dict[int, str] = {}

router = APIRouter(prefix="/api")


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "body": row["body"],
        "created_at": row["created_at"],
    }


def _scrub(body: str) -> tuple[str, str | None]:
    """Return (cleaned, error). error is None on success."""
    # Strip control chars (anything < 0x20, including \n \r \t).
    stripped = "".join(ch for ch in body if ord(ch) >= 0x20)
    # Collapse runs of whitespace to a single space.
    parts = stripped.split()
    cleaned = " ".join(parts)
    if not cleaned:
        return "", "Empty message"
    if len(cleaned) > _MAX_BODY:
        return "", "Message too long"
    return cleaned, None


def _check_user_rate(user_id: int) -> bool:
    """Return True if the user is under the per-user rate limit (sliding window)."""
    now = time.monotonic()
    bucket = _user_buckets[user_id]
    cutoff = now - _USER_RATE_WINDOW_SEC
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _USER_RATE_MAX:
        return False
    bucket.append(now)
    return True


@router.get("/chat")
async def get_chat(since: int | None = None, session_token: str | None = Cookie(default=None)):
    await _require_auth(session_token)
    rows = await db.get_chat_messages(since_id=since, limit=_HISTORY_LIMIT)
    messages = [_row_to_dict(r) for r in rows]
    latest_id = messages[-1]["id"] if messages else (since or 0)
    return {"messages": messages, "latest_id": latest_id}


@router.post("/chat")
@limiter.limit("10/minute")
async def post_chat(request: Request, body: dict, session_token: str | None = Cookie(default=None)):
    user = await _require_auth(session_token)
    raw = str(body.get("body", ""))

    cleaned, err = _scrub(raw)
    if err:
        raise HTTPException(400, err)

    if not _check_user_rate(user["id"]):
        raise HTTPException(429, "Slow down — too many messages")

    if cleaned == _last_body_by_user.get(user["id"]):
        raise HTTPException(400, "Duplicate message")

    new_id = await db.insert_chat_message(user["id"], user["username"], cleaned)
    _last_body_by_user[user["id"]] = cleaned
    return {"id": new_id}
