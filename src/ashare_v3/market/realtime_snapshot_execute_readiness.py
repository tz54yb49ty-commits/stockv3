"""N3-B1 realtime snapshot execute readiness gate.

This module performs read-only checks before the first realtime snapshot
execute. It does not call market data adapters, write snapshot facts, write
outbox rows, execute migrations, or start workers.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.preload_plan import REALTIME_SNAPSHOT_TABLES, normalize_db_row
from ashare_v3.market.realtime_snapshot_execute_contract import DEFAULT_B1_CONTRACT_JSON_PATH
from ashare_v3.market.subscription_plan import ASSET_KINDS


DEFAULT_B1_READINESS_JSON_PATH = "docs/N3_B1_realtime_daily_snapshot_execute_readiness.json"
DEFAULT_B1_READINESS_MD_PATH = "docs/N3_B1_REALTIME_DAILY_SNAPSHOT_EXECUTE_READINESS.md"


def build_realtime_snapshot_execute_readiness(
    *,
    dsn: str,
    market_data_run_id: str,
    contract_path: str = DEFAULT_B1_CONTRACT_JSON_PATH,
    preload_run_id: str | None = None,
    current_date: str | None = None,
    allow_repeat_idempotent: bool = False,
) -> dict[str, Any]:
    contract = read_json(contract_path)
    source_run_id = str(contract.get("source_run_id") or market_data_run_id)
    resolved_preload_run_id = preload_run_id or derive_preload_run_id(contract, source_run_id)
    today = current_date or datetime.now().strftime("%Y%m%d")
    db_state = fetch_readiness_db_state(
        dsn=dsn,
        source_run_id=source_run_id,
        preload_run_id=resolved_preload_run_id,
        snapshot_run_id=str(contract.get("snapshot_run_id") or ""),
        for_trade_date=str(contract.get("for_trade_date") or ""),
    )
    return build_readiness_from_inputs(
        contract=contract,
        market_data_run_id=market_data_run_id,
        preload_run_id=resolved_preload_run_id,
        current_date=today,
        calendar_rows=db_state["calendar_rows"],
        source_run=db_state["source_run"],
        preload_run=db_state["preload_run"],
        preload_status_counts=db_state["preload_status_counts"],
        snapshot_run=db_state["snapshot_run"],
        snapshot_row_counts=db_state["snapshot_row_counts"],
        outbox_status_counts=db_state["outbox_status_counts"],
        allow_repeat_idempotent=allow_repeat_idempotent,
    )


def fetch_readiness_db_state(
    *,
    dsn: str,
    source_run_id: str,
    preload_run_id: str,
    snapshot_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT trade_date, exchange, is_open, prev_trade_date, next_trade_date,
                   source, source_version
            FROM common_trade_calendar
            WHERE trade_date = %s
            ORDER BY exchange
            """,
            (for_trade_date,),
        )
        calendar_rows = [normalize_db_row(row) for row in cur.fetchall()]

        source_run = fetch_market_data_run(cur, source_run_id)
        preload_run = fetch_market_data_run(cur, preload_run_id)
        snapshot_run = fetch_market_data_run(cur, snapshot_run_id)
        preload_status_counts = fetch_preload_status_counts(cur, preload_run_id)
        snapshot_row_counts = fetch_snapshot_row_counts(cur, snapshot_run_id, for_trade_date)
        outbox_status_counts = fetch_outbox_status_counts(cur, snapshot_run_id)

    return {
        "calendar_rows": calendar_rows,
        "source_run": source_run,
        "preload_run": preload_run,
        "snapshot_run": snapshot_run,
        "preload_status_counts": preload_status_counts,
        "snapshot_row_counts": snapshot_row_counts,
        "outbox_status_counts": outbox_status_counts,
    }


def fetch_market_data_run(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any] | None:
    if not run_id:
        return None
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, for_trade_date, source_trade_date,
               prev_trade_date, mode, status, p0_count, p1_count, p2_count,
               market_data_pulled, market_data_fact_written,
               downstream_layers_touched, worker_started
        FROM common_market_data_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    return normalize_db_row(row) if row is not None else None


