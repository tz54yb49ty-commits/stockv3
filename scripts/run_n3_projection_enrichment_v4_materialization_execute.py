#!/usr/bin/env python3
"""Run N3 projection enrichment v4 row-level materialization.

Writes require both --execute and --user-confirmed. Missing either flag returns
BLOCKED before opening a database connection.
"""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ashare_v3.market.projection_enrichment_v4_materialization_execute import main


if __name__ == "__main__":
    raise SystemExit(main())
