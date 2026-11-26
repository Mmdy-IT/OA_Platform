from __future__ import annotations

import os

import uvicorn

from backend.app import app


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("OA_HOST", "0.0.0.0"),
        port=int(os.getenv("OA_PORT", "8000")),
        log_level=os.getenv("OA_LOG_LEVEL", "info"),
    )
