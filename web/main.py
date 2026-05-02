"""Entry point: start the Dreadnought web server.

Run from the project root:
    python -m web.main
"""

import os

import uvicorn

from web.server import app


def _server_config() -> tuple[str, int, str]:
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8000"))
    log_level = os.environ.get("LOG_LEVEL", "info")
    return host, port, log_level


if __name__ == "__main__":
    host, port, log_level = _server_config()
    uvicorn.run(app, host=host, port=port, log_level=log_level)
