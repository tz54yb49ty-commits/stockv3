#!/usr/bin/env python3
"""Run the read-only runtime_control dashboard web app."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("ASHARE_V3_RUNTIME_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("ASHARE_V3_RUNTIME_WEB_PORT", "8788"))
    uvicorn.run("ashare_v3.web.runtime_dashboard:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
