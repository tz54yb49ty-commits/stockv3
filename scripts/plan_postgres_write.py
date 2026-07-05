#!/usr/bin/env python3
"""Print a PostgreSQL write/rollback dry-run plan using sample rows only."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.postgres_write_plan import TABLE_SPECS, build_postgres_write_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True, choices=sorted(TABLE_SPECS))
    parser.add_argument("--source-batch-id", default="sample_batch_20260521_v1")
    parser.add_argument("--source-version", default="sample_batch_20260521_v1")
    args = parser.parse_args()

    plan = build_postgres_write_plan(
        table_name=args.table,
        rows=sample_rows(args.table, source_batch_id=args.source_batch_id, source_version=args.source_version),
    )
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    return 0 if plan.passed else 1


def sample_rows(table: str, *, source_batch_id: str, source_version: str) -> list[dict[str, object]]:
    if table == "common_ingest_batch":
        return [
            {
                "batch_id": source_batch_id,
                "trade_date": "20260521",
                "data_domain": "stock",
                "data_type": "stock_daily",
                "source": "sample",
                "source_version": source_version,
                "status": "pending",
                "started_at": "2026-05-21T00:00:00Z",
            }
        ]
    if table == "common_quality_gate_result":
        return [
            {
                "source_batch_id": source_batch_id,
                "source_version": source_version,
                "data_domain": "stock",
                "data_type": "stock_daily",
                "gate_name": "sample_gate",
                "severity": "P0",
                "status": "passed",
            }
        ]
    if table == "common_trade_calendar":
        return [
            {
                "trade_date": "20260521",
                "exchange": "SSE",
                "is_open": True,
                "source": "sample",
                "source_batch_id": source_batch_id,
                "source_version": source_version,
            }
        ]
    if table == "stock_identity":
        return [with_source({"stock_identity_key": "stock:SZ:000001", "ts_code": "000001.SZ", "code": "000001", "exchange": "SZ", "name": "平安银行"}, source_batch_id, source_version)]
    if table == "index_identity":
        return [with_source({"index_identity_key": "index:SH:000001", "ts_code": "000001.SH", "code": "000001", "exchange": "SH", "name": "上证指数"}, source_batch_id, source_version)]
    if table == "board_identity":
        return [with_source({"board_identity_key": "board:TDX:881002", "board_code": "881002", "board_name": "煤炭开采", "board_type": "tdx_industry"}, source_batch_id, source_version)]
    if table == "stock_daily_bar_fact":
        return [with_source({"stock_identity_key": "stock:SZ:000001", "trade_date": "20260521", "ts_code": "000001.SZ", "code": "000001", "exchange": "SZ", "open": "1", "high": "2", "low": "1", "close": "2"}, source_batch_id, source_version)]
    if table == "stock_daily_basic":
        return [with_source({"stock_identity_key": "stock:SZ:000001", "trade_date": "20260521", "ts_code": "000001.SZ", "code": "000001", "exchange": "SZ"}, source_batch_id, source_version)]
    if table == "index_daily_bar_fact":
        return [with_source({"index_identity_key": "index:SH:000001", "trade_date": "20260521", "code": "000001", "exchange": "SH", "open": "1", "high": "2", "low": "1", "close": "2"}, source_batch_id, source_version)]
    if table == "board_daily_bar_fact":
        return [with_source({"board_identity_key": "board:TDX:881002", "trade_date": "20260521", "board_code": "881002", "board_type": "tdx_industry", "open": "1", "high": "2", "low": "1", "close": "2"}, source_batch_id, source_version)]
    if table == "stock_financial_metrics_fact":
        return [with_source({"stock_identity_key": "stock:SZ:000001", "asof_date": "20260521", "ts_code": "000001.SZ", "code": "000001", "exchange": "SZ"}, source_batch_id, source_version)]
    if table == "index_membership_fact":
        return [with_source({"trade_date": "20260521", "index_identity_key": "index:SH:000300", "stock_identity_key": "stock:SZ:000001", "index_code": "000300", "stock_code": "000001"}, source_batch_id, source_version)]
    if table == "board_membership_fact":
        return [with_source({"trade_date": "20260521", "board_identity_key": "board:TDX:881002", "stock_identity_key": "stock:SZ:000001", "board_code": "881002", "board_type": "tdx_industry", "stock_code": "000001"}, source_batch_id, source_version)]
    raise ValueError(f"unsupported sample table: {table}")


def with_source(row: dict[str, object], source_batch_id: str, source_version: str) -> dict[str, object]:
    row = dict(row)
    row.update({"source": "sample", "source_batch_id": source_batch_id, "source_version": source_version})
    return row


if __name__ == "__main__":
    raise SystemExit(main())
