# Mid-Mission Reconnect Design

**Date:** 2026-04-30  
**Status:** Approved

## Problem

When a player navigates from the game to the portal (closing the WebSocket) while mid-mission, the current server treats the disconnect as death. This is punishing and unexpected: players expect to resume exactly where they left off.

The anti-exploit rationale (yanking the WebSocket to escape danger) is outweighed by the poor UX. Explicit game abandonment (`/api/end-game`) already handles the exploit case separately.

## Approach: In-Memory Engine Persistence

Keep the `Engine` object alive in `game_manager` across WebSocket disconnects. On reconnect, reattach a new WebSocket to the existing engine and resume the game loop. No dungeon serialization required.

This is the same approach used by WebBrogue: the game process (or object) outlives the connection; the server reattaches clients to it.

## Out of Scope

Server-restart durability for mid-mission state. If the server restarts while a player is mid-mission (disconnected), they load back to the star map — not dead, but dungeon lost. Full dungeon serialization is a separate future project.

---

## Design

### `GameSession` changes (`web/game_manager.py`)

Add two fields:

- `connected: bool = False` — True while a WebSocket is actively attached
- `idle_since: datetime | None = None` — set when `connected` goes False, cleared on reconnect

The duplicate-connection guard in `game_session()` changes from:
> session exists → reject

to:
> session exists **and** `connected == True` → reject (genuine duplicate)
> session exists **and** `connected == False` → allow (reconnect)

### On WebSocket disconnect (`web/server.py` — `game_session` finally block)

Current behaviour: unregister session, save death state if mid-mission.

New behaviour:
1. Mark `session.connected = False`, set `session.idle_since = datetime.now(UTC)`
2. Save `engine_to_dict(engine)` to DB — no death penalty, regardless of `is_mid_mission`
3. Notify watchers (`await q.put(None)` for each watcher queue) — unchanged
4. Do **not** call `game_manager.unregister()`

### On WebSocket reconnect (`web/server.py` — `game_session`)

At the top of `game_session()`, after auth and before engine construction:

1. Check `game_manager.get(username)`
2. If session exists and `connected == False`:
   - Skip DB load, skip `Engine()` creation
   - Reuse `session.engine`
   - Mark `session.connected = True`, clear `session.idle_since`
   - Create fresh `input_queue` and `send_frame` closure for the new WebSocket
   - Create new `_gather_task` and run loop
3. If session exists and `connected == True`: close with 1008 (duplicate)
4. If no session: load from DB, create engine, register new session (existing path)

### Idle cleanup

A background task (started on app startup) runs on a configurable interval (default: every 5 minutes) and evicts sessions where `idle_since` is older than a configurable TTL (default: 30 minutes).

On eviction:
1. Save `engine_to_dict(engine)` to DB
2. Call `game_manager.unregister(username)`

The idle TTL is long enough that a player briefly visiting the portal and returning will never be evicted.

### `/api/end-game` (`web/auth.py`)

No changes. Explicit game abandonment while mid-mission still treats as death. `force_end = True` path is unchanged.

### `is_mid_mission` / `make_death_save_dict`

`is_mid_mission` is no longer called on natural disconnect. It remains in use only in the `force_end` path (`/api/end-game`). `make_death_save_dict("Connection lost mid-mission")` call in `server.py` is removed.

---

## Files Changed

| File | Change |
|------|--------|
| `web/game_manager.py` | Add `connected`, `idle_since` fields; add idle cleanup task |
| `web/server.py` | Reconnect logic at session start; disconnect saves without death; remove `is_mid_mission` check |
| `web/auth.py` | No changes |

---

## Testing

- Reconnect while on ship: resumes at star map
- Reconnect while mid-mission: resumes mid-dungeon, exact position
- Duplicate connection (already connected): rejected with 1008
- Explicit `/api/end-game` mid-mission: still treated as death
- Idle eviction: session saved and unregistered after TTL; next connect loads from DB normally
- Server startup: idle cleanup background task starts
- Watcher disconnect on player disconnect: unchanged behaviour
