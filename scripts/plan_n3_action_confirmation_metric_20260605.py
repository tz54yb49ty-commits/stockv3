#!/usr/bin/env python3
"""Generate read-only 20260605 N3 action-confirmation metric artifacts."""

from __future__ import annotations

import argparse
import json
import os
from typing import Sequence

from ashare_v3.market.action_confirmation_metric_materialization_execute import (
    DEFAULT_CONTRACT_MD_PATH_20260605,
    DEFAULT_CONTRACT_PATH_20260605,
    DEFAULT_DRY_RUN_MD_PATH_20260605,
    DEFAULT_DRY_RUN_PATH_20260605,
    DEFAULT_PAYLOAD_PATH_20260605,
    DEFAULT_PREFLIGHT_MD_PATH_20260605,
    DEFAULT_PREFLIGHT_PATH_20260605,
    DEFAULT_ROLLBACK_SQL_PATH_20260605,
    write_20260605_artifacts,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - script import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build read-only 20260605 N3 action-confirmation metric dry-run/preflight artifacts."
    )
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--payload-path", default=DEFAULT_PAYLOAD_PATH_20260605)
    parser.add_argument("--contract-path", default=DEFAULT_CONTRACT_PATH_20260605)
    parser.add_argument("--contract-md-path", default=DEFAULT_CONTRACT_MD_PATH_20260605)
    parser.add_argument("--preflight-path", default=DEFAULT_PREFLIGHT_PATH_20260605)
    parser.add_argument("--preflight-md-path", default=DEFAULT_PREFLIGHT_MD_PATH_20260605)
    parser.add_argument("--dry-run-path", default=DEFAULT_DRY_RUN_PATH_20260605)
    parser.add_argument("--dry-run-md-path", default=DEFAULT_DRY_RUN_MD_PATH_20260605)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH_20260605)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = write_20260605_artifacts(
        dsn=args.dsn,
        payload_path=args.payload_path,
        contract_path=args.contract_path,
        contract_md_path=args.contract_md_path,
        preflight_path=args.preflight_path,
        preflight_md_path=args.preflight_md_path,
        dry_run_path=args.dry_run_path,
        dry_run_md_path=args.dry_run_md_path,
        rollback_sql_path=args.rollback_sql_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("dry_run_result") == "DRY_RUN_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
