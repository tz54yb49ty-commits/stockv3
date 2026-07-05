"""Persistence contract helpers for N3 index/board 1m HINT projection proof."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import re
from typing import Any, Mapping, Sequence


HINT_1M_PROOF_KIND = "index_board_1m_hint_projection_v1"
HINT_1M_MIDDAY_BRIDGE_PROOF_KIND = "index_board_1m_hint_projection_v1_midday_bridge_v1"
ALLOWED_HINT_1M_PROOF_KINDS = frozenset({HINT_1M_PROOF_KIND, HINT_1M_MIDDAY_BRIDGE_PROOF_KIND})
HINT_1M_SOURCE_MODE = "index_board_frequency8_1m"
HINT_1M_METRIC_ROLE = "hint_trigger_proof"
HINT_1M_PROOF_OWNER = "N3"
HINT_1M_PROOF_CONSUMER = "N4"
HINT_1M_PROJECTION_SCHEMA_VERSION = "n3.hint_index_board_1m_projection.v1"
HINT_1M_HASH_POLICY = "payload_hash_canonical_file_sha256_trace"

ALLOWED_HINT_WRITE_TABLES = [
    "common_market_data_run",
    "common_market_data_quality_item",
    "index_realtime_hint_projection_metric",
    "board_realtime_hint_projection_metric",
]

_METRIC_FACT_REQUIRED_FIELDS = (
    "projection_run_id",
    "trade_date",
    "metric_minute_label",
    "asset_kind",
    "identity_key",
    "code",
    "direction",
    "condition_key",
    "original_condition_key",
    "source_condition_pool_id",
    "source_minute_target_scope_id",
    "source_subscription_run_id",
    "source_artifact_path",
    "source_artifact_sha256",
    "source_previous_day_minute_run_id",
    "source_context_run_id",
    "proof_kind",
    "source_mode",
    "metric_role",
    "proof_owner",
    "proof_consumer",
    "not_n5_final_proof",
    "current_window_start",
    "current_window_end",
    "previous_completed_window_start",
    "previous_completed_window_end",
    "current_window_elapsed_count",
    "full_window_count",
    "projection_30m_type",
    "projection_30m_flag",
    "metric_ready",
    "blocked_reasons",
)

_RUN_ID_RE = re.compile(
    r"^realtime_hint_projection_metric_(?P<trade_date>\d{8})_until_(?P<until_hhmm>\d{4})"
    r"__asset_(?P<asset_scope>index_board)"
    r"__(?P<proof_kind>index_board_1m_hint_projection_v1(?:_midday_bridge_v1)?)"
    r"__(?P<source_subscription_run_id>"
    r"market_data_subscription_(?P<subscription_trade_date>\d{8})"
    r"_condition_layer_(?P<source_trade_date>\d{8})"
    r"_source_(?P=source_trade_date)_for_(?P=subscription_trade_date)_v(?P<subscription_version>\d+)"
    r")$"
)


class HintProjectionPersistenceError(RuntimeError):
    """Raised when the N3 HINT projection persistence contract is unsafe."""


def build_hint_projection_run_id(
    *,
    trade_date: str,
    until_hhmm: str,
    source_subscription_run_id: str,
    proof_kind: str = HINT_1M_PROOF_KIND,
) -> str:
    _validate_date(trade_date, "trade_date")
    _validate_hhmm(until_hhmm, "until_hhmm")
    _validate_proof_kind(proof_kind)
    if not source_subscription_run_id.startswith(f"market_data_subscription_{trade_date}_"):
        raise HintProjectionPersistenceError("source_subscription_run_id trade_date mismatch")
    run_id = (
        f"realtime_hint_projection_metric_{trade_date}_until_{until_hhmm}"
        f"__asset_index_board__{proof_kind}__{source_subscription_run_id}"
    )
    parse_hint_projection_run_id(run_id)
    return run_id


def parse_hint_projection_run_id(run_id: str) -> dict[str, str]:
    match = _RUN_ID_RE.match(str(run_id or ""))
    if not match:
        raise HintProjectionPersistenceError("invalid hint projection run_id")
    parsed = match.groupdict()
    _validate_date(parsed["trade_date"], "trade_date")
    _validate_hhmm(parsed["until_hhmm"], "until_hhmm")
    if parsed["subscription_trade_date"] != parsed["trade_date"]:
        raise HintProjectionPersistenceError("subscription trade_date mismatch")
    if parsed["asset_scope"] != "index_board":
        raise HintProjectionPersistenceError("asset_scope must be index_board")
    _validate_proof_kind(parsed["proof_kind"])
    return {
        "trade_date": parsed["trade_date"],
        "until_hhmm": parsed["until_hhmm"],
        "asset_scope": parsed["asset_scope"],
        "proof_kind": parsed["proof_kind"],
        "source_subscription_run_id": parsed["source_subscription_run_id"],
        "source_trade_date": parsed["source_trade_date"],
        "subscription_version": parsed["subscription_version"],
    }


def build_hint_projection_write_plan(
    *,
    projection_run_id: str,
    proof_rows: Sequence[Mapping[str, Any]],
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_artifact_path: str,
    source_artifact_sha256: str,
    source_artifact_payload_hash: str | None = None,
    source_artifact_file_sha256: str | None = None,
    source_previous_day_minute_run_id: str,
    source_context_run_id: str,
) -> dict[str, Any]:
    parsed = parse_hint_projection_run_id(projection_run_id)
    if parsed["source_subscription_run_id"] != source_subscription_run_id:
        raise HintProjectionPersistenceError("source_subscription_run_id mismatch")
    _require(source_condition_run_id, "source_condition_run_id")
    _require(source_artifact_path, "source_artifact_path")
    _require(source_artifact_sha256, "source_artifact_sha256")
    payload_hash = source_artifact_payload_hash or source_artifact_sha256
    _require(payload_hash, "source_artifact_payload_hash")
    if source_artifact_sha256 != payload_hash:
        raise HintProjectionPersistenceError("payload hash mismatch with source_artifact_sha256")
    _require(source_previous_day_minute_run_id, "source_previous_day_minute_run_id")
    _require(source_context_run_id, "source_context_run_id")

    metric_rows: dict[str, list[dict[str, Any]]] = {"index": [], "board": []}
    excluded_metric_rows: list[dict[str, Any]] = []
    for row in proof_rows:
        materialized = _materialize_metric_row(
            row,
            parsed=parsed,
            projection_run_id=projection_run_id,
            source_condition_run_id=source_condition_run_id,
            source_subscription_run_id=source_subscription_run_id,
            source_artifact_path=source_artifact_path,
            source_artifact_sha256=payload_hash,
            source_artifact_payload_hash=payload_hash,
            source_artifact_file_sha256=source_artifact_file_sha256,
            source_previous_day_minute_run_id=source_previous_day_minute_run_id,
            source_context_run_id=source_context_run_id,
        )
        insert_blockers = _metric_fact_insert_blockers(materialized)
        if insert_blockers:
            if materialized["metric_ready"]:
                raise HintProjectionPersistenceError(
                    "metric_ready HINT proof row missing insert-required fields: "
                    f"{materialized.get('identity_key')}:{','.join(insert_blockers)}"
                )
            excluded_metric_rows.append(_metric_fact_exclusion(materialized, insert_blockers))
            continue
        metric_rows[materialized["asset_kind"]].append(materialized)
    metric_rows = {asset: rows for asset, rows in metric_rows.items() if rows}

    rows_by_asset = {asset: len(rows) for asset, rows in metric_rows.items()}
    ready_count = sum(1 for rows in metric_rows.values() for row in rows if row["metric_ready"])
    not_ready_count = sum(1 for rows in metric_rows.values() for row in rows if not row["metric_ready"])
    projection_distribution = Counter(
        row["projection_30m_type"] for rows in metric_rows.values() for row in rows
    )
    exclusion_reason_counts = Counter(
        reason for row in excluded_metric_rows for reason in row.get("blocked_reasons", [])
    )
    insert_blocker_counts = Counter(
        reason for row in excluded_metric_rows for reason in row.get("insert_blockers", [])
    )
    quality_items = [
        {
            "run_id": projection_run_id,
            "source_condition_run_id": source_condition_run_id,
            "for_trade_date": parsed["trade_date"],
            "source_trade_date": parsed["source_trade_date"],
            "data_domain": "common",
            "layer_scope": "market_data_run",
            "table_name": "index/board_realtime_hint_projection_metric",
            "gate_code": "N3_HINT_INDEX_BOARD_1M_PROOF_PERSISTENCE_READY",
            "gate_name": "N3 HINT index/board 1m proof persistence plan",
            "severity": "P2",
            "status": "passed",
            "expected_value": str(len(proof_rows)),
            "actual_value": str(len(proof_rows)),
            "details": {
                "proof_kind": parsed["proof_kind"],
                "rows_by_asset": rows_by_asset,
                "metric_fact_rows": sum(rows_by_asset.values()),
                "metric_fact_exclusion_count": len(excluded_metric_rows),
                "projection_type_distribution": dict(projection_distribution),
                "source_artifact_payload_hash": payload_hash,
                "source_artifact_file_sha256": source_artifact_file_sha256,
                "source_artifact_hash_policy": HINT_1M_HASH_POLICY,
                "writes_outbox": False,
            },
        }
    ]
    if excluded_metric_rows:
        quality_items.append(
            {
                "run_id": projection_run_id,
                "source_condition_run_id": source_condition_run_id,
                "for_trade_date": parsed["trade_date"],
                "source_trade_date": parsed["source_trade_date"],
                "data_domain": "common",
                "layer_scope": "market_data_run",
                "table_name": "index/board_realtime_hint_projection_metric",
                "gate_code": "N3_HINT_INDEX_BOARD_1M_PROOF_NOT_READY_EXCLUDED_FROM_FACT",
                "gate_name": "N3 HINT not-ready proof rows excluded from metric fact",
                "severity": "P1",
                "status": "warning",
                "expected_value": "0",
                "actual_value": str(len(excluded_metric_rows)),
                "details": {
                    "proof_kind": parsed["proof_kind"],
                    "exclusion_reason_counts": dict(exclusion_reason_counts),
                    "insert_blocker_counts": dict(insert_blocker_counts),
                    "sample_excluded_metric_rows": excluded_metric_rows[:20],
                    "writes_outbox": False,
                },
            }
        )
    return {
        "projection_run_id": projection_run_id,
        "proof_kind": parsed["proof_kind"],
        "allowed_write_tables": list(ALLOWED_HINT_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "touches_n4_n5_n6": False,
        "stock_rows": 0,
        "rows_by_asset": rows_by_asset,
        "metric_ready": {"ready": ready_count, "not_ready": not_ready_count},
        "proof_rows_input_total": len(proof_rows),
        "metric_fact_exclusion_count": len(excluded_metric_rows),
        "metric_fact_exclusion_reason_counts": dict(exclusion_reason_counts),
        "projection_type_distribution": dict(projection_distribution),
        "common_market_data_run": {
            "run_id": projection_run_id,
            "source_condition_run_id": source_condition_run_id,
            "for_trade_date": parsed["trade_date"],
            "source_trade_date": parsed["source_trade_date"],
            "prev_trade_date": parsed["source_trade_date"],
            "mode": "execute",
            "status": "passed",
            "market_data_pulled": False,
            "market_data_fact_written": True,
            "downstream_layers_touched": False,
            "worker_started": False,
            "raw_json": {
                "stage": "N3-HINT-index-board-1m-projection-persistence",
                "proof_kind": parsed["proof_kind"],
                "source_artifact_path": source_artifact_path,
                "source_artifact_sha256": payload_hash,
                "source_artifact_payload_hash": payload_hash,
                "source_artifact_file_sha256": source_artifact_file_sha256,
                "source_artifact_hash_policy": HINT_1M_HASH_POLICY,
                "writes_outbox": False,
                "not_n5_final_proof": True,
                "proof_rows_input_total": len(proof_rows),
                "metric_fact_exclusion_count": len(excluded_metric_rows),
                "metric_fact_exclusion_reason_counts": dict(exclusion_reason_counts),
            },
        },
        "quality_items": quality_items,
        "metric_rows": metric_rows,
    }


def ensure_clean_hint_projection_target(snapshot: Mapping[str, Any], projection_run_id: str) -> None:
    dirty = {
        key: int(snapshot.get(key) or 0)
        for key in (
            "run_exists",
            "quality_rows",
            "index_rows",
            "board_rows",
            "outbox_refs",
            "inbox_refs",
            "checkpoint_refs",
            "n4_refs",
            "n5_refs",
            "n6_refs",
        )
        if int(snapshot.get(key) or 0) != 0
    }
    if dirty:
        raise HintProjectionPersistenceError(f"dirty hint projection target for {projection_run_id}: {dirty}")


def build_hint_projection_rollback_sql(projection_run_id: str) -> str:
    parse_hint_projection_run_id(projection_run_id)
    return f"""-- N3 HINT index/board 1m projection proof rollback.
