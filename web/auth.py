"""FastAPI auth router: register, login, logout, game management."""

from __future__ import annotations

import json
import re

import bcrypt as _bcrypt_lib
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from slowapi import Limiter

from web import db, game_manager


def _real_ip(request: Request) -> str:
    """Rate-limit key: first IP in X-Forwarded-For, else the direct client IP."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_real_ip)

router = APIRouter(prefix="/api")

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{1,30}$")
_MIN_PASSWORD = 10


async def _require_auth(session_token: str | None = None):
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await db.get_session_user(session_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


def _set_auth_cookies(response: Response, token: str) -> None:
    response.set_cookie("session_token", token, httponly=True, samesite="strict")
    response.set_cookie("session_token_pub", token, httponly=False, samesite="strict")


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("session_token")
    response.delete_cookie("session_token_pub")


# ── Auth endpoints ────────────────────────────────────────────────────────────


@router.post("/register", status_code=201)
async def register(body: dict):
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    confirm = str(body.get("confirm", ""))

    if not _USERNAME_RE.match(username):
        raise HTTPException(400, "Username must be 1–30 alphanumeric/underscore characters")
    if len(password) < _MIN_PASSWORD:
        raise HTTPException(400, f"Password must be at least {_MIN_PASSWORD} characters")
    if password != confirm:
        raise HTTPException(400, "Passwords do not match")

    pw_hash = _bcrypt_lib.hashpw(password.encode(), _bcrypt_lib.gensalt()).decode()
    uid = await db.create_user(username, pw_hash)
    if uid is None:
        raise HTTPException(409, "Username already taken")

    return {"message": "Account created"}


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, body: dict, response: Response):
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))

    user = await db.get_user_by_name(username)
    if user is None or not _bcrypt_lib.checkpw(password.encode(), user["pw_hash"].encode()):
        raise HTTPException(401, "Invalid username or password")

    token = await db.create_session(user["id"])
    _set_auth_cookies(response, token)
    return {"message": "Logged in", "username": user["username"]}


@router.post("/logout")
async def logout(response: Response, session_token: str | None = Cookie(default=None)):
    if session_token:
        await db.delete_session(session_token)
    _clear_auth_cookies(response)
    return {"message": "Logged out"}


@router.get("/me")
async def me(session_token: str | None = Cookie(default=None)):
    user = await _require_auth(session_token)
    return {"username": user["username"]}


# ── Game management endpoints ─────────────────────────────────────────────────


@router.get("/my-game")
async def my_game(session_token: str | None = Cookie(default=None)):
    user = await _require_auth(session_token)
    meta = await db.get_game_meta(user["id"])
    return {"exists": meta is not None, "updated_at": meta["updated_at"] if meta else None}


@router.post("/new-game", status_code=201)
async def new_game(body: dict, session_token: str | None = Cookie(default=None)):
    user = await _require_auth(session_token)

    if await db.has_game(user["id"]):
        raise HTTPException(409, "You already have an active game. Resume or end it first.")
    if game_manager.get(user["username"]) is not None:
        raise HTTPException(409, "A game session is currently active. Disconnect first.")

    seed = body.get("seed")
    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            raise HTTPException(400, "seed must be an integer")

    from engine.game_state import Engine
    from game.ship import Ship
    from web.save_load import engine_to_dict
    from world.dungeon_gen import generate_player_ship
    from world.galaxy import Galaxy

    engine = Engine()
    engine.galaxy = Galaxy(seed=seed)
    engine.ship = Ship()
    gm, rooms, exit_pos = generate_player_ship(seed=engine.galaxy.seed)
    engine.ship.game_map = gm
    engine.ship.rooms = rooms
    engine.ship.exit_pos = exit_pos
    state_json = json.dumps(engine_to_dict(engine))
    await db.save_game(user["id"], state_json)

    return {"message": "New game created"}


@router.post("/end-game")
async def end_game(session_token: str | None = Cookie(default=None)):
    user = await _require_auth(session_token)

    session = game_manager.get(user["username"])
    treat_as_death = False
    if session is not None:
        import asyncio

        from web.save_load import is_mid_mission, make_death_save_dict

        treat_as_death = is_mid_mission(session.engine)

        # Force-terminate an active session: redirect watchers then cancel the game loop.
        session.force_end = True
        for q in list(session.watcher_queues):
            await q.put(game_manager.PORTAL_REDIRECT)
        if session._gather_task is not None and not session._gather_task.done():
            session._gather_task.cancel()
            # Await the cancellation so the websocket's finally block runs
            # (and calls game_manager.unregister) before we return — otherwise
            # an immediate /api/new-game sees a stale active session and 409s.
            try:
                await session._gather_task
            except (asyncio.CancelledError, Exception):
                pass
        else:
            # Task already done (player disconnected before End Game was clicked).
            # The websocket's finally block already ran with force_end=False, so
            # game_manager.unregister was never called — do it explicitly now.
            game_manager.unregister(user["username"])

        if treat_as_death:
            # Mid-mission abandon = death. Rewrite save instead of deleting,
            # so on reconnect the player lands in GameOverState.
            await db.save_game(user["id"], json.dumps(make_death_save_dict()))
            return {"message": "Mission abandoned"}

    await db.delete_game(user["id"])
    return {"message": "Game ended"}


@router.get("/active-games")
async def active_games(session_token: str | None = Cookie(default=None)):
    user = await _require_auth(session_token)
    result = []
    for username in game_manager.list_active():
        if username == user["username"]:
            continue
        session = game_manager.get(username)
        result.append(
            {
                "username": username,
                "watching_count": len(session.watcher_queues) if session else 0,
            }
        )
    return result
