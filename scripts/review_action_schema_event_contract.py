#!/usr/bin/env python3
"""Run N5-2 action schema / event contract review.

This script is static and report-only. It does not connect to PostgreSQL,
execute migrations, consume N4 outbox rows, update inbox/checkpoint state,
write action facts/events, start workers, or enter N6.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from ashare_v3.action.schema_event_review import (
    DEFAULT_N5_2_JSON_REPORT_PATH,
    DEFAULT_N5_2_MD_REPORT_PATH,
    DEFAULT_N5_2_SCHEMA_PATH,
    run_n5_schema_event_contract_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run N5-2 action schema/event contract review.")
    parser.add_argument("--schema-path", default=DEFAULT_N5_2_SCHEMA_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N5_2_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N5_2_MD_REPORT_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_n5_schema_event_contract_review(
        schema_path=args.schema_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    schema = report["schema_review"]
    return "\n".join(
        [
            "action schema / event contract review",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  execution_mode={report['execution_mode']}",
            f"  schema_path={report['schema_path']}",
            f"  missing_tables={schema['missing_tables']}",
            f"  missing_required_literals={schema['missing_required_literals']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  migration_executed=false writes_performed=false real_n4_outbox_consumed=false",
            "  common_event_inbox_updated=false consumer_checkpoint_updated=false n6_user_layer_touched=false",
            "  market_data_pulled=false voice_touched=false sim_touched=false real_trade_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
