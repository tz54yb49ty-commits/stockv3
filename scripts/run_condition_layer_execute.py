#!/usr/bin/env python3
"""Execute the v3 N2 condition layer into the development database.

This writes only condition-layer tables. It does not run migrations, pull
market data, start workers, or enter downstream runtime layers.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.web_policy import (
    DEFAULT_POLICY_DRAFT_RELATIVE_PATH,
    merge_web_policy,
    stable_policy_hash,
    web_policy_to_condition_pool_policy,
    web_policy_to_scope_policy,
)
from ashare_v3.condition.basis import build_condition_basis_dry_run
from ashare_v3.condition.execute import build_execute_run_id, execute_condition_layer
from ashare_v3.condition.execute_contract import build_condition_execute_contract
from ashare_v3.condition.execute_preflight import (
    build_condition_execute_preflight,
    fetch_active_run_status,
    fetch_run_id_status,
    fetch_schema_status,
)
from ashare_v3.condition.pool import build_condition_pool_dry_run
from ashare_v3.condition.readiness_plan import build_condition_layer_execute_readiness_plan
from ashare_v3.condition.scope import build_minute_target_scope_dry_run
from ashare_v3.condition.scope_policy import load_scope_policy, normalize_scope_policy
try:
    from check_condition_source_ready import DEFAULT_DSN, run_check
except ModuleNotFoundError:
    from scripts.check_condition_source_ready import DEFAULT_DSN, run_check


@dataclass(frozen=True)
class ConditionRunnerPolicy:
    policy_name: str
    policy_hash: str
    policy_source: str
    scope_policy: dict[str, Any] | None
    condition_pool_policy: dict[str, Any] | None
    policy_id: str = "built_in_default"
    policy_version: str = "built_in"
    previous_policy_hash: str | None = None
    policy_diff_summary: dict[str, Any] = field(default_factory=dict)


def load_condition_runner_policy(path: str | Path) -> ConditionRunnerPolicy:
    policy_path = Path(path)
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("N2 policy file must be a JSON object")

    if isinstance(payload.get("web_policy"), dict):
        web_policy = merge_web_policy(payload["web_policy"])
        scope_policy = normalize_scope_policy(payload.get("scope_policy") or web_policy_to_scope_policy(web_policy))
        condition_pool_policy = normalize_scope_policy(
            payload.get("condition_pool_policy") or web_policy_to_condition_pool_policy(web_policy)
        )
        return ConditionRunnerPolicy(
            policy_name=str(web_policy.get("policy_name") or "web_policy"),
            policy_hash=str(payload.get("policy_hash") or stable_policy_hash(web_policy)),
            policy_source=str(payload.get("source") or payload.get("artifact_type") or "web_policy_artifact"),
            scope_policy=scope_policy,
            condition_pool_policy=condition_pool_policy,
            policy_id=str(payload.get("policy_id") or payload.get("artifact_type") or "web_policy"),
            policy_version=str(payload.get("policy_version") or ""),
            previous_policy_hash=str(payload.get("previous_policy_hash")) if payload.get("previous_policy_hash") else None,
            policy_diff_summary=dict(payload.get("policy_diff_summary") or {}),
        )

    scope_policy = load_scope_policy(policy_path)
    return ConditionRunnerPolicy(
        policy_name=str(scope_policy.get("policy_name") or "scope_policy"),
        policy_hash=stable_policy_hash(scope_policy),
        policy_source="scope_policy",
        scope_policy=scope_policy,
        condition_pool_policy=scope_policy,
        policy_id="scope_policy",
        policy_version="",
        policy_diff_summary={},
    )


def resolve_condition_runner_policy(policy_path: str | Path | None, *, project_root: Path | None = None) -> ConditionRunnerPolicy:
    if policy_path:
        return load_condition_runner_policy(policy_path)
    default_path = (project_root or Path.cwd()) / DEFAULT_POLICY_DRAFT_RELATIVE_PATH
    if default_path.exists():
        return load_condition_runner_policy(default_path)
    return ConditionRunnerPolicy(
        policy_name="default",
        policy_hash="",
        policy_source="built_in_default",
        scope_policy=None,
        condition_pool_policy=None,
        policy_id="built_in_default",
        policy_version="built_in",
        policy_diff_summary={},
    )


def condition_runner_report_metadata(
    policy_bundle: ConditionRunnerPolicy,
    scope_report: dict[str, Any],
    *,
    execute_requested: bool,
) -> dict[str, Any]:
    return {
        "policy_source": policy_bundle.policy_source,
        "policy_id": policy_bundle.policy_id,
        "policy_version": policy_bundle.policy_version,
        "policy_hash": policy_bundle.policy_hash,
        "previous_policy_hash": policy_bundle.previous_policy_hash,
        "policy_diff_summary": policy_bundle.policy_diff_summary,
        "n3_rebuild_required": bool(execute_requested),
        "n3_lineage_auto_switch": False,
        "active_lineage_plan": {
            "overwrite_semantics": "lineage_supersede_only",
            "n3_lineage_auto_switch": False,
        },
        "scope_delta_summary": scope_delta_summary(scope_report),
    }


def scope_delta_summary(scope_report: dict[str, Any]) -> dict[str, Any]:
    preview = dict(scope_report.get("scope_preview") or {})
    summary: dict[str, Any] = {}
    for domain in ("stock", "index", "board"):
        item = dict(preview.get(domain) or {})
        summary[domain] = {
            "minute_target_scope_rows": int(item.get("scope_row_count") or item.get("row_count") or 0),
            "minute_target_scope_objects": int(item.get("object_count") or 0),
            "selected_from_condition_pool": True,
        }
    return summary


def build_source_not_ready_preflight(
    *,
    ready: dict[str, Any],
    requested_run_id: str = "",
    execute_requested: bool = False,
    user_confirmed: bool = False,
    overwrite: bool = False,
    policy_bundle: ConditionRunnerPolicy | None = None,
) -> dict[str, Any]:
    missing_data_types = list(ready.get("missing_data_types") or [])
    blocked_reasons = ["source_not_ready"] + [f"missing_active:{item}" for item in missing_data_types]
    report: dict[str, Any] = {
        "stage": "N2-source-readiness-preflight",
        "result": "PREFLIGHT_BLOCKED",
        "source_ready": False,
        "source_trade_date": ready.get("source_trade_date"),
        "for_trade_date": ready.get("for_trade_date"),
        "prev_trade_date": ready.get("prev_trade_date"),
        "requested_run_id": requested_run_id,
        "execute_requested": bool(execute_requested),
        "execute_allowed": False,
        "user_confirmed": bool(user_confirmed),
        "overwrite": bool(overwrite),
        "blocked_reasons": blocked_reasons,
        "missing_data_types": missing_data_types,
        "ready_check": ready,
        "writes_performed": False,
        "will_execute_sql": False,
        "database_written": False,
        "condition_business_rows_written": False,
        "market_data_pulled": False,
        "downstream_layers_touched": False,
        "worker_started": False,
        "n3_lineage_auto_switch": False,
        "active_lineage_plan": {
            "overwrite_semantics": "lineage_supersede_only",
            "n3_lineage_auto_switch": False,
        },
    }
    if policy_bundle is not None:
        report.update(
            {
                "policy_source": policy_bundle.policy_source,
                "policy_id": policy_bundle.policy_id,
                "policy_version": policy_bundle.policy_version,
                "policy_hash": policy_bundle.policy_hash,
                "previous_policy_hash": policy_bundle.previous_policy_hash,
                "policy_diff_summary": policy_bundle.policy_diff_summary,
                "n3_rebuild_required": False,
                "scope_delta_summary": {},
            }
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run condition-layer execute for v3 development database.")
    parser.add_argument("--source-trade-date", required=True, help="Finalized ingestion trade date, e.g. 20260522.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument(
        "--policy",
        default="",
        help=f"Optional scope/web policy JSON path, e.g. {DEFAULT_POLICY_DRAFT_RELATIVE_PATH}.",
    )
    parser.add_argument("--execute", action="store_true", help="Required to write condition-layer rows.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required when P1 exists or overwrite is requested.")
    parser.add_argument("--overwrite", action="store_true", help="Supersede an existing active run after postcheck.")
    parser.add_argument("--run-id", default="", help="Optional fixed N2 execute run_id override.")
    parser.add_argument("--operator", default="manual")
    parser.add_argument("--confirmation-note", default="")
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    ready = run_check(args.dsn, args.source_trade_date)
    policy_bundle = resolve_condition_runner_policy(args.policy)
    if not ready.get("passed"):
        report = build_source_not_ready_preflight(
            ready=ready,
            requested_run_id=args.run_id,
            execute_requested=args.execute,
            user_confirmed=args.user_confirmed,
            overwrite=args.overwrite,
            policy_bundle=policy_bundle,
        )
        if args.report_path:
            path = Path(args.report_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print(format_summary(report))
        return 2 if args.execute else 0

    scope_policy = policy_bundle.scope_policy
    condition_pool_policy = policy_bundle.condition_pool_policy
    basis_report = build_condition_basis_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
    )
    pool_report = build_condition_pool_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
        condition_pool_policy=condition_pool_policy,
    )
    scope_report = build_minute_target_scope_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
        scope_policy=scope_policy,
        condition_pool_policy=condition_pool_policy,
    )
    policy_metadata = condition_runner_report_metadata(
        policy_bundle,
        scope_report,
        execute_requested=args.execute,
    )
    if args.execute:
        if not args.user_confirmed:
            parser.error("N2-E3 execute requires --user-confirmed.")
        report = execute_condition_layer(
            dsn=args.dsn,
            ready_check=ready,
            basis_report=basis_report,
            pool_report=pool_report,
            scope_report=scope_report,
            user_confirmed=args.user_confirmed,
            overwrite=args.overwrite,
            operator=args.operator,
            confirmation_note=args.confirmation_note,
            run_id_override=args.run_id,
            condition_pool_policy=condition_pool_policy,
            policy_metadata=policy_metadata,
        )
    else:
        readiness_plan = build_condition_layer_execute_readiness_plan(
            basis_report=basis_report,
            pool_report=pool_report,
            scope_report=scope_report,
        )
        contract = build_condition_execute_contract(
            readiness_plan,
            user_confirmed=args.user_confirmed,
            overwrite=args.overwrite,
            operator=args.operator,
            confirmation_note=args.confirmation_note,
        )
        schema_status = fetch_schema_status(args.dsn)
        active_run_status = fetch_active_run_status(
            args.dsn,
            source_trade_date=str(readiness_plan["source_trade_date"]),
            for_trade_date=str(readiness_plan["for_trade_date"]),
            overwrite=args.overwrite,
        )
        run_id_status = None
        if args.run_id:
            requested_run_id = build_execute_run_id(
                str(readiness_plan["source_trade_date"]),
                str(readiness_plan["for_trade_date"]),
                run_id_override=args.run_id,
            )
            run_id_status = fetch_run_id_status(args.dsn, requested_run_id)
        report = build_condition_execute_preflight(
            readiness_plan=readiness_plan,
            execute_contract=contract,
            schema_status=schema_status,
            active_run_status=active_run_status,
            run_id_status=run_id_status,
        )
        if args.run_id:
            report["requested_run_id"] = args.run_id
        report.update(policy_metadata)

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0


def format_summary(report: dict[str, Any]) -> str:
    if report.get("stage") != "N2-E3":
        blocked = report.get("blocked_reasons", [])
        return "\n".join(
            [
                "condition-layer execute dry-run",
                f"  source_trade_date={report.get('source_trade_date')}",
                f"  for_trade_date={report.get('for_trade_date')}",
                f"  prev_trade_date={report.get('prev_trade_date')}",
                f"  requested_run_id={report.get('requested_run_id') or report.get('run_id_status', {}).get('requested_run_id')}",
                f"  execute_allowed={report.get('execute_allowed')} blocked_reasons={blocked}",
                "  writes_performed=false will_execute_sql=false",
            ]
        )
    rows = report["actual_row_counts"]
    row_summary = ", ".join(f"{table}: {count}" for table, count in rows.items())
    return "\n".join(
        [
            "condition-layer execute completed",
            f"  execute_run_id={report['execute_run_id']}",
            f"  source_trade_date={report['source_trade_date']}",
            f"  for_trade_date={report['for_trade_date']}",
            f"  prev_trade_date={report['prev_trade_date']}",
            f"  policy={report['policy_name']} policy_hash={report['policy_hash']}",
            f"  actual_rows={{{row_summary}}}",
            f"  run_status={report['postcheck']['run_status']} active_run_count={report['postcheck']['active_run_count']}",
            "  writes_performed=true will_execute_sql=true migration_performed=false minute_kline_pulled=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
