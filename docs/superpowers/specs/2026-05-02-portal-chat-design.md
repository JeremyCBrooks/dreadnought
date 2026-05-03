# Portal Public Chat — Design

**Date:** 2026-05-02
**Status:** Approved, ready for implementation planning

## Goal

Add a basic public chat to the portal page. Visible and usable only to logged-in players. No private messages — one shared room. Layered bot/spam protection.

## Scope

- **In scope:** Portal-only chat sidebar (`portal.html`); SQLite persistence; 5 s polling; rate limiting (per-IP + per-user); content scrub; duplicate guard; 30-day retention.
- **Out of scope (v1):** WebSocket push; private messages; multiple rooms; moderation tools (delete/ban/mute UI); message edits; mentions; emoji/markdown rendering; mobile collapse UI; account-age gates; CAPTCHA.

## Architecture

A right-aligned chat sidebar on `portal.html`, behind the same auth check the rest of the portal uses. Two new REST endpoints, one new SQLite table, and a small client polling loop reusing the existing 5 s `setInterval`. No new long-lived connections.

```
┌─ portal.html ──────────────────────────────┬─ chat sidebar ─┐
│  Header (user-bar, logout)                 │ Public Chat    │
│  ── My Game section                        │ ┌────────────┐ │
│  ── Active Players section                 │ │ chat log   │ │
│                                            │ │ (scroll)   │ │
│                                            │ └────────────┘ │
│                                            │ [textarea]Send │
│                                            │ 0/280          │
└────────────────────────────────────────────┴────────────────┘
```

## Components

### `web/db.py` additions

Schema added to `_SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    username   TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_created_at ON chat_messages(created_at);
```

`username` is denormalized onto the row so deleted users' history still renders cleanly without a join.

Functions:

- `insert_chat_message(user_id: int, username: str, body: str) -> int` — inserts and returns the new id.
- `get_chat_messages(since_id: int | None, limit: int) -> list[Row]` — when `since_id is None`, returns the last `limit` rows ordered ascending by id; when set, returns rows with `id > since_id` ordered ascending.
- `delete_old_chat_messages(max_age_seconds: float) -> int` — used by the cleanup loop.

### `web/chat.py` (new)

```python
router = APIRouter(prefix="/api")

_MAX_BODY = 280
_USER_RATE_WINDOW_SEC = 30.0
_USER_RATE_MAX = 5
_HISTORY_LIMIT = 50

_user_buckets: dict[int, deque[float]] = defaultdict(deque)
_last_body_by_user: dict[int, str] = {}
```

Helpers:

- `_scrub(body: str) -> tuple[str, str | None]` — returns `(cleaned, error)`. Steps: strip control chars (anything `< 0x20`, including newlines — chat is single-line), collapse whitespace runs to single spaces, trim. If the result is empty, return `("", "Empty message")`. If `len(cleaned) > _MAX_BODY`, return `("", "Message too long")`. Otherwise return `(cleaned, None)`.
- `_check_user_rate(user_id: int) -> bool` — sliding-window over `_user_buckets[user_id]`: drop timestamps older than `_USER_RATE_WINDOW_SEC`; if remaining count ≥ `_USER_RATE_MAX` return `False`; else append `now` and return `True`.

Endpoints:

- `GET /api/chat?since=<int>` — auth required. Returns `{messages: [{id, username, body, created_at}, ...], latest_id: int}`. No `since` returns last 50 oldest→newest.
- `POST /api/chat` — auth required, decorated `@limiter.limit("10/minute")`. Body `{body: str}`. Pipeline order:
  1. (slowapi runs IP limit first)
  2. Auth (401 if missing)
  3. `cleaned, err = _scrub(body)` — if `err`, return 400 with `detail=err` ("Empty message" or "Message too long").
  4. `_check_user_rate(user_id)` → 429 "Slow down — too many messages" if over limit.
  5. Duplicate guard: `if cleaned == _last_body_by_user.get(user_id)` → 400 "Duplicate message".
  6. `db.insert_chat_message(user_id, username, cleaned)`; update `_last_body_by_user[user_id] = cleaned`.

  Returns `{id, created_at}`.

