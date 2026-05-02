"""FastAPI server — authenticated WebSocket game sessions with watch mode."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from engine.game_state import QuitToPortal
from web import db, game_manager
from web.auth import limiter
from web.auth import router as auth_router
from web.key_map import BROWSER_TO_KEYSYM, WebKeyEvent, mod_flags

_IDLE_TTL_SECONDS = 12 * 60 * 60  # 12 hours
_IDLE_CHECK_INTERVAL = 5 * 60  # 5 minutes


async def _evict_idle_sessions(ttl_seconds: float = _IDLE_TTL_SECONDS) -> None:
    from web.save_load import is_mid_mission, make_death_save_dict

    for username in game_manager.get_idle_usernames(ttl_seconds):
        session = game_manager.get(username)
        if session is None:
            continue
        if is_mid_mission(session.engine):
            user = await db.get_user_by_name(username)
            if user is not None:
                state_json = json.dumps(make_death_save_dict("Disconnected too long"))
                await db.save_game(user["id"], state_json)
        game_manager.unregister(username)


async def _idle_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(_IDLE_CHECK_INTERVAL)
        await _evict_idle_sessions()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await db.init_db()
    task = asyncio.create_task(_idle_cleanup_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=_lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(auth_router)


@app.get("/tileset.png")
async def serve_tileset() -> FileResponse:
    return FileResponse("data/terminal10x16_gs_ro.png", media_type="image/png")


# ── Player WebSocket ──────────────────────────────────────────────────────────


@app.websocket("/ws")
async def game_session(ws: WebSocket, token: str = "") -> None:
    user = await db.get_session_user(token)
    if user is None:
        await ws.close(code=1008)
        return

    username: str = user["username"]
    user_id: int = user["id"]

    existing = game_manager.get(username)
    if existing is not None:
        if existing.connected:
            # Genuine duplicate — already playing.
            await ws.close(code=1008)
            return
        # Reconnect: reuse the in-memory engine.
        engine = existing.engine
        session = existing
        session.connected = True
        session.idle_since = None
        session.force_end = False
    else:
        # New connection: load save from DB.
        saved = await db.load_game(user_id)
        if saved is None:
            await ws.accept()
            await ws.send_json({"type": "portal_redirect"})
            await ws.close()
            return

        from engine.game_state import Engine
        from web.save_load import dict_to_engine

        engine = Engine()
        dict_to_engine(saved, engine)
        session = game_manager.register(username, engine)
        session.connected = True

    def _quit_to_portal() -> None:
        raise QuitToPortal()

    engine.on_quit = _quit_to_portal

    await ws.accept()

    input_queue: asyncio.Queue = asyncio.Queue()

    async def send_frame(data: dict) -> None:
        await session.broadcast(data)
        try:
            await ws.send_json(data)
        except (RuntimeError, WebSocketDisconnect):
            pass  # WS already closed; engine stops when it reads None from input_queue

    async def receive_loop() -> None:
        # Starlette ≥1.0 swallows WebSocketDisconnect inside iter_json(), so
        # the async-for exits normally on disconnect.  Use finally so the
        # sentinel always reaches run_async regardless of how the loop ends.
        try:
            async for msg in ws.iter_json():
                code_str = msg.get("code", "")
                key_str = code_str if code_str.startswith("Numpad") else msg.get("key", "")
                sym = BROWSER_TO_KEYSYM.get(key_str)
                if sym is None:
                    continue
                event = WebKeyEvent(
                    sym=sym,
                    mod=mod_flags(
                        shift=msg.get("shift", False),
                        ctrl=msg.get("ctrl", False),
                        alt=msg.get("alt", False),
                    ),
                    type=msg.get("type", "keydown"),
                )
                await input_queue.put(event)
        finally:
            await input_queue.put(None)

    async def _run() -> None:
        await asyncio.gather(engine.run_async(send_frame, input_queue), receive_loop())

    assert session._gather_task is None or session._gather_task.done()
    session._gather_task = asyncio.create_task(_run())
    try:
        await session._gather_task
    except asyncio.CancelledError:
        pass
    except QuitToPortal:
        await db.delete_game(user_id)
        for q in list(session.watcher_queues):
            await q.put(game_manager.PORTAL_REDIRECT)
        try:
            await ws.send_json({"type": "portal_redirect"})
        except Exception:
            pass
        session.force_end = True  # skip auto-save in finally
    finally:
        if session.force_end:
            # Two cases: auth.py force-ended the session (save already handled),
            # or QuitToPortal (save deleted above). Either way: skip auto-save.
            game_manager.unregister(username)
        else:
            from datetime import UTC, datetime

            from web.save_load import engine_to_dict

            session.connected = False
            session.idle_since = datetime.now(UTC)
            for q in session.watcher_queues:
                await q.put(None)
            state_json = json.dumps(engine_to_dict(engine))
            await db.save_game(user_id, state_json)


# ── Watch WebSocket ───────────────────────────────────────────────────────────


@app.websocket("/ws/watch/{username}")
async def watch_session(ws: WebSocket, username: str, token: str = "") -> None:
    user = await db.get_session_user(token)
    if user is None or user["username"] == username:
        await ws.close(code=1008)
        return

    session = game_manager.get(username)
    if session is None or not session.connected:
        await ws.close(code=1008)
        return

    await ws.accept()

    q: asyncio.Queue = asyncio.Queue()
    session.watcher_queues.append(q)

    # Send current full snapshot immediately
    frame = session.make_full_frame(session.engine.CONSOLE_WIDTH, session.engine.CONSOLE_HEIGHT)
    if frame["tiles"]:
        await ws.send_json(frame)

    try:
        while True:
            # Race: frame from game vs client closing the WebSocket.
            # Without this, the loop blocks on q.get() and never notices a disconnect.
            get_task = asyncio.create_task(q.get())
            recv_task = asyncio.create_task(ws.receive())
            done, pending = await asyncio.wait(
                {get_task, recv_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
            if recv_task in done:
                break  # client disconnected or sent unexpected data
            data = get_task.result()
            if data is None:  # player disconnected / session ended
                try:
                    await ws.send_json({"type": "portal_redirect"})
                except Exception:
                    pass
                break
            if data is game_manager.PORTAL_REDIRECT:
                try:
                    await ws.send_json({"type": "portal_redirect"})
                except Exception:
                    pass
                break
            await ws.send_json(data)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if q in session.watcher_queues:
            session.watcher_queues.remove(q)


app.mount("/", StaticFiles(directory="web/static", html=True), name="static")