-- Boundary: rollback only proposed HINT proof rows, quality rows, and run row.
-- Hard-fail before delete if event infra or downstream N4/N5/N6/user/sim refs exist.
\\set ON_ERROR_STOP on

BEGIN;

SELECT set_config('app.n3_hint_projection_run_id', '{projection_run_id}', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.n3_hint_projection_run_id');
  outbox_refs BIGINT := 0;
  outbox_delivered_or_delivering_refs BIGINT := 0;
  inbox_refs BIGINT := 0;
  checkpoint_refs BIGINT := 0;
  n4_refs BIGINT := 0;
  n5_refs BIGINT := 0;
  n6_refs BIGINT := 0;
  downstream_flags BIGINT := 0;
BEGIN
  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO outbox_delivered_or_delivering_refs
  FROM common_event_outbox
  WHERE (source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%')
    AND status IN ('delivered', 'delivering');

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = target_run_id
     OR payload_json::TEXT LIKE '%' || target_run_id || '%'
     OR raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%'
     OR last_event_id LIKE '%' || target_run_id || '%';

  IF to_regclass('common_trigger_state') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_trigger_state WHERE to_jsonb(common_trigger_state)::TEXT LIKE $1'
      INTO n4_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('common_trigger_match') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM common_trigger_match WHERE to_jsonb(common_trigger_match)::TEXT LIKE $2'
      INTO n4_refs USING n4_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('common_action_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_run WHERE to_jsonb(common_action_run)::TEXT LIKE $1'
      INTO n5_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM common_action_event WHERE to_jsonb(common_action_event)::TEXT LIKE $2'
      INTO n5_refs USING n5_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_projection_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_projection_run WHERE to_jsonb(user_projection_run)::TEXT LIKE $1'
      INTO n6_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_signal_projection WHERE to_jsonb(user_signal_projection)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_signal_card WHERE to_jsonb(user_signal_card)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;

  SELECT count(*) INTO downstream_flags
  FROM common_market_data_run
  WHERE run_id = target_run_id
    AND (coalesce(downstream_layers_touched, false) OR coalesce(worker_started, false));

  IF outbox_refs <> 0
     OR outbox_delivered_or_delivering_refs <> 0
     OR inbox_refs <> 0
     OR checkpoint_refs <> 0
     OR n4_refs <> 0
     OR n5_refs <> 0
     OR n6_refs <> 0
     OR downstream_flags <> 0 THEN
    RAISE EXCEPTION 'N3 HINT projection rollback blocked for %, outbox=%, delivered_or_delivering=%, inbox=%, checkpoint=%, n4=%, n5=%, n6=%, downstream_or_worker=%',
      target_run_id, outbox_refs, outbox_delivered_or_delivering_refs, inbox_refs, checkpoint_refs, n4_refs, n5_refs, n6_refs, downstream_flags;
  END IF;
END $$;

DELETE FROM common_market_data_quality_item
WHERE run_id = current_setting('app.n3_hint_projection_run_id')
   OR details::TEXT LIKE '%' || current_setting('app.n3_hint_projection_run_id') || '%';

DELETE FROM index_realtime_hint_projection_metric
WHERE projection_run_id = current_setting('app.n3_hint_projection_run_id');

DELETE FROM board_realtime_hint_projection_metric
WHERE projection_run_id = current_setting('app.n3_hint_projection_run_id');

DELETE FROM common_market_data_run
WHERE run_id = current_setting('app.n3_hint_projection_run_id')
  AND coalesce(downstream_layers_touched, false) = false
  AND coalesce(worker_started, false) = false;

COMMIT;
"""


def _materialize_metric_row(
    row: Mapping[str, Any],
    *,
    parsed: Mapping[str, str],
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_artifact_path: str,
    source_artifact_sha256: str,
    source_artifact_payload_hash: str,
    source_artifact_file_sha256: str | None,
    source_previous_day_minute_run_id: str,
    source_context_run_id: str,
) -> dict[str, Any]:
    asset_kind = str(row.get("asset_kind") or "")
    if asset_kind not in {"index", "board"}:
        raise HintProjectionPersistenceError(f"stock/non-index-board proof row is forbidden: {asset_kind}")
    parsed_proof_kind = str(parsed["proof_kind"])
    row_proof_kind = str(row.get("proof_kind") or "")
    _validate_proof_kind(row_proof_kind)
    if parsed_proof_kind == HINT_1M_PROOF_KIND and row_proof_kind != HINT_1M_PROOF_KIND:
        raise HintProjectionPersistenceError(f"proof_kind mismatch for {row.get('identity_key')}")
    if parsed_proof_kind == HINT_1M_MIDDAY_BRIDGE_PROOF_KIND and row.get("midday_bridge_policy") != "hint_1300_as_1130_close_v1":
        raise HintProjectionPersistenceError(f"midday bridge trace missing for {row.get('identity_key')}")
    for key, expected in (
        ("source_mode", HINT_1M_SOURCE_MODE),
        ("metric_role", HINT_1M_METRIC_ROLE),
        ("proof_owner", HINT_1M_PROOF_OWNER),
        ("proof_consumer", HINT_1M_PROOF_CONSUMER),
    ):
        if row.get(key) != expected:
            raise HintProjectionPersistenceError(f"{key} mismatch for {row.get('identity_key')}")
    if row.get("not_n5_final_proof") is not True:
        raise HintProjectionPersistenceError("not_n5_final_proof must be true")
    projection_type = str(row.get("projection_30m_type") or "unknown")
    if projection_type not in {"volume_up", "shrink_down", "none", "unknown"}:
        raise HintProjectionPersistenceError("projection_30m_type is not allowed")
    identity_key = str(row.get("identity_key") or "")
    if not identity_key.startswith(f"{asset_kind}:"):
        raise HintProjectionPersistenceError("identity_key asset prefix mismatch")
    metric_ready = bool(row.get("valid")) and projection_type != "unknown"
    blocked_reasons = list(row.get("blocked_reasons") or [])
    raw_json = {
        "proof": dict(row),
        "projection_run_proof_kind": parsed_proof_kind,
        "source_artifact_path": source_artifact_path,
        "source_artifact_sha256": source_artifact_sha256,
        "source_artifact_payload_hash": source_artifact_payload_hash,
        "source_artifact_file_sha256": source_artifact_file_sha256,
        "source_artifact_hash_policy": HINT_1M_HASH_POLICY,
        "source_subscription_run_id": source_subscription_run_id,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "source_context_run_id": source_context_run_id,
        "writes_outbox": False,
        "not_n5_final_proof": True,
    }
    trace_json = {
        "projection_run_id": projection_run_id,
        "projection_run_proof_kind": parsed_proof_kind,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_artifact_payload_hash": source_artifact_payload_hash,
        "source_artifact_file_sha256": source_artifact_file_sha256,
        "source_artifact_hash_policy": HINT_1M_HASH_POLICY,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "source_context_run_id": source_context_run_id,
        "blocked_reasons": blocked_reasons,
        "midday_bridge_policy": row.get("midday_bridge_policy"),
        "raw_minute_label": row.get("raw_minute_label"),
        "logical_minute_label": row.get("logical_minute_label"),
    }
    return {
        "projection_run_id": projection_run_id,
        "trade_date": parsed["trade_date"],
        "metric_minute_label": parsed["until_hhmm"],
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "code": row.get("code") or identity_key.split(":")[-1],
        "name": row.get("name"),
        "direction": row.get("direction"),
        "condition_key": row.get("condition_key"),
        "original_condition_key": row.get("original_condition_key") or row.get("condition_key"),
        "source_condition_pool_id": row.get("source_condition_pool_id"),
        "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        "source_subscription_run_id": source_subscription_run_id,
        "source_artifact_path": source_artifact_path,
        "source_artifact_sha256": source_artifact_sha256,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "source_context_run_id": source_context_run_id,
        "proof_kind": HINT_1M_PROOF_KIND,
        "source_mode": HINT_1M_SOURCE_MODE,
        "metric_role": HINT_1M_METRIC_ROLE,
        "proof_owner": HINT_1M_PROOF_OWNER,
        "proof_consumer": HINT_1M_PROOF_CONSUMER,
        "not_n5_final_proof": True,
        "projection_schema_version": HINT_1M_PROJECTION_SCHEMA_VERSION,
        "current_window_start": row.get("current_window_start"),
        "current_window_end": row.get("current_window_end"),
        "previous_completed_window_start": row.get("previous_completed_window_start"),
        "previous_completed_window_end": row.get("previous_completed_window_end"),
        "current_window_elapsed_count": row.get("current_window_elapsed_count"),
        "full_window_count": row.get("full_window_count"),
        "current_30m_price": row.get("current_30m_price"),
        "current_30m_elapsed_amount": row.get("current_30m_elapsed_amount"),
        "previous_day_same_elapsed_30m_amount": row.get("previous_day_same_elapsed_30m_amount"),
        "previous_day_full_30m_amount": row.get("previous_day_full_30m_amount"),
        "current_30m_virtual_amount": row.get("current_30m_virtual_amount"),
        "reference_30m_amount": row.get("reference_30m_amount"),
        "reference_30m_entity_high": row.get("reference_30m_entity_high"),
        "reference_30m_entity_low": row.get("reference_30m_entity_low"),
        "projection_30m_type": projection_type,
        "projection_30m_flag": bool(row.get("projection_30m_flag")),
        "metric_ready": metric_ready,
        "blocked_reasons": blocked_reasons,
        "raw_json": raw_json,
        "trace_json": trace_json,
    }


def _metric_fact_insert_blockers(row: Mapping[str, Any]) -> list[str]:
    missing = [
        field
        for field in _METRIC_FACT_REQUIRED_FIELDS
        if row.get(field) is None or row.get(field) == ""
    ]
    blockers = [f"missing_required_metric_fact_field:{field}" for field in missing]
    for field in ("current_window_elapsed_count", "full_window_count"):
        value = row.get(field)
        if value is not None:
            try:
                if int(value) <= 0:
                    blockers.append(f"non_positive_metric_fact_field:{field}")
            except (TypeError, ValueError):
                blockers.append(f"invalid_metric_fact_field:{field}")
    return blockers


def _metric_fact_exclusion(row: Mapping[str, Any], insert_blockers: Sequence[str]) -> dict[str, Any]:
    return {
        "asset_kind": row.get("asset_kind"),
        "identity_key": row.get("identity_key"),
        "condition_key": row.get("condition_key"),
        "direction": row.get("direction"),
        "current_window_start": row.get("current_window_start"),
        "current_window_end": row.get("current_window_end"),
        "previous_completed_window_start": row.get("previous_completed_window_start"),
        "previous_completed_window_end": row.get("previous_completed_window_end"),
        "projection_30m_type": row.get("projection_30m_type"),
        "metric_ready": False,
        "blocked_reasons": list(row.get("blocked_reasons") or []),
        "insert_blockers": list(insert_blockers),
    }


def _validate_date(value: str, field: str) -> None:
    try:
        datetime.strptime(str(value), "%Y%m%d")
    except ValueError as exc:
        raise HintProjectionPersistenceError(f"invalid {field}") from exc


def _validate_hhmm(value: str, field: str) -> None:
    text = str(value)
    if not re.match(r"^\d{4}$", text):
        raise HintProjectionPersistenceError(f"invalid {field}")
    hour = int(text[:2])
    minute = int(text[2:])
    if hour > 23 or minute > 59:
        raise HintProjectionPersistenceError(f"invalid {field}")


def _validate_proof_kind(value: str) -> None:
    if value not in ALLOWED_HINT_1M_PROOF_KINDS:
        raise HintProjectionPersistenceError("proof_kind is not allowed")


def _require(value: Any, field: str) -> None:
    if value in (None, ""):
        raise HintProjectionPersistenceError(f"missing {field}")
