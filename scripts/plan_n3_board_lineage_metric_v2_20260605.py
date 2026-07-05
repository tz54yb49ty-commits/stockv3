#!/usr/bin/env python3
"""Generate read-only N3 board-lineage metric_v2 artifacts for 20260605."""

from __future__ import annotations

import argparse
import json
import os
from typing import Sequence

from ashare_v3.market.action_confirmation_metric_materialization_execute import (
    DEFAULT_BOARD_LINEAGE_METRIC_V2_CONTRACT_PATH_20260605,
    DEFAULT_BOARD_LINEAGE_METRIC_V2_DRY_RUN_PATH_20260605,
    DEFAULT_BOARD_LINEAGE_METRIC_V2_PAYLOAD_PATH_20260605,
    DEFAULT_BOARD_LINEAGE_METRIC_V2_PREFLIGHT_PATH_20260605,
    DEFAULT_BOARD_LINEAGE_METRIC_V2_ROLLBACK_SQL_PATH_20260605,
    write_20260605_board_lineage_metric_v2_artifacts,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover
    from scripts.check_condition_source_ready import DEFAULT_DSN


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan N3 20260605 board-lineage action-confirmation metric_v2 materialization."
    )
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--payload-path", default=DEFAULT_BOARD_LINEAGE_METRIC_V2_PAYLOAD_PATH_20260605)
    parser.add_argument("--contract-path", default=DEFAULT_BOARD_LINEAGE_METRIC_V2_CONTRACT_PATH_20260605)
    parser.add_argument("--preflight-path", default=DEFAULT_BOARD_LINEAGE_METRIC_V2_PREFLIGHT_PATH_20260605)
    parser.add_argument("--dry-run-path", default=DEFAULT_BOARD_LINEAGE_METRIC_V2_DRY_RUN_PATH_20260605)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_BOARD_LINEAGE_METRIC_V2_ROLLBACK_SQL_PATH_20260605)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = write_20260605_board_lineage_metric_v2_artifacts(
        dsn=args.dsn,
        payload_path=args.payload_path,
        contract_path=args.contract_path,
        preflight_path=args.preflight_path,
        dry_run_path=args.dry_run_path,
        rollback_sql_path=args.rollback_sql_path,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary.get("dry_run_result") == "DRY_RUN_PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
