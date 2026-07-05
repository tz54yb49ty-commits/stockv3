#!/usr/bin/env python3
"""Run N5-3 action schema migration review.

This script is static and report-only. It does not connect to PostgreSQL,
execute migrations, consume N4 outbox rows, update inbox/checkpoint state,
write action facts/events, start workers, or enter N6.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from ashare_v3.action.schema_migration_review import (
    DEFAULT_N5_3_JSON_REPORT_PATH,
    DEFAULT_N5_3_MD_REPORT_PATH,
    DEFAULT_N5_3_ROLLBACK_PREVIEW_PATH,
    DEFAULT_N5_3_SCHEMA_PATH,
    run_n5_action_schema_migration_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run N5-3 action schema migration review.")
    parser.add_argument("--schema-path", default=DEFAULT_N5_3_SCHEMA_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N5_3_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N5_3_MD_REPORT_PATH)
    parser.add_argument("--rollback-preview-path", default=DEFAULT_N5_3_ROLLBACK_PREVIEW_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_n5_action_schema_migration_review(
        schema_path=args.schema_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        rollback_preview_path=args.rollback_preview_path,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    review = report["migration_review"]
    quality = report["quality"]
    side_effects = report["side_effects"]
    return "\n".join(
        [
            "action schema migration review",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  execution_mode={report['execution_mode']}",
            f"  schema_path={report['schema_path']}",
            f"  created_tables={review['created_tables']}",
            f"  additive_only={review['additive_only']}",
            f"  unsafe_statements={review['unsafe_statements']}",
            f"  extra_created_tables={review['extra_created_tables']}",
            f"  index_target_violations={review['index_target_violations']}",
            f"  payload_contract_missing={review['payload_contract_missing']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            f"  rollback_preview_path={report['rollback_preview']['path']} executed={report['rollback_preview']['executed']}",
            (
                "  migration_executed=false writes_performed=false "
                f"common_event_inbox_updated={side_effects['common_event_inbox_updated']} "
                f"consumer_checkpoint_updated={side_effects['consumer_checkpoint_updated']}"
            ),
            (
                "  real_n4_outbox_consumed=false n6_user_layer_touched=false "
                "voice_touched=false sim_touched=false mobile_touched=false "
                "real_trade_touched=false worker_started=false"
            ),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