### `web/server.py` changes

- Import and `app.include_router(chat_router)` next to the existing `auth_router`.
- New `_chat_cleanup_loop()` — sleeps `24 * 3600`, calls `db.delete_old_chat_messages(30 * 86400)`, repeats. Started and cancelled in `_lifespan` alongside the existing two cleanup loops.

### `web/static/portal.html` changes

- Restructure the body into a flex two-column layout: existing `<header>` + the two `<section>`s in a left column; new `<aside id="chat-sidebar">` as the right column with fixed width ~320 px.
- Sidebar contents: `<h2>Public Chat</h2>`, `<div id="chat-log">` (scrollable), `<form id="chat-form">` containing `<textarea id="chat-input" maxlength="280" rows="2">` + `<button>Send</button>`, `<div id="chat-meta"><span id="chat-count">0/280</span><span id="chat-error"></span></div>`.
- CSS additions: column layout, message row styling (`<time> <strong>username</strong>: body`), `overflow-wrap: anywhere` on bodies, red color on `#chat-count` when `>= 260`, fade-out on `#chat-error`.

### `web/static/portal.js` changes

State:

```js
let chatLatestId = 0;
```

Functions:

- `renderChatMessages(msgs, append)` — builds `<div class="chat-msg">` rows; if `append` and the user was scroll-pinned (within 30 px of bottom) before append, scrolls to bottom; on initial render always scrolls to bottom.
- `refreshChat()` — `GET /api/chat?since=<chatLatestId>` (or no param if `chatLatestId === 0`); on success, updates `chatLatestId` to `latest_id` and renders. Silently ignores non-OK responses other than 401 (which `api()` already handles).
- `sendChat(e)` — `e.preventDefault()`; reads textarea; POSTs `/api/chat`; on OK, clears textarea and resets counter; on 4xx, displays `detail` in `#chat-error` for 5 s; on network error, shows "Send failed — try again".
- `updateChatCount()` — `input` listener on textarea, updates `#chat-count` and toggles red class.
- Wire `refreshChat()` into `init()` (once on load) and into the existing `setInterval(refreshActivePlayers, 5000)` (so both poll on the same tick).
- Submit on Enter; Shift+Enter inserts newline (which `_scrub` strips server-side anyway, so effectively just a soft line wrap).

## Data Flow

**On portal load:**
1. `init()` runs `/api/me` → 401 redirects to `/`.
2. `init()` calls `refreshChat()` once with no `since`. Server returns last 50 messages ascending. Client renders, sets `chatLatestId` to the max id, scrolls to bottom.
3. The 5 s `setInterval` tick fires both `refreshActivePlayers()` and `refreshChat()`. `refreshChat()` always passes `since=<chatLatestId>`. Server returns only newer rows (often `[]`). Client appends, bumps `chatLatestId`.

**On send:**
1. User types, presses Enter or clicks Send. `sendChat()` runs.
2. Server pipeline: IP limit → auth → length check → scrub → user rate → duplicate → insert → update last-body cache.
3. On 2xx: textarea cleared. Message appears within ≤5 s on the next poll. No optimistic insert in v1.
4. On 4xx: `detail` shown in `#chat-error`.

**Cleanup loop:**
- `_chat_cleanup_loop()` sleeps 24 h, then deletes rows where `created_at < now - 30 * 86400`.

## Spam Protection Stack

| Layer | Mechanism | Limit |
|------|-----------|-------|
| A. Per-user rate | In-memory sliding window on `user_id` | 5 messages / 30 s |
| B. Per-IP rate | Existing `slowapi` limiter, IP-keyed via `_real_ip` | 10 POST /api/chat / minute |
| C. Content scrub | `_scrub()`: trim, control-char strip, whitespace collapse, length cap | ≤ 280 chars after trim |
| D. Duplicate guard | In-memory `_last_body_by_user[user_id]` compared to scrubbed body | Block exact match against immediately previous message |

A and D reset on server restart — acceptable; an attacker buys at most one extra burst of 5, and slowapi (B) keeps applying.

