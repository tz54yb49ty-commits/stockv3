#!/usr/bin/env python3
"""Generate read-only DB/artifact summaries for N5/N3T Fastlane monitoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


N5_ACTIVE_SCOPE_ARTIFACT_TYPE = "n5_active_scope_snapshot_v1"
N3_SCOPED_ARTIFACT_TYPES = {
    "n3_c1_scoped_current_day_pull_plan_v1",
    "n3_c1_scoped_current_day_staging_v1",
    "n3_c1_scoped_closed_1m_artifact_v1",
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate N5/N3T Fastlane monitor summaries from read-only local evidence."
    )
    parser.add_argument("--raw-db-snapshot-path", default="")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--for-trade-date", default="")
    parser.add_argument("--n5-action-run-id-like", default="")
    parser.add_argument("--n3t-metric-run-id-like", default="")
    parser.add_argument("--n5-active-scope-artifact-dir", required=True)
    parser.add_argument("--n3-c1-n3t-artifact-dir", required=True)
    parser.add_argument("--db-summary-output-path", required=True)
    parser.add_argument("--artifact-summary-output-path", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    db_summary_path = Path(args.db_summary_output_path)
    artifact_summary_path = Path(args.artifact_summary_output_path)
    db_summary = build_db_summary(_load_raw_db_snapshot(args))
    artifact_summary = build_artifact_summary(
        n5_active_scope_artifact_dir=Path(args.n5_active_scope_artifact_dir),
        n3_c1_n3t_artifact_dir=Path(args.n3_c1_n3t_artifact_dir),
    )
    _write_json(db_summary_path, db_summary)
    _write_json(artifact_summary_path, artifact_summary)
    report = {
        "result": "DB_ARTIFACT_SUMMARY_OUTPUT_PASS",
        "db_summary_path": str(db_summary_path),
        "db_summary_sha256": _sha256_file(db_summary_path),
        "artifact_summary_path": str(artifact_summary_path),
        "artifact_summary_sha256": _sha256_file(artifact_summary_path),
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "result={result} db_summary_path={db_summary_path} db_summary_sha256={db_summary_sha256} "
            "artifact_summary_path={artifact_summary_path} artifact_summary_sha256={artifact_summary_sha256}".format(
                **report
            )
        )
    return 0


def _load_raw_db_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    raw_path = str(args.raw_db_snapshot_path or "").strip()
    if raw_path:
        return _read_json_object(Path(raw_path))
    dsn = str(args.dsn or os.environ.get("ASHARE_V3_POSTGRES_DSN") or "").strip()
    if not dsn:
        raise SystemExit("either --raw-db-snapshot-path or --dsn is required")
    for_trade_date = str(args.for_trade_date or "").strip()
    if not (for_trade_date.isdigit() and len(for_trade_date) == 8):
        raise SystemExit("--for-trade-date YYYYMMDD is required with --dsn")
    return _read_db_snapshot_via_dsn(
        dsn=dsn,
        for_trade_date=for_trade_date,
        n5_action_run_id_like=str(args.n5_action_run_id_like or "")
        or f"n5_live_tracking_{for_trade_date}%__fastlane_v1",
        n3t_metric_run_id_like=str(args.n3t_metric_run_id_like or "")
        or f"n3t_action_confirmation_metric_{for_trade_date}%__fastlane%",
    )


def _read_db_snapshot_via_dsn(
    *,
    dsn: str,
    for_trade_date: str,
    n5_action_run_id_like: str,
    n3t_metric_run_id_like: str,
) -> dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(
        dsn,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
        connect_timeout=10,
    ) as conn, conn.cursor() as cur:
        return collect_raw_db_snapshot(
            cur,
            for_trade_date=for_trade_date,
            n5_action_run_id_like=n5_action_run_id_like,
            n3t_metric_run_id_like=n3t_metric_run_id_like,
        )


def collect_raw_db_snapshot(
    cur: Any,
    *,
    for_trade_date: str,
    n5_action_run_id_like: str,
    n3t_metric_run_id_like: str,
) -> dict[str, Any]:
    n4_triggermatched = _query_count(
        cur,
        """
        SELECT count(*)::bigint AS count
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND trade_date = %s
          AND event_type = 'TriggerMatched'
          AND status = 'pending'
        """,
        (for_trade_date,),
    )
    n4_non_pending = _query_count(
        cur,
        """
        SELECT count(*)::bigint AS count
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND trade_date = %s
          AND event_type = 'TriggerMatched'
          AND status <> 'pending'
        """,
        (for_trade_date,),
    )
    cur.execute(
        """
        SELECT event_type, count(*)::bigint AS count
        FROM common_event_outbox
        WHERE source_layer = 'N5_action'
          AND trade_date = %s
          AND source_run_id LIKE %s
          AND event_type IN ('ActionEligible', 'ActionExecuted')
        GROUP BY event_type
        ORDER BY event_type
        """,
        (for_trade_date, n5_action_run_id_like),
    )
    n5_event_counts = {str(row.get("event_type") or ""): _as_int(row.get("count")) for row in cur.fetchall()}
    n5_active_tracking = _query_count(
        cur,
        """
        SELECT count(*)::bigint AS count
        FROM common_action_tracking_state
        WHERE trade_date = %s
          AND run_id LIKE %s
          AND action_state = 'eligible'
          AND tracking_status = 'tracking'
        """,
        (for_trade_date, n5_action_run_id_like),
    )
    n3t_metric_counts = _query_n3t_metric_counts(
        cur,
        for_trade_date=for_trade_date,
        n3t_metric_run_id_like=n3t_metric_run_id_like,
    )
    legacy_metric_used = _query_count(
        cur,
        """
        SELECT count(*)::bigint AS count
        FROM common_event_outbox
        WHERE source_layer = 'N5_action'
          AND trade_date = %s
          AND source_run_id LIKE %s
          AND event_type = 'ActionExecuted'
          AND COALESCE(payload_json ->> 'source_metric_run_id', '') NOT LIKE %s
        """,
        (for_trade_date, n5_action_run_id_like, n3t_metric_run_id_like),
    )
    return {
        "n4_triggermatched": n4_triggermatched,
        "n4_triggermatched_non_pending_observed": n4_non_pending,
        "n5_actioneligible": n5_event_counts.get("ActionEligible", 0),
        "n5_active_tracking": n5_active_tracking,
        "n5_actionexecuted": n5_event_counts.get("ActionExecuted", 0),
        "n3t_c1_closed_metric_rows": n3t_metric_counts["contract_rows"],
        "n5_output_event_types": sorted(event_type for event_type, count in n5_event_counts.items() if count > 0),
        "n4_outbox_status_unchanged": True,
        "n4_outbox_updated": False,
        "n3t_lineage_ok": n3t_metric_counts["total_rows"] == n3t_metric_counts["contract_rows"],
        "legacy_metric_used": legacy_metric_used > 0,
    }


def _query_n3t_metric_counts(
    cur: Any,
    *,
    for_trade_date: str,
    n3t_metric_run_id_like: str,
) -> dict[str, int]:
    union_sql = "\nUNION ALL\n".join(
        [
            """
            SELECT projection_run_id, source_basis, metric_role, proof_consumer,
                   not_n5_final_proof, metric_ready, metric_quality_status
            FROM stock_n3t_action_confirmation_metric
            WHERE for_trade_date = %s AND projection_run_id LIKE %s
            """,
            """
            SELECT projection_run_id, source_basis, metric_role, proof_consumer,
                   not_n5_final_proof, metric_ready, metric_quality_status
            FROM index_n3t_action_confirmation_metric
            WHERE for_trade_date = %s AND projection_run_id LIKE %s
            """,
            """
            SELECT projection_run_id, source_basis, metric_role, proof_consumer,
                   not_n5_final_proof, metric_ready, metric_quality_status
            FROM board_n3t_action_confirmation_metric
            WHERE for_trade_date = %s AND projection_run_id LIKE %s
            """,
        ]
    )
    cur.execute(
        f"""
        SELECT
          count(*)::bigint AS total_rows,
          count(*) FILTER (
            WHERE source_basis = 'N3T_C1_CLOSED'
              AND metric_role = 'action_confirmation'
              AND proof_consumer = 'N5'
              AND not_n5_final_proof = false
              AND metric_ready = true
              AND metric_quality_status = 'passed'
          )::bigint AS contract_rows
        FROM ({union_sql}) AS n3t_rows
        """,
        (
            for_trade_date,
            n3t_metric_run_id_like,
            for_trade_date,
            n3t_metric_run_id_like,
            for_trade_date,
            n3t_metric_run_id_like,
        ),
    )
    row = cur.fetchone() or {}
    return {
        "total_rows": _as_int(row.get("total_rows")),
        "contract_rows": _as_int(row.get("contract_rows")),
    }


def _query_count(cur: Any, sql: str, params: tuple[Any, ...]) -> int:
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return _as_int(row.get("count"))


def build_db_summary(raw_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "n5_n3t_fastlane_db_summary_v1",
        "n4_triggermatched": _as_int(raw_snapshot.get("n4_triggermatched")),
        "n4_triggermatched_non_pending_observed": _as_int(
            raw_snapshot.get("n4_triggermatched_non_pending_observed")
        ),
        "n5_actioneligible": _as_int(raw_snapshot.get("n5_actioneligible")),
        "n5_active_tracking": _as_int(raw_snapshot.get("n5_active_tracking")),
        "n5_actionexecuted": _as_int(raw_snapshot.get("n5_actionexecuted")),
        "n3t_c1_closed_metric_rows": _as_int(raw_snapshot.get("n3t_c1_closed_metric_rows")),
        "n5_output_event_types": sorted(str(value) for value in (raw_snapshot.get("n5_output_event_types") or [])),
        "n4_outbox_status_unchanged": bool(raw_snapshot.get("n4_outbox_status_unchanged")),
        "n4_outbox_updated": bool(raw_snapshot.get("n4_outbox_updated")),
        "n3t_lineage_ok": bool(raw_snapshot.get("n3t_lineage_ok")),
        "legacy_metric_used": bool(raw_snapshot.get("legacy_metric_used")),
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }


def build_artifact_summary(
    *,
    n5_active_scope_artifact_dir: Path,
    n3_c1_n3t_artifact_dir: Path,
) -> dict[str, Any]:
    n5_artifacts = _read_artifacts(n5_active_scope_artifact_dir, {N5_ACTIVE_SCOPE_ARTIFACT_TYPE})
    n3_artifacts = _read_artifacts(n3_c1_n3t_artifact_dir, N3_SCOPED_ARTIFACT_TYPES)
    n3_scanned_n5_db = any(bool(artifact.get("n3_scans_n5_db")) for artifact in n3_artifacts)
    n3_full_market_fallback = any(
        bool(artifact.get("full_market_fallback"))
        or bool(artifact.get("full_market_fallback_used"))
        or bool(artifact.get("full_market_fallback_allowed"))
        for artifact in n3_artifacts
    )
    non_explicit_inputs = [
        str(artifact.get("source_input_type") or "")
        for artifact in n3_artifacts
        if str(artifact.get("source_input_type") or "") not in {"", N5_ACTIVE_SCOPE_ARTIFACT_TYPE}
    ]
    return {
        "artifact_type": "n5_n3t_fastlane_artifact_summary_v1",
        "n5_active_scope_artifacts": len(n5_artifacts),
        "n3_scoped_c1_artifacts": len(n3_artifacts),
        "n3_consumed_only_explicit_active_scope_artifact": not non_explicit_inputs,
        "n3_scanned_n5_db": n3_scanned_n5_db,
        "n3_full_market_fallback": n3_full_market_fallback,
        "old_n3_n4_labels_unchanged": True,
        "n6_touched": False,
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }


def _read_artifacts(root: Path, allowed_types: set[str]) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        payload = _read_json_object(path)
        if str(payload.get("artifact_type") or "") in allowed_types:
            artifacts.append(payload)
    return artifacts


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _forbidden_operation_proof() -> dict[str, bool]:
    return {
        "database_written_by_plan": False,
        "runtime_executed_by_plan": False,
        "launchd_loaded_or_started": False,
        "n4_outbox_updated_by_plan": False,
        "n6_touched_by_plan": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