def fetch_preload_status_counts(cur: psycopg.Cursor[dict[str, Any]], preload_run_id: str) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for asset_kind in ASSET_KINDS:
        table_name = f"{asset_kind}_previous_day_minute_preload_status"
        cur.execute(
            f"""
            SELECT status, count(*)::bigint AS row_count
            FROM {table_name}
            WHERE run_id = %s
            GROUP BY status
            """,
            (preload_run_id,),
        )
        counts = {str(row["status"]): int(row["row_count"]) for row in cur.fetchall()}
        output[asset_kind] = {
            "passed": counts.get("passed", 0),
            "partial": counts.get("partial", 0),
            "missing": counts.get("missing", 0),
            "failed": counts.get("failed", 0),
            "total": sum(counts.values()),
        }
    return output


def fetch_snapshot_row_counts(
    cur: psycopg.Cursor[dict[str, Any]],
    snapshot_run_id: str,
    for_trade_date: str,
) -> dict[str, int]:
    output: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        table_name = REALTIME_SNAPSHOT_TABLES[asset_kind]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS row_count
            FROM {table_name}
            WHERE run_id = %s
              AND for_trade_date = %s
            """,
            (snapshot_run_id, for_trade_date),
        )
        output[asset_kind] = int(cur.fetchone()["row_count"])
    return output


def fetch_outbox_status_counts(cur: psycopg.Cursor[dict[str, Any]], snapshot_run_id: str) -> dict[str, int]:
    if not snapshot_run_id:
        return {}
    cur.execute(
        """
        SELECT status, count(*)::bigint AS row_count
        FROM common_event_outbox
        WHERE source_layer = 'N3_market_data'
          AND source_run_id = %s
        GROUP BY status
        ORDER BY status
        """,
        (snapshot_run_id,),
    )
    return {str(row["status"]): int(row["row_count"]) for row in cur.fetchall()}


def build_readiness_from_inputs(
    *,
    contract: Mapping[str, Any],
    market_data_run_id: str,
    preload_run_id: str,
    current_date: str,
    calendar_rows: Sequence[Mapping[str, Any]],
    source_run: Mapping[str, Any] | None,
    preload_run: Mapping[str, Any] | None,
    preload_status_counts: Mapping[str, Mapping[str, int]],
    snapshot_run: Mapping[str, Any] | None,
    snapshot_row_counts: Mapping[str, int],
    outbox_status_counts: Mapping[str, int],
    allow_repeat_idempotent: bool = False,
) -> dict[str, Any]:
    quality_items = build_readiness_quality_items(
        contract=contract,
        market_data_run_id=market_data_run_id,
        preload_run_id=preload_run_id,
        current_date=current_date,
        calendar_rows=calendar_rows,
        source_run=source_run,
        preload_run=preload_run,
        preload_status_counts=preload_status_counts,
        snapshot_run=snapshot_run,
        snapshot_row_counts=snapshot_row_counts,
        outbox_status_counts=outbox_status_counts,
        allow_repeat_idempotent=allow_repeat_idempotent,
    )
    counts = count_quality_severities(quality_items)
    ready = counts["P0"] == 0
    blocked_reason = None if ready else first_blocked_reason(quality_items, current_date, str(contract.get("for_trade_date") or ""))
    return {
        "stage": "N3-B1-readiness-gate",
        "layer_role": "N3_market_data",
        "mode": "read_only",
        "ready": ready,
        "blocked": not ready,
        "blocked_reason": blocked_reason,
        "current_date": current_date,
        "for_trade_date": contract.get("for_trade_date"),
        "source_run_id": contract.get("source_run_id"),
        "market_data_run_id": market_data_run_id,
        "snapshot_run_id": contract.get("snapshot_run_id"),
        "preload_run_id": preload_run_id,
        "allow_repeat_idempotent": allow_repeat_idempotent,
        "calendar": {
            "row_count": len(calendar_rows),
            "is_trade_date": any(bool(row.get("is_open")) for row in calendar_rows),
            "rows": [dict(row) for row in calendar_rows],
        },
        "source_run": dict(source_run) if source_run is not None else None,
        "preload_run": dict(preload_run) if preload_run is not None else None,
        "preload_status_counts": normalize_nested_ints(preload_status_counts),
        "snapshot_run": dict(snapshot_run) if snapshot_run is not None else None,
        "snapshot_row_counts": {asset: int(snapshot_row_counts.get(asset) or 0) for asset in ASSET_KINDS},
        "snapshot_existing_row_count": sum(int(snapshot_row_counts.get(asset) or 0) for asset in ASSET_KINDS),
        "outbox_status_counts": {str(key): int(value) for key, value in outbox_status_counts.items()},
        "outbox_existing_row_count": sum(int(value) for value in outbox_status_counts.values()),
        "execute_runner_readiness": dict(contract.get("execute_runner_readiness") or {}),
        "quality": {
            "p0_count": counts["P0"],
            "p1_count": counts["P1"],
            "p2_count": counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "realtime_snapshot_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def build_readiness_quality_items(
    *,
    contract: Mapping[str, Any],
    market_data_run_id: str,
    preload_run_id: str,
    current_date: str,
    calendar_rows: Sequence[Mapping[str, Any]],
    source_run: Mapping[str, Any] | None,
    preload_run: Mapping[str, Any] | None,
    preload_status_counts: Mapping[str, Mapping[str, int]],
    snapshot_run: Mapping[str, Any] | None,
    snapshot_row_counts: Mapping[str, int],
    outbox_status_counts: Mapping[str, int],
    allow_repeat_idempotent: bool,
) -> list[dict[str, Any]]:
    for_trade_date = str(contract.get("for_trade_date") or "")
    contract_quality = contract.get("quality") or {}
    calendar_open = any(bool(row.get("is_open")) for row in calendar_rows)
    snapshot_existing_rows = sum(int(snapshot_row_counts.get(asset) or 0) for asset in ASSET_KINDS)
    outbox_existing_rows = sum(int(value) for value in outbox_status_counts.values())
    repeated = snapshot_run is not None or snapshot_existing_rows > 0 or outbox_existing_rows > 0
    preload_status_total = sum(int((preload_status_counts.get(asset) or {}).get("total") or 0) for asset in ASSET_KINDS)
    preload_missing = sum(
        int((preload_status_counts.get(asset) or {}).get("missing") or 0)
        + int((preload_status_counts.get(asset) or {}).get("partial") or 0)
        + int((preload_status_counts.get(asset) or {}).get("failed") or 0)
        for asset in ASSET_KINDS
    )
    runner_readiness = contract.get("execute_runner_readiness") or {}
    runner_gate_passed = (
        not runner_readiness
        or (
            bool(runner_readiness.get("runner_exists"))
            and bool(runner_readiness.get("execute_final_gate_allowed"))
        )
    )
    items = [
        quality_item(
            "P0",
            "passed" if contract.get("stage") == "N3-B1-preflight" and int(contract_quality.get("p0_count") or 0) == 0 else "failed",
            "n3_b1_readiness_contract_clean",
            "N3-B1 readiness requires a clean B1 preflight contract",
            expected="stage=N3-B1-preflight P0=0",
            actual=f"stage={contract.get('stage')} P0={contract_quality.get('p0_count')}",
        ),
        quality_item(
            "P0",
            "passed" if contract.get("source_run_id") == market_data_run_id else "failed",
            "n3_b1_readiness_source_run_matches_contract",
            "CLI run_id must match the B1 contract source_run_id",
            expected=str(contract.get("source_run_id")),
            actual=market_data_run_id,
        ),
        quality_item(
            "P0",
            "passed" if runner_gate_passed else "failed",
            "n3_b1_execute_runner_ready_for_contract",
            "execute runner must support the B1 contract before final gate",
            expected="runner_exists=true execute_final_gate_allowed=true",
            actual=(
                "not_declared"
                if not runner_readiness
                else f"runner_exists={runner_readiness.get('runner_exists')} "
                f"execute_final_gate_allowed={runner_readiness.get('execute_final_gate_allowed')} "
                f"reason={runner_readiness.get('blocked_reason')}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if current_date == for_trade_date else "failed",
            "n3_b1_current_date_equals_for_trade_date",
            "realtime snapshot execute must run on for_trade_date only",
            expected=for_trade_date,
            actual=current_date,
        ),
        quality_item(
            "P0",
            "passed" if calendar_rows else "failed",
            "n3_b1_trade_calendar_row_exists",
            "common_trade_calendar must contain for_trade_date before realtime snapshot execute",
            expected=f"trade_date={for_trade_date}",
            actual=f"row_count={len(calendar_rows)}",
        ),
        quality_item(
            "P0",
            "passed" if calendar_open else "failed",
            "n3_b1_trade_calendar_is_open",
            "for_trade_date must be an open A-share trade date",
            expected="is_open=true",
            actual=f"is_open={calendar_open}",
        ),
        quality_item(
            "P0",
            "passed" if source_run_is_clean(source_run, market_data_run_id) else "failed",
            "n3_b1_source_subscription_run_passed",
            "N3-6 market_data_subscription source run must be passed with P0=0",
            expected="status=passed P0=0",
            actual=describe_run(source_run),
        ),
        quality_item(
            "P0",
            "passed" if preload_run_is_completed(preload_run) and preload_status_total > 0 else "failed",
            "n3_b1_previous_day_preload_completed",
            "N3-A1 previous-day minute preload must be completed before realtime snapshot execute",
            expected="status=passed P0=0 preload_status_rows>0",
            actual=f"{describe_run(preload_run)} preload_status_rows={preload_status_total}",
        ),
        quality_item(
            "P1",
            "warning" if preload_missing > 0 else "passed",
            "n3_b1_previous_day_preload_missing_carried",
            "N3-A1 missing/partial/failed preload objects are non-blocking only when recorded as status/quality evidence",
            expected="0",
            actual=str(preload_missing),
            details={"preload_status_counts": normalize_nested_ints(preload_status_counts)},
        ),
        quality_item(
            "P0",
            "passed" if not repeated or allow_repeat_idempotent else "failed",
            "n3_b1_snapshot_run_id_not_previously_executed",
            "B1 snapshot_run_id must not already have run/fact/outbox rows unless explicit idempotent repeat is allowed",
            expected="no existing snapshot run, fact rows, or outbox rows",
            actual=f"run_exists={snapshot_run is not None} snapshot_rows={snapshot_existing_rows} outbox_rows={outbox_existing_rows}",
        ),
        quality_item(
            "P1",
            "warning" if repeated and allow_repeat_idempotent else "passed",
            "n3_b1_repeat_requires_idempotent_review",
            "repeat execution is only allowed under explicit idempotent review",
            expected="no repeat",
            actual=f"allow_repeat_idempotent={allow_repeat_idempotent}",
        ),
        quality_item(
            "P0",
            "passed",
            "n3_b1_readiness_no_market_pull_or_write",
            "readiness gate must not pull market data or write snapshot/outbox",
            expected="read-only",
            actual="read-only",
        ),
    ]
    return items


def source_run_is_clean(source_run: Mapping[str, Any] | None, expected_run_id: str) -> bool:
    if source_run is None:
        return False
    return (
        source_run.get("run_id") == expected_run_id
        and source_run.get("status") == "passed"
        and int(source_run.get("p0_count") or 0) == 0
    )


def preload_run_is_completed(preload_run: Mapping[str, Any] | None) -> bool:
    if preload_run is None:
        return False
    return preload_run.get("status") == "passed" and int(preload_run.get("p0_count") or 0) == 0


def first_blocked_reason(items: Sequence[Mapping[str, Any]], current_date: str, for_trade_date: str) -> str:
    for item in items:
        if item.get("severity") != "P0" or item.get("status") != "failed":
            continue
        gate_code = str(item.get("gate_code"))
        if gate_code == "n3_b1_current_date_equals_for_trade_date":
            if current_date < for_trade_date:
                return "current_date_before_for_trade_date"
            if current_date > for_trade_date:
                return "current_date_after_for_trade_date"
            return "current_date_mismatch"
        if gate_code == "n3_b1_trade_calendar_row_exists":
            return "trade_calendar_missing"
        if gate_code == "n3_b1_trade_calendar_is_open":
            return "for_trade_date_not_open"
        if gate_code == "n3_b1_source_subscription_run_passed":
            return "n3_6_subscription_run_not_passed"
        if gate_code == "n3_b1_previous_day_preload_completed":
            return "previous_day_preload_not_completed"
        if gate_code == "n3_b1_snapshot_run_id_not_previously_executed":
            return "snapshot_run_id_already_executed"
        if gate_code == "n3_b1_execute_runner_ready_for_contract":
            return "execute_runner_not_ready_for_contract"
        return gate_code
    return "unknown"


def derive_preload_run_id(contract: Mapping[str, Any], source_run_id: str) -> str:
    previous_day = str(contract.get("prev_trade_date") or contract.get("source_trade_date") or "")
    for_trade_date = str(contract.get("for_trade_date") or "")
    return f"previous_day_minute_preload_{previous_day}_for_{for_trade_date}__{source_run_id}"


def describe_run(run: Mapping[str, Any] | None) -> str:
    if run is None:
        return "missing"
    return f"run_id={run.get('run_id')} status={run.get('status')} P0={run.get('p0_count')}"


def normalize_nested_ints(value: Mapping[str, Mapping[str, int]]) -> dict[str, dict[str, int]]:
    return {
        str(outer_key): {str(inner_key): int(inner_value) for inner_key, inner_value in inner.items()}
        for outer_key, inner in value.items()
    }


def format_realtime_snapshot_readiness_summary(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    return "\n".join(
        [
            "realtime snapshot execute readiness",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  ready={str(report['ready']).lower()}",
            f"  blocked_reason={report['blocked_reason']}",
            f"  current_date={report['current_date']}",
            f"  for_trade_date={report['for_trade_date']}",
            f"  source_run_id={report['source_run_id']}",
            f"  snapshot_run_id={report['snapshot_run_id']}",
            f"  preload_run_id={report['preload_run_id']}",
            f"  calendar_row_count={report['calendar']['row_count']} is_trade_date={report['calendar']['is_trade_date']}",
            f"  snapshot_existing_row_count={report['snapshot_existing_row_count']} outbox_existing_row_count={report['outbox_existing_row_count']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  market_data_pulled=false realtime_snapshot_written=false event_outbox_written=false worker_started=false",
        ]
    )


def format_realtime_snapshot_readiness_markdown(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    lines = [
        "# N3-B1 Realtime Daily Snapshot Execute Readiness",
        "",
        "## Summary",
        "",
        f"- stage: `{report['stage']}`",
        f"- layer_role: `{report['layer_role']}`",
        f"- ready: `{str(report['ready']).lower()}`",
        f"- blocked_reason: `{report['blocked_reason']}`",
        f"- current_date: `{report['current_date']}`",
        f"- for_trade_date: `{report['for_trade_date']}`",
        f"- source_run_id: `{report['source_run_id']}`",
        f"- snapshot_run_id: `{report['snapshot_run_id']}`",
        f"- preload_run_id: `{report['preload_run_id']}`",
        f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
        "",
        "## Readiness Inputs",
        "",
        f"- calendar_row_count: `{report['calendar']['row_count']}`",
        f"- is_trade_date: `{report['calendar']['is_trade_date']}`",
        f"- snapshot_existing_row_count: `{report['snapshot_existing_row_count']}`",
        f"- outbox_existing_row_count: `{report['outbox_existing_row_count']}`",
        "",
        "## Preload Status Counts",
        "",
    ]
    for asset_kind, counts in report["preload_status_counts"].items():
        lines.append(
            f"- {asset_kind}: passed=`{counts['passed']}` partial=`{counts['partial']}` "
            f"missing=`{counts['missing']}` failed=`{counts['failed']}` total=`{counts['total']}`"
        )
    lines.extend(["", "## Quality", ""])
    for item in quality["items"]:
        lines.append(
            f"- {item['severity']} {item['status']} {item['gate_code']}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    lines.extend(["", "## Boundary", ""])
    for key, value in report["side_effects"].items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.append("")
    return "\n".join(lines)


def write_readiness_files(report: Mapping[str, Any], *, markdown_path: str, json_path: str) -> None:
    write_text(markdown_path, format_realtime_snapshot_readiness_markdown(report))
    write_text(json_path, json.dumps(json_safe(report), ensure_ascii=False, indent=2, default=str) + "\n")


def read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, Counter):
        return dict(value)
    return value
