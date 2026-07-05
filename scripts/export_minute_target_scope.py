#!/usr/bin/env python3
"""Export a read-only minute_target_scope dry-run report.

N2-D boundary: this script generates the v3 market data scope preview only.
It reads the v3 condition source interface and ingestion facts, does not write
condition tables, does not pull minute bars, does not start workers, and does
not touch the old system.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.execute_plan import build_minute_scope_execute_plan
from ashare_v3.condition.scope import build_minute_target_scope_dry_run
from ashare_v3.condition.scope_policy import load_scope_policy
from check_condition_source_ready import DEFAULT_DSN, run_check


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v3 minute_target_scope dry-run report.")
    parser.add_argument("--source-trade-date", required=True, help="Finalized ingestion trade date, e.g. 20260522.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed N2-D mode.")
    parser.add_argument("--execute", action="store_true", help="Reserved for later stages; rejected in N2-D.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--policy", default="", help="Optional scope selection policy JSON path.")
    parser.add_argument("--plan-execute", action="store_true", help="Attach an N2-D3 future-write plan without executing SQL.")
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N2-D only supports --dry-run. Execute requires explicit later-stage confirmation.")

    ready = run_check(args.dsn, args.source_trade_date)
    if not ready.get("passed"):
        print(json.dumps({"source_ready": ready, "passed": False}, ensure_ascii=False, indent=2, default=str))
        return 2

    scope_policy = load_scope_policy(args.policy) if args.policy else None
    report = build_minute_target_scope_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
        scope_policy=scope_policy,
    )
    if args.plan_execute:
        report["execute_plan"] = build_minute_scope_execute_plan(report)

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["passed"] else 2


def format_summary(report: dict[str, Any]) -> str:
    scope = report["scope_preview"]
    quality = report["quality"]
    condition_pool_source = report["condition_pool_source"]
    policy = report["scope_policy"]
    lines = [
        "minute_target_scope dry-run",
        f"  source_trade_date={report['source_trade_date']}",
        f"  for_trade_date={report['for_trade_date']}",
        f"  prev_trade_date={report['prev_trade_date']}",
        f"  source_ready_passed={report['source_ready_passed']}",
        f"  scope_policy={policy['policy_name']} policy_mode={policy['mode']}",
        f"  scope_policy_warnings={policy['warnings']}",
        f"  condition_pool_source={condition_pool_source['mode']} condition_pool_run_id={condition_pool_source['run_id']}",
        f"  index_objects={scope['index']['object_count']} index_scope_rows={scope['index']['scope_row_count']} condition_pool_source={scope['index'].get('condition_pool_source')}",
        f"  index_policy_selected={scope['index']['policy_selected_count']} excluded={scope['index']['policy_excluded_count']} excluded_reasons={scope['index']['policy_excluded_reason_counts']}",
        f"  index_scope_source_counts={scope['index']['scope_source_counts']} prev_day_minute_required={scope['index']['previous_day_minute_required_count']} prev_day_minute_mismatch={scope['index']['previous_day_minute_date_mismatch_count']}",
        f"  board_objects={scope['board']['object_count']} board_scope_rows={scope['board']['scope_row_count']} condition_pool_source={scope['board'].get('condition_pool_source')}",
        f"  board_policy_selected={scope['board']['policy_selected_count']} excluded={scope['board']['policy_excluded_count']} excluded_reasons={scope['board']['policy_excluded_reason_counts']}",
        f"  board_scope_source_counts={scope['board']['scope_source_counts']} prev_day_minute_required={scope['board']['previous_day_minute_required_count']} prev_day_minute_mismatch={scope['board']['previous_day_minute_date_mismatch_count']}",
        f"  stock_objects={scope['stock']['object_count']} stock_scope_rows={scope['stock']['scope_row_count']} condition_pool_source={scope['stock']['condition_pool_source']}",
        f"  stock_policy_selected={scope['stock']['policy_selected_count']} excluded={scope['stock']['policy_excluded_count']} excluded_reasons={scope['stock']['policy_excluded_reason_counts']}",
        f"  stock_policy_distribution={summarize_stock_distribution(scope['stock'].get('policy_distribution', {}))}",
        f"  stock_scope_source_counts={scope['stock']['scope_source_counts']} prev_day_minute_required={scope['stock']['previous_day_minute_required_count']} prev_day_minute_mismatch={scope['stock']['previous_day_minute_date_mismatch_count']}",
        f"  stock_mv_filter_excluded={scope['stock']['excluded_below_min_total_mv_count']} stock_missing_total_mv={scope['stock']['missing_total_mv_count']}",
        f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
        "  writes_performed=false condition_pool_written=false minute_kline_pulled=false",
    ]
    if execute_plan := report.get("execute_plan"):
        lines.extend(format_execute_plan_summary(execute_plan))
    return "\n".join(lines)


def format_execute_plan_summary(execute_plan: dict[str, Any]) -> list[str]:
    would_write = execute_plan["would_write"]
    row_count_summary = ", ".join(f"{table}: {spec['row_count']}" for table, spec in would_write.items())
    return [
        "  execute_plan:",
        f"    plan_mode={execute_plan['plan_mode']} planned_run_id={execute_plan['planned_run_id']}",
        f"    policy_hash={execute_plan['policy_hash']}",
        f"    would_write={{{row_count_summary}}}",
        f"    execute_preconditions_passed={execute_plan['execute_preconditions_passed']} requires_user_confirmation={execute_plan['requires_user_confirmation']}",
        f"    requires_persisted_condition_pool_ids={execute_plan['requires_persisted_condition_pool_ids']} execute_ready={execute_plan['execute_ready']}",
        f"    not_ready_reasons={execute_plan['not_ready_reasons']}",
        f"    rollback_strategy={execute_plan['rollback_plan']['strategy']} rollback_run_id={execute_plan['rollback_plan']['run_id']}",
        "    will_connect_database=false will_execute_sql=false writes_performed=false",
    ]


def summarize_stock_distribution(distribution: dict[str, Any]) -> dict[str, Any]:
    return {
        "direction_counts": distribution.get("direction_counts", {}),
        "total_mv_bucket_counts": distribution.get("total_mv_bucket_counts", {}),
        "top_condition_keys": top_items(distribution.get("condition_key_counts", {}), 6),
        "top_boards": top_items(distribution.get("preferred_board_code_counts", {}), 6),
    }


def top_items(counts: dict[str, int], limit: int) -> dict[str, int]:
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit])


if __name__ == "__main__":
    raise SystemExit(main())
