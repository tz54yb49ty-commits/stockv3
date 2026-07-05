#!/usr/bin/env python3
"""CLI wrapper for scoped 002831 stock_financial TDX parity repair."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.stock_financial_002831_tdx_parity_repair import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
