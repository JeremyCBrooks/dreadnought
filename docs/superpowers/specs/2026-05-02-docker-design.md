# Docker Container Design — Dreadnought Web Server

**Date:** 2026-05-02
**Scope:** Single container running the FastAPI/uvicorn web server for cloud deployment

---

## Overview

Package the Dreadnought web server as a production-ready Docker image for deployment on cloud container platforms (Fly.io, Railway, Render, etc.). The desktop tcod TUI (`main.py`) is excluded — this container serves browser-based play only.

---

## Architecture

### Files Added/Modified

| File | Change |
|---|---|
| `Dockerfile` | New — multi-stage build |
| `.dockerignore` | New — excludes noise from image |
| `.env.example` | New — documents env vars for operators |
| `web/main.py` | Modified — read PORT, LOG_LEVEL from env |
| `web/server.py` or DB init module | Modified — read DATABASE_PATH from env (exact file TBD during impl) |
| `web/server.py` | Modified — add `GET /health` endpoint |

### Multi-Stage Build

**Build stage** (`python:3.12-slim`):
- Copies `pyproject.toml` + `uv.lock`
- Installs uv binary from `ghcr.io/astral-sh/uv:latest`
- Runs `uv sync --frozen --no-dev --no-install-project` to populate `.venv`
- No app source — layer caches cleanly when only code changes

**Runtime stage** (`python:3.12-slim`):
- Copies `.venv` from build stage
- Copies app source (filtered by `.dockerignore`)
- Creates non-root user `appuser`, owns `/app`
- Creates `/app/data/db/` for the database volume mount point
- Sets `ENV PATH="/app/.venv/bin:$PATH"`
- Exposes port 8000
- Includes `HEALTHCHECK` polling `/health` every 30s
- `CMD ["python", "-m", "web.main"]`

### Dockerfile

```dockerfile
# Build stage
FROM python:3.12-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Runtime stage
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . .
RUN useradd -m appuser && mkdir -p /app/data/db && chown -R appuser /app
USER appuser
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/health')"
CMD ["python", "-m", "web.main"]
```

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Uvicorn listen port — cloud platforms inject this |
| `DATABASE_PATH` | `dreadnought.db` | Path to SQLite file |
| `LOG_LEVEL` | `info` | Uvicorn log verbosity |

For cloud deployment, set `DATABASE_PATH=/app/data/db/dreadnought.db` and mount a persistent volume at `/app/data/db`.

---

## Persistence

The SQLite database is excluded from the image via `.dockerignore`. Cloud platforms attach a persistent volume at `/app/data/db`. The `DATABASE_PATH` env var points the app at the correct location.

**Volume mount point:** `/app/data/db`

---

## Health Check

`GET /health` returns `{"status": "ok"}` with HTTP 200. Added as a one-liner route in `web/server.py`. Used by cloud platforms to determine container readiness before routing traffic.

The `HEALTHCHECK` instruction uses Python stdlib (`urllib.request`) — no curl dependency required.

---

## `.dockerignore` Contents

```
.venv/
.git/
__pycache__/
*.pyc
tests/
docs/
*.db
.env*
*.md
main.py
```

---

## Image Size Estimate

~200–300MB (multi-stage eliminates build tools; tcod bundles SDL2 so no extra system libs needed).

---

## Out of Scope

- Desktop TUI (`main.py` / tcod window) — excluded from container
- Nginx reverse proxy / TLS termination — handled by cloud platform
- Horizontal scaling — SQLite is single-writer; one instance per volume
