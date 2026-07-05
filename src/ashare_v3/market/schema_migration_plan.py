"""N3-0D market data schema migration execute plan dry-run.

This stage prepares the future migration contract for 006, including the
execution order and rollback preview. It does not execute SQL, create tables,
write rows, pull market data, or start workers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.schema_migration_review import (
    DEFAULT_MARKET_SCHEMA_PATH,
    REQUIRED_MARKET_CONTROL_TABLES,
    build_market_data_schema_migration_review,
)


DEFAULT_SUBSCRIPTION_REPORT_PATH = "docs/N3_0_market_data_subscription_plan_20260525.json"
REQUIRED_CONFIRMATION_PHRASE = "允许执行 N3-0D market data schema migration"


def build_market_data_schema_migration_plan(
    *,
    dsn: str,
    schema_path: str = DEFAULT_MARKET_SCHEMA_PATH,
    subscription_report_path: str = DEFAULT_SUBSCRIPTION_REPORT_PATH,
    user_confirmation: bool = False,
) -> dict[str, Any]:
    review = build_market_data_schema_migration_review(dsn=dsn, schema_path=schema_path)
    subscription_report = load_subscription_report(subscription_report_path)
    return build_market_data_schema_migration_plan_from_inputs(
        schema_path=schema_path,
        review=review,
        subscription_report=subscription_report,
        subscription_report_path=subscription_report_path,
        user_confirmation=user_confirmation,
    )


def build_market_data_schema_migration_plan_from_inputs(
    *,
    schema_path: str,
    review: Mapping[str, Any],
    subscription_report: Mapping[str, Any] | None,
    subscription_report_path: str,
    user_confirmation: bool,
) -> dict[str, Any]:
    quality_items = build_plan_quality_items(
        review=review,
        subscription_report=subscription_report,
        subscription_report_path=subscription_report_path,
        user_confirmation=user_confirmation,
    )
    severity_counts = count_quality_severities(quality_items)
    review_ready = bool(review.get("ready_for_user_migration_review")) and int(review.get("quality", {}).get("p0_count") or 0) == 0
    subscription_ready = subscription_report_is_ready(subscription_report)
    ready_for_user_confirmation = review_ready and subscription_ready and severity_counts["P0"] == 0
    execute_allowed = ready_for_user_confirmation and user_confirmation
    not_ready_reasons = not_ready_reason_list(
        review_ready=review_ready,
        subscription_ready=subscription_ready,
        user_confirmation=user_confirmation,
        severity_counts=severity_counts,
    )
    return {
        "stage": "N3-0D",
        "plan_mode": "market_data_schema_migration_execute_plan_dry_run",
        "schema_path": schema_path,
        "subscription_report_path": subscription_report_path,
        "migration_plan_id": "market_data_schema_006_first_apply_plan",
        "migration_required": bool(review.get("migration_required")),
        "ready_for_user_confirmation": ready_for_user_confirmation,
        "user_confirmation_required": True,
        "user_confirmation_phrase_required": REQUIRED_CONFIRMATION_PHRASE,
        "user_confirmation_present": user_confirmation,
        "execute_allowed": execute_allowed,
        "not_ready_reasons": not_ready_reasons,
        "review_summary": review_summary(review),
        "subscription_plan_summary": subscription_summary(subscription_report),
        "pre_migration_checks": pre_migration_checks(review, subscription_report),
        "future_execution_plan": {
            "strategy": "apply_006_common_market_data_control_tables",
            "will_create_tables": list(REQUIRED_MARKET_CONTROL_TABLES),
            "will_create_market_data_fact_tables": False,
            "will_write_business_rows": False,
            "will_pull_market_data": False,
            "will_start_worker": False,
            "execution_order": [
                "confirm explicit user authorization",
                "capture schema-only backup or equivalent DDL snapshot",
                "open short PostgreSQL migration connection to v3 development database",
                "execute sql/006_market_data_layer_schema.sql in one transaction",
                "postcheck common_market_data_* tables and required columns",
                "confirm N2 condition run and scope tables remain unchanged",
                "write migration report",
            ],
            "schema_sql_file": schema_path,
        },
        "post_migration_verification_plan": {
            "required_market_tables": list(REQUIRED_MARKET_CONTROL_TABLES),
            "expected_existing_count": len(REQUIRED_MARKET_CONTROL_TABLES),
            "checks": [
                "all common_market_data_* control tables exist",
                "required columns exist",
                "no market data fact tables are created by 006",
                "no trigger/action/mobile/voice/sim/worker objects are created",
                "condition-layer active run count is unchanged",
                "market data business row count remains zero until a later execute",
            ],
        },
        "rollback_sql_preview": build_rollback_sql_preview(),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def load_subscription_report(path: str) -> dict[str, Any] | None:
    report_path = Path(path)
    if not report_path.exists():
        return None
    return json.loads(report_path.read_text(encoding="utf-8"))


def build_plan_quality_items(
    *,
    review: Mapping[str, Any],
    subscription_report: Mapping[str, Any] | None,
    subscription_report_path: str,
    user_confirmation: bool,
) -> list[dict[str, Any]]:
    review_p0 = int(review.get("quality", {}).get("p0_count") or 0)
    subscription_p0 = int(subscription_report.get("quality", {}).get("p0_count") or 0) if subscription_report else None
    items = [
        quality_item(
            "P0",
            "passed" if review.get("ready_for_user_migration_review") and review_p0 == 0 else "failed",
            "n3_0c_schema_review_ready",
            "N3-0D migration plan requires N3-0C review to be clean",
            expected="ready_for_user_migration_review=true and P0=0",
            actual=f"ready={review.get('ready_for_user_migration_review')} p0={review_p0}",
        ),
        quality_item(
            "P0",
            "passed" if subscription_report_is_ready(subscription_report) else "failed",
            "n3_0_subscription_plan_ready",
            "N3-0D migration plan requires the subscription dry-run report to be clean",
            expected="subscription plan report exists and P0=0",
            actual="missing" if subscription_report is None else f"p0={subscription_p0} passed={subscription_report.get('passed')}",
            details={"subscription_report_path": subscription_report_path},
        ),
        quality_item(
            "P1",
            "warning" if not user_confirmation else "passed",
            "explicit_user_confirmation_required",
            "Executing migration requires an explicit user authorization phrase; this dry-run does not execute it",
            expected=REQUIRED_CONFIRMATION_PHRASE,
            actual="present" if user_confirmation else "missing",
        ),
        quality_item("P0", "passed", "migration_plan_no_execute", "N3-0D plan does not execute SQL"),
        quality_item("P0", "passed", "migration_plan_no_market_data_pull", "N3-0D plan does not pull market data"),
        quality_item("P0", "passed", "migration_plan_no_downstream_layers", "N3-0D plan does not enter trigger/action/mobile/voice/sim"),
    ]
    return items


def subscription_report_is_ready(subscription_report: Mapping[str, Any] | None) -> bool:
    if subscription_report is None:
        return False
    quality = subscription_report.get("quality") or {}
    return bool(subscription_report.get("passed")) and int(quality.get("p0_count") or 0) == 0


def not_ready_reason_list(
    *,
    review_ready: bool,
    subscription_ready: bool,
    user_confirmation: bool,
    severity_counts: Mapping[str, int],
) -> list[str]:
    reasons: list[str] = []
    if not review_ready:
        reasons.append("schema_review_not_ready")
    if not subscription_ready:
        reasons.append("subscription_plan_not_ready")
    if int(severity_counts.get("P0") or 0) > 0:
        reasons.append("p0_blocker_present")
    if not user_confirmation:
        reasons.append("pending_explicit_user_confirmation")
    return reasons


def review_summary(review: Mapping[str, Any]) -> dict[str, Any]:
    database = review.get("database_status") or {}
    return {
        "stage": review.get("stage"),
        "schema_path": review.get("schema_path"),
        "migration_required": review.get("migration_required"),
        "ready_for_user_migration_review": review.get("ready_for_user_migration_review"),
        "migration_safe_to_apply_after_user_confirmation": review.get("migration_safe_to_apply_after_user_confirmation"),
        "manual_review_required": review.get("manual_review_required"),
        "market_tables_existing": database.get("market_tables_existing"),
        "market_tables_missing": database.get("market_tables_missing"),
        "dependency_missing": database.get("dependency_missing"),
        "p0_count": (review.get("quality") or {}).get("p0_count"),
        "p1_count": (review.get("quality") or {}).get("p1_count"),
        "p2_count": (review.get("quality") or {}).get("p2_count"),
    }


def subscription_summary(subscription_report: Mapping[str, Any] | None) -> dict[str, Any]:
    if subscription_report is None:
        return {"report_exists": False}
    quality = subscription_report.get("quality") or {}
    return {
        "report_exists": True,
        "source_condition_run_id": subscription_report.get("source_condition_run_id"),
        "for_trade_date": subscription_report.get("for_trade_date"),
        "source_scope_row_count": subscription_report.get("source_scope_row_count"),
        "candidate_row_count": subscription_report.get("candidate_row_count"),
        "subscription_row_count": subscription_report.get("subscription_row_count"),
        "subscription_object_count": subscription_report.get("subscription_object_count"),
        "required_data_kind_counts": subscription_report.get("required_data_kind_counts"),
        "dedup_ratio": subscription_report.get("dedup_ratio"),
        "p0_count": quality.get("p0_count"),
        "p1_count": quality.get("p1_count"),
        "p2_count": quality.get("p2_count"),
        "passed": subscription_report.get("passed"),
    }


def pre_migration_checks(review: Mapping[str, Any], subscription_report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return [
        {
            "check": "schema_review_clean",
            "passed": bool(review.get("ready_for_user_migration_review")) and int(review.get("quality", {}).get("p0_count") or 0) == 0,
        },
        {
            "check": "subscription_plan_clean",
            "passed": subscription_report_is_ready(subscription_report),
        },
        {
            "check": "market_control_tables_absent_for_first_apply",
            "passed": bool((review.get("database_status") or {}).get("all_market_tables_missing")),
        },
        {
            "check": "n2_dependency_tables_exist",
            "passed": not bool((review.get("database_status") or {}).get("dependency_missing")),
        },
        {
            "check": "explicit_user_confirmation_present",
            "passed": False,
            "reason": "This dry-run intentionally does not treat 'continue' as migration authorization.",
        },
    ]


def build_rollback_sql_preview() -> list[str]:
    return [
        "-- Only for a later user-confirmed first-apply migration, before business rows exist.",
        "BEGIN;",
        "DROP TABLE IF EXISTS common_market_data_pull_plan;",
        "DROP TABLE IF EXISTS common_market_data_subscription;",
        "DROP TABLE IF EXISTS common_market_data_subscription_candidate;",
        "DROP TABLE IF EXISTS common_market_data_quality_item;",
        "DROP TABLE IF EXISTS common_market_data_run;",
        "COMMIT;",
    ]


def format_market_schema_migration_plan_markdown(report: Mapping[str, Any]) -> str:
    review = report["review_summary"]
    subscription = report["subscription_plan_summary"]
    quality = report["quality"]
    side_effects = report["side_effects"]
    lines = [
        "# N3-0D Market Data Schema Migration Plan",
        "",
        "## Summary",
        "",
        f"- migration_plan_id: {report['migration_plan_id']}",
        f"- schema_path: {report['schema_path']}",
        f"- migration_required: {str(report['migration_required']).lower()}",
        f"- ready_for_user_confirmation: {str(report['ready_for_user_confirmation']).lower()}",
        f"- user_confirmation_required: {str(report['user_confirmation_required']).lower()}",
        f"- user_confirmation_present: {str(report['user_confirmation_present']).lower()}",
        f"- execute_allowed: {str(report['execute_allowed']).lower()}",
        f"- not_ready_reasons: {report['not_ready_reasons']}",
        "",
        "## Review Input",
        "",
        f"- N3-0C ready_for_user_migration_review: {str(review['ready_for_user_migration_review']).lower()}",
        f"- N3-0C P0/P1/P2: {review['p0_count']}/{review['p1_count']}/{review['p2_count']}",
        f"- market_tables_existing: {review['market_tables_existing']}",
        f"- market_tables_missing: {review['market_tables_missing']}",
        f"- dependency_missing: {review['dependency_missing']}",
        "",
        "## Subscription Input",
        "",
        f"- report_exists: {str(subscription.get('report_exists')).lower()}",
        f"- source_condition_run_id: {subscription.get('source_condition_run_id')}",
        f"- for_trade_date: {subscription.get('for_trade_date')}",
        f"- source_scope_row_count: {subscription.get('source_scope_row_count')}",
        f"- candidate_row_count: {subscription.get('candidate_row_count')}",
        f"- subscription_row_count: {subscription.get('subscription_row_count')}",
        f"- subscription_object_count: {subscription.get('subscription_object_count')}",
        f"- required_data_kind_counts: {subscription.get('required_data_kind_counts')}",
        f"- dedup_ratio: {subscription.get('dedup_ratio')}",
        f"- P0/P1/P2: {subscription.get('p0_count')}/{subscription.get('p1_count')}/{subscription.get('p2_count')}",
        "",
        "## Future Execution Plan",
        "",
        f"- strategy: {report['future_execution_plan']['strategy']}",
        f"- will_create_tables: {report['future_execution_plan']['will_create_tables']}",
        "- will_create_market_data_fact_tables: false",
        "- will_write_business_rows: false",
        "- will_pull_market_data: false",
        "- will_start_worker: false",
        "",
        "Execution order if a later explicit authorization is provided:",
    ]
    for index, step in enumerate(report["future_execution_plan"]["execution_order"], start=1):
        lines.append(f"{index}. {step}")
    lines.extend(
        [
            "",
            "## Post-Migration Verification Plan",
            "",
        ]
    )
    for check in report["post_migration_verification_plan"]["checks"]:
        lines.append(f"- {check}")
    lines.extend(
        [
            "",
            "## Rollback SQL Preview",
            "",
            "```sql",
            *report["rollback_sql_preview"],
            "```",
            "",
            "## Quality",
            "",
            f"- P0: {quality['p0_count']}",
            f"- P1: {quality['p1_count']}",
            f"- P2: {quality['p2_count']}",
            "",
            "Quality items:",
        ]
    )
    for item in quality["items"]:
        lines.append(
            f"- {item['severity']} {item['status']} {item['gate_code']}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    lines.extend(
        [
            "",
            "## Boundary Confirmation",
            "",
            f"- old_system_touched: {str(side_effects['old_system_touched']).lower()}",
            f"- migration_executed: {str(side_effects['migration_executed']).lower()}",
            f"- will_execute_sql: {str(side_effects['will_execute_sql']).lower()}",
            f"- writes_performed: {str(side_effects['writes_performed']).lower()}",
            f"- market_data_pulled: {str(side_effects['market_data_pulled']).lower()}",
            f"- market_data_fact_written: {str(side_effects['market_data_fact_written']).lower()}",
            f"- downstream_layers_touched: {str(side_effects['downstream_layers_touched']).lower()}",
            f"- worker_started: {str(side_effects['worker_started']).lower()}",
            "",
            "## Rollback",
            "",
            "N3-0D did not execute migration and did not write database rows. "
            "Rollback for this dry-run stage is deleting this report and the plan code if needed.",
            "",
        ]
    )
    return "\n".join(lines)
