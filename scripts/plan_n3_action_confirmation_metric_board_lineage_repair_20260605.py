"""Generate read-only N3 board lineage repair artifacts for 20260605."""

from __future__ import annotations

import argparse
import json
import os
from typing import Sequence

from ashare_v3.market.action_confirmation_metric_board_lineage_repair_plan import (
    DEFAULT_CONTRACT_JSON_PATH,
    DEFAULT_CONTRACT_MD_PATH,
    DEFAULT_DRY_RUN_JSON_PATH,
    DEFAULT_DRY_RUN_MD_PATH,
    DEFAULT_PAYLOAD_JSON_PATH,
    DEFAULT_PREFLIGHT_JSON_PATH,
    DEFAULT_PREFLIGHT_MD_PATH,
    DEFAULT_ROLLBACK_SQL_PATH,
    write_artifacts,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover
    from scripts.check_condition_source_ready import DEFAULT_DSN


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan N3 20260605 board lineage repair for action-confirmation metric coverage."
    )
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-json-path", default=DEFAULT_CONTRACT_JSON_PATH)
    parser.add_argument("--contract-md-path", default=DEFAULT_CONTRACT_MD_PATH)
    parser.add_argument("--preflight-json-path", default=DEFAULT_PREFLIGHT_JSON_PATH)
    parser.add_argument("--preflight-md-path", default=DEFAULT_PREFLIGHT_MD_PATH)
    parser.add_argument("--dry-run-json-path", default=DEFAULT_DRY_RUN_JSON_PATH)
    parser.add_argument("--dry-run-md-path", default=DEFAULT_DRY_RUN_MD_PATH)
    parser.add_argument("--payload-json-path", default=DEFAULT_PAYLOAD_JSON_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = write_artifacts(
        dsn=args.dsn,
        contract_json_path=args.contract_json_path,
        contract_md_path=args.contract_md_path,
        preflight_json_path=args.preflight_json_path,
        preflight_md_path=args.preflight_md_path,
        dry_run_json_path=args.dry_run_json_path,
        dry_run_md_path=args.dry_run_md_path,
        payload_json_path=args.payload_json_path,
        rollback_sql_path=args.rollback_sql_path,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary.get("result") == "DRY_RUN_PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
