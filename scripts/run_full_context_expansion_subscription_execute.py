#!/usr/bin/env python3
"""Execute N3 C1 full-context expansion subscription control-row persist."""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.full_context_expansion_subscription_plan import (
    DEFAULT_DRY_RUN_JSON_PATH,
    DEFAULT_EXECUTE_MD_PATH,
    DEFAULT_EXECUTE_REPORT_PATH,
    run_full_context_expansion_subscription_execute,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute N3 full-context expansion subscription scope.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--dry-run-path", default=DEFAULT_DRY_RUN_JSON_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_EXECUTE_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_EXECUTE_MD_PATH)
    parser.add_argument("--execute", action="store_true", help="Required explicit execute authorization.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required operator confirmation.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        report = run_full_context_expansion_subscription_execute(
            dsn=args.dsn,
            dry_run_path=args.dry_run_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
        )
    except RuntimeError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        quality = report["quality"]
        write_result = report["write_result"]
        print(
            "\n".join(
                [
                    "N3 full-context expansion subscription execute",
                    f"  market_data_run_id={report['market_data_run_id']}",
                    f"  candidate_rows_written={write_result['candidate_rows_written']}",
                    f"  subscription_rows_written={write_result['subscription_rows_written']}",
                    f"  pull_plan_rows_written={write_result['pull_plan_rows_written']}",
                    f"  p0/p1/p2={quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
                    "  market_data_pulled=false market_data_fact_written=false event_outbox_written=false",
                ]
            )
        )
    return 0 if int(report["quality"]["p0_count"]) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

