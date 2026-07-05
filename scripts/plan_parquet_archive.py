#!/usr/bin/env python3
"""Print a Parquet archive manifest dry-run plan using sample rows only."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.parquet_archive import DATASET_PARTITION_KEYS, DEFAULT_DATA_ROOT, build_parquet_archive_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=sorted(DATASET_PARTITION_KEYS))
    parser.add_argument("--source-batch-id", required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--schema-version", default="v1")
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--partition-date", default="20260521")
    args = parser.parse_args()

    plan = build_parquet_archive_plan(
        dataset=args.dataset,
        rows=sample_rows(args.dataset, args.partition_date),
        source_batch_id=args.source_batch_id,
        source_version=args.source_version,
        schema_version=args.schema_version,
        data_root=args.data_root,
    )
    print(json.dumps(plan.to_manifest_dict(), ensure_ascii=False, indent=2))
    return 0 if plan.passed else 1


def sample_rows(dataset: str, partition_date: str) -> list[dict[str, str]]:
    if DATASET_PARTITION_KEYS[dataset] == ("asof_date",):
        return [{"stock_identity_key": "stock:SZ:000001", "asof_date": partition_date}]
    if dataset.startswith("board_"):
        return [{"board_identity_key": "board:TDX:881002", "trade_date": partition_date}]
    if dataset.startswith("index_"):
        return [{"index_identity_key": "index:SH:000001", "trade_date": partition_date}]
    return [{"stock_identity_key": "stock:SZ:000001", "trade_date": partition_date}]


if __name__ == "__main__":
    raise SystemExit(main())
