"""Execute N3 20260605 board-lineage scoped subscription control rows."""

from __future__ import annotations

import argparse
import json
import os
from typing import Sequence

from ashare_v3.market.action_confirmation_metric_board_lineage_repair_plan import (
    DEFAULT_PAYLOAD_JSON_PATH,
    DEFAULT_SUBSCRIPTION_CONTRACT_JSON_PATH,
    DEFAULT_SUBSCRIPTION_EXECUTE_REPORT_JSON_PATH,
    DEFAULT_SUBSCRIPTION_EXECUTE_REPORT_MD_PATH,
    DEFAULT_SUBSCRIPTION_PREFLIGHT_JSON_PATH,
    run_board_lineage_scoped_subscription_execute,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover
    from scripts.check_condition_source_ready import DEFAULT_DSN


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute board-lineage scoped N3 subscription control rows."
    )
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-path", required=True, default=DEFAULT_SUBSCRIPTION_CONTRACT_JSON_PATH)
    parser.add_argument("--preflight-path", required=True, default=DEFAULT_SUBSCRIPTION_PREFLIGHT_JSON_PATH)
    parser.add_argument("--payload-path", default=DEFAULT_PAYLOAD_JSON_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_SUBSCRIPTION_EXECUTE_REPORT_JSON_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_SUBSCRIPTION_EXECUTE_REPORT_MD_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_board_lineage_scoped_subscription_execute(
        dsn=args.dsn,
        contract_path=args.contract_path,
        preflight_path=args.preflight_path,
        payload_path=args.payload_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
    )
    if args.json or report.get("result") != "EXECUTE_PASS":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        rows = report.get("actual_rows") or {}
        quality = report.get("quality") or {}
        print(
            "\n".join(
                [
                    "N3 board-lineage scoped subscription execute",
                    f"  subscription_run_id={report.get('subscription_run_id')}",
                    f"  status={report.get('run_status')}",
                    f"  candidate_rows={rows.get('common_market_data_subscription_candidate')}",
                    f"  subscription_rows={rows.get('common_market_data_subscription')}",
                    f"  pull_plan_rows={rows.get('common_market_data_pull_plan')}",
                    f"  P0/P1/P2={quality.get('P0')}/{quality.get('P1')}/{quality.get('P2')}",
                    "  market_data_pulled=false market_data_fact_written=false writes_outbox=false",
                ]
            )
        )
    return 0 if report.get("result") == "EXECUTE_PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
