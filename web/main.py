"""Entry point: start the Dreadnought web server.

Run from the project root:
    python -m web.main
"""

import os

import uvicorn

from web.server import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    log_level = os.environ.get("LOG_LEVEL", "info")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level)
