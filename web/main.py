"""Entry point: start the Dreadnought web server.

Run from the project root:
    python -m web.main
"""

import uvicorn

from web.server import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