## Error Handling & Edge Cases

- **Unauth on poll:** 401 → existing `api()` helper redirects to `/`.
- **Network/server error on poll:** silently swallowed; next tick retries.
- **Network error on send:** "Send failed — try again" in `#chat-error`; textarea contents preserved.
- **Race on `since`:** `id INTEGER PRIMARY KEY` is monotonic; `WHERE id > ?` with commit-per-insert is safe under concurrent writers — a poll mid-insert simply picks the row up next tick.
- **User deleted while messages exist:** denormalized `username` column means rows still render correctly; no join required.
- **Server restart:** in-memory rate buckets and duplicate guard reset to empty. IP limit (slowapi, also in-memory but shared with the rest of the app) likewise resets.
- **Long unbroken strings:** `overflow-wrap: anywhere` on body cells prevents sidebar blowout.
- **XSS:** all rendered fields routed through the existing `escHtml()` helper.
- **Empty page state:** placeholder "No messages yet" when log is empty.
- **Auto-scroll:** capture `wasPinned = (log.scrollHeight - log.scrollTop - log.clientHeight) < 30` before append; only scroll to bottom if `wasPinned`. Prevents yanking users reading scrollback.
- **Newlines in input:** stripped by `_scrub`; chat is single-line by intent.

## Testing

Tests written first per project TDD convention. New files under `tests/web/`.

### `tests/web/test_chat_db.py`

- `insert_chat_message` returns increasing ids; row reads back with same body, username, user_id.
- `get_chat_messages(since_id=None, limit=50)` returns last 50 ascending when >50 rows exist.
- `get_chat_messages(since_id=N, limit=50)` returns only rows with `id > N`, ascending.
- `delete_old_chat_messages(cutoff_seconds)` removes only rows older than the cutoff.
- After deleting the user, their old messages still readable via `get_chat_messages` (denormalized `username` survives).

### `tests/web/test_chat_api.py`

Using FastAPI `TestClient` with an auth-cookie fixture:

- Unauthed `GET /api/chat` → 401; authed → 200 with `messages` and `latest_id`.
- Unauthed `POST /api/chat` → 401.
- POST with body `""`, `"   "` → 400 "Empty message".
- POST with body 281 chars → 400 "Message too long".
- POST with body containing control chars (`\x01`, `\x07`) → 200; stored body has them stripped.
- POST 6 valid messages back-to-back from one user → first 5 succeed, 6th returns 429 "Slow down".
- POST identical body twice in a row → second returns 400 "Duplicate message".
- POST `"hi"`, `"there"`, `"hi"` → all three succeed (duplicate guard is "vs immediately previous", not "ever").
- IP rate limit: 11 POSTs in a minute (across distinct authed users sharing one IP) → 11th returns 429 (slowapi).
- After insert, `GET /api/chat?since=<previous_latest_id>` returns just the new row.

### `tests/web/test_chat_cleanup.py`

- Insert rows with `created_at` 31 days ago and "now"; call `delete_old_chat_messages(30 * 86400)`; only the recent row remains.

No client-side JS tests (consistent with the rest of `web/static/`).

## Files Touched

| File | Change |
|------|--------|
| `web/db.py` | + schema, + 3 functions |
| `web/chat.py` | new — router, scrub, rate-limit helpers |
| `web/server.py` | + include_router, + cleanup loop in `_lifespan` |
| `web/static/portal.html` | restructure to 2-column flex, add chat sidebar markup + CSS |
| `web/static/portal.js` | + chat polling, send handler, counter |
| `tests/web/test_chat_db.py` | new |
| `tests/web/test_chat_api.py` | new |
| `tests/web/test_chat_cleanup.py` | new |

## Constants Summary

- `_HISTORY_LIMIT = 50` (messages on first load)
- `_MAX_BODY = 280` (chars after trim)
- `_USER_RATE_MAX = 5` per `_USER_RATE_WINDOW_SEC = 30.0`
- IP limit: `10/minute` on `POST /api/chat` (slowapi)
- Poll cadence: 5 s (existing portal interval, reused)
- Retention: 30 days; cleanup sweep every 24 h
