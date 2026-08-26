#!/usr/bin/env python3
"""Read-only native-Windows capability gate for TQ HTTP and eltdx."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.windows_n1_sources import (
    EltdxWindowsSource, TQHttpClient, TQWindowsSource, three_year_start,
)


def main() -> int:
    tq = TQWindowsSource(TQHttpClient())
    scopes: dict[str, list[dict[str, object]]] = {market: [] for market in ("5", "9", "11", "12", "14")}
    for row in tq.fetch_market_members():
        scopes[str(row["market"])].append(row)
    if any(not rows for rows in scopes.values()):
        raise RuntimeError(f"empty TQ scope: { {key: len(value) for key, value in scopes.items()} }")
    sector_counts = {}
    for market in ("9", "11", "12", "14"):
        actual_code = str(scopes[market][0].get("Code") or scopes[market][0].get("code"))
        sector_counts[actual_code] = len(tq.fetch_sector_members(actual_code))
    if any(count <= 0 for count in sector_counts.values()):
        raise RuntimeError(f"empty actual-sector membership: {sector_counts}")
    stock_symbol = str(scopes["5"][0].get("Code") or scopes["5"][0].get("code"))
    today = date.today()
    daily_count = len(tq.fetch_daily(
        stock_symbol, asset_kind="stock", start_date=three_year_start(today),
        end_date=today.strftime("%Y%m%d"),
    ))
    if daily_count <= 0:
        raise RuntimeError("empty TQ qfq daily smoke")
    from eltdx import TdxClient
    with TdxClient(timeout=8) as client:
        eltdx = EltdxWindowsSource(client)
        finance_count = len(eltdx.fetch_finance_batch(["sz000001"]))
        report_counts = {key: len(rows) for key, rows in eltdx.fetch_three_reports("000001").items()}
    if finance_count <= 0 or any(count <= 0 for count in report_counts.values()):
        raise RuntimeError("empty eltdx finance smoke")
    print(json.dumps({
        "result": "WINDOWS_N1_SOURCE_CAPABILITY_READY",
        "tq_scope_counts": {key: len(value) for key, value in scopes.items()},
        "actual_sector_counts": sector_counts,
        "stock_qfq_daily": {"symbol": stock_symbol, "row_count": daily_count},
        "eltdx": {"finance_batch_rows": finance_count, "report_rows": report_counts},
        "database_writes": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
