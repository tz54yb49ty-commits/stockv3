#!/usr/bin/env python3
"""Run the database-free Windows N6 fixture on loopback only."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

import uvicorn

from ashare_v3.web.windows_n6_fixture_app import create_windows_n6_fixture_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1",))
    parser.add_argument("--port", type=int, default=8786)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    uvicorn.run(
        create_windows_n6_fixture_app(),
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
