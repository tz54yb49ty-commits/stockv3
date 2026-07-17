import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MIDDAY_BRIDGE_PROOF_KIND = "index_board_1m_hint_projection_v1_midday_bridge_v1"


def _args(**overrides):
    values = {
        "for_trade_date": "20260630",
        "target_run_id": "n3_hint_index_board_1m_source_payload_20260630_until_source_returned_v1",
        "n4_context_run_id": "trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1",
        "subscription_run_id": "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1",
        "hint_proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
    }
    if "for_trade_date" in overrides and "subscription_run_id" not in overrides:
        trade_date = str(overrides["for_trade_date"])
        values["target_run_id"] = (
            f"n3_hint_index_board_1m_source_payload_{trade_date}_until_source_returned_v1"
        )
        values["subscription_run_id"] = (
            f"market_data_subscription_{trade_date}_condition_layer_20260629_source_20260629_for_{trade_date}_v1"
        )
        values["n4_context_run_id"] = (
            f"trigger_context_snapshot_{trade_date}_condition_layer_20260629_source_20260629_for_{trade_date}_v1__atomic_rule_v1"
        )
    values.update(overrides)
    return SimpleNamespace(**values)


def _report():
    return {
        "step_id": "n3_hint_source_fetch",
        "target_absence_checked": True,
        "target_absence_check_status": "passed",
    }


def _scope(*, index=True, board=True, stock_hint_excluded_count=3, for_trade_date="20260630"):
    scope = {
        "for_trade_date": for_trade_date,
        "n4_context_run_id": "ctx",
        "n4_context_status": "passed",
        "source_scope_policy": "n4_context_hint_index_board_frequency8_v1",
        "stock_hint_excluded_count": stock_hint_excluded_count,
        "stock_rows": [],
        "stock_excluded_count": stock_hint_excluded_count,
    }
    scope["index_1m_objects"] = (
        [
            {
                "asset_kind": "index",
                "identity_key": "index:SH:000001",
                "exchange": "SH",
                "code": "000001",
                "name": "上证指数",
                "direction": "buy",
                "condition_key": "BUY_HINT",
                "source_condition_pool_id": 1,
                "source_minute_target_scope_id": 2,
            }
        ]
        if index
        else []
    )
    scope["board_1m_objects"] = (
        [
            {
                "asset_kind": "board",
                "identity_key": "board:TDX:881001",
                "exchange": "TDX",
                "code": "881001",
                "name": "行业板块",
                "direction": "buy",
                "condition_key": "BUY_HINT",
                "source_condition_pool_id": 1,
                "source_minute_target_scope_id": 2,
            }
        ]
        if board
        else []
    )
    scope["index_object_count"] = len(scope["index_1m_objects"])
    scope["board_object_count"] = len(scope["board_1m_objects"])
    scope["index_board_1m_count"] = scope["index_object_count"] + scope["board_object_count"]
    return scope


class ScopeLoader:
    def __init__(self, scope):
        self.scope = scope
        self.calls = 0

    def load_n3_hint_frequency8_scope(self, *, args, report, dependencies, config=None):
        self.calls += 1
        return self.scope


class PreviousDayRowsLoader:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def load_n3_hint_previous_day_reference_rows(self, **_kwargs):
        self.calls += 1
        return {
            "previous_day_1m_rows": self.rows,
            "source_previous_day_minute_run_id": "previous_day_run",
        }


class CleanTargetSnapshotLoader:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or {
            "run_exists": 0,
            "quality_rows": 0,
            "index_rows": 0,
            "board_rows": 0,
            "outbox_refs": 0,
            "inbox_refs": 0,
            "checkpoint_refs": 0,
            "n4_refs": 0,
            "n5_refs": 0,
            "n6_refs": 0,
        }
        self.calls = 0
        self.target_run_ids = []

    def load_n3_hint_target_snapshot(self, **_kwargs):
        self.calls += 1
        return self.snapshot

    def load_n3_hint_idempotency_snapshot(self, **_kwargs):
        self.calls += 1
        self.target_run_ids.append(str(_kwargs.get("target_run_id") or ""))
        return self.snapshot


class FailIfCalledArtifactWriter:
    def __init__(self):
        self.calls = 0

    def write_n3_hint_frequency8_artifacts(self, **_kwargs):
        self.calls += 1
        raise AssertionError("artifact writer must not run for a passed idempotent target")


class MarketAdapter:
    def __init__(self, *, rows_by_identity=None):
        self.rows_by_identity = rows_by_identity or {}
        self.index_board_calls = []
        self.stock_calls = 0

    def fetch_index_board_1m_rows(self, *, obj, symbol=None, frequency=8, start=0, offset=800, market=None):
        self.index_board_calls.append(
            {
                "identity_key": obj["identity_key"],
                "symbol": symbol,
                "frequency": frequency,
                "start": start,
                "offset": offset,
                "market": market,
            }
        )
        return self.rows_by_identity.get(obj["identity_key"], [])

    def fetch_stock_quotes(self, *_args, **_kwargs):
        self.stock_calls += 1
        raise AssertionError("stock quote fetch is forbidden for HINT source")


class FakeMootdxClient:
    def __init__(self, *, rows_by_symbol=None):
        self.rows_by_symbol = rows_by_symbol or {}
        self.index_calls = []
        self.quote_calls = []

    def index(self, *, symbol=None, frequency=8, start=0, offset=800, market=None):
        self.index_calls.append(
            {
                "symbol": symbol,
                "frequency": frequency,
                "start": start,
                "offset": offset,
                "market": market,
            }
        )
        return self.rows_by_symbol.get(symbol, [])

    def quotes(self, *_args, **_kwargs):
        self.quote_calls.append(True)
        raise AssertionError("stock quote fetch is forbidden for HINT source")


class FakeScopeConnection:
    def __init__(self, *, context_status="passed", rows_by_table=None):
        self.context_status = context_status
        self.rows_by_table = rows_by_table or {}
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        self.statements.append(sql)
        normalized = " ".join(sql.lower().split())
        if normalized in {"begin read only", "rollback"}:
            return FakeCursor([])
        if "from common_trigger_run" in normalized:
            return FakeCursor([{"status": self.context_status}] if self.context_status else [])
        for table in ("stock_trigger_context_snapshot", "index_trigger_context_snapshot", "board_trigger_context_snapshot"):
            if f"from {table}" in normalized:
                return FakeCursor(self.rows_by_table.get(table, []))
        raise AssertionError(f"unexpected SQL: {sql}")


class FakePreviousDayReferenceConnection:
    def __init__(self, *, cumulative_rows=None, entity_rows=None):
        self.cumulative_rows = list(cumulative_rows or [])
        self.entity_rows = list(entity_rows or [])
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from board_previous_day_minute_cumulative" in normalized:
            return FakeCursor(self.cumulative_rows)
        if "from board_minute_bar_1m" in normalized:
            return FakeCursor(self.entity_rows)
        if "from index_previous_day_minute_cumulative" in normalized:
            return FakeCursor([])
        if "from index_minute_bar_1m" in normalized:
            return FakeCursor([])
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeTargetSnapshotConnection:
    def __init__(self, *, table_counts=None, existing_tables=None, columns_by_table=None):
        self.table_counts = table_counts or {}
        self.existing_tables = set(existing_tables or self.table_counts)
        self.columns_by_table = columns_by_table or {}
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if normalized in {"begin read only", "rollback"}:
            return FakeCursor([])
        if normalized.startswith("select to_regclass"):
            table_name = str(params[0])
            return FakeCursor([(table_name if table_name in self.existing_tables else None,)])
        if "from information_schema.columns" in normalized:
            table_name = str(params[0])
            requested = set(params[1])
            rows = [
                {"column_name": column}
                for column in self.columns_by_table.get(table_name, ())
                if column in requested
            ]
            return FakeCursor(rows)
        if " from " in normalized and normalized.startswith("select count(*)"):
            table_name = normalized.split(" from ", 1)[1].split()[0]
            return FakeCursor([(self.table_counts.get(table_name, 0),)])
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeExecuteConnection:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        return FakeCursor([])


def _raw_row_for_date(trade_date, label, *, marker="mootdx_index_frequency_8", amount=100, close=1.5):
    formatted_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
    return {
        "datetime": f"{formatted_date} {label}:00",
        "open": 1,
        "high": 2,
        "low": 0.5,
        "close": close,
        "amount": amount,
        "source_marker": marker,
    }


def _raw_row(label, *, marker="mootdx_index_frequency_8", amount=100, close=1.5):
    return _raw_row_for_date("20260630", label, marker=marker, amount=amount, close=close)


def _labels_between(start, end):
    hour, minute = [int(part) for part in start.split(":")]
    end_hour, end_minute = [int(part) for part in end.split(":")]
    labels = []
    while (hour, minute) <= (end_hour, end_minute):
        labels.append(f"{hour:02d}:{minute:02d}")
        minute += 1
        if minute == 60:
            hour += 1
            minute = 0
    return labels


def _hint_source_payload_for_preflight(*, target_run_id):
    rows = []
    for label in ["10:01", "10:30", *_labels_between("10:31", "10:44")]:
        rows.append(
            {
                "asset_kind": "board",
                "identity_key": "board:TDX:881001",
                "exchange": "TDX",
                "code": "881001",
                "name": "行业板块",
                "bar_time": f"2026-07-01T{label}:00+08:00",
                "datetime": f"2026-07-01T{label}:00+08:00",
                "minute_label": label,
                "open": 10,
                "high": 12,
                "low": 8,
                "close": 11,
                "amount": 100,
                "source_marker": "mootdx_index_frequency_8",
                "trade_date": "20260701",
                "source_trade_date": "20260701",
            }
        )
    return {
        "proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
        "hint_proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
        "source_mode": "index_board_frequency8_1m",
        "asset_scope": "index_board_only",
        "for_trade_date": "20260701",
        "target_run_id": target_run_id,
        "n4_context_run_id": "trigger_context_snapshot_20260701_condition_layer_20260630_source_20260630_for_20260701_v1__atomic_rule_v1",
        "subscription_run_id": "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1",
        "proof_input_time": "2026-07-01T10:44:00+08:00",
        "actual_until_hhmm": "1044",
        "index_board_1m_rows": rows,
        "source_payload_counts": {"index_rows": 0, "board_rows": len(rows), "stock_rows": 0},
        "source_object_counts": {"index": 0, "board": 1, "stock_excluded": 35},
        "source_scope_identity_keys": {"index": [], "board": ["board:TDX:881001"]},
        "stock_rows": 0,
        "stock_excluded_count": 35,
        "midday_bridge_policy": "hint_1300_as_1130_close_v1",
        "database_written": False,
        "writes_outbox": False,
    }


def _previous_day_rows_for_preflight():
    return [
        {
            "asset_kind": "board",
            "identity_key": "board:TDX:881001",
            "trade_date": "20260630",
            "canonical_minute_label": label,
            "minute_label": label,
            "amount": 100,
            "source_marker": "a1_previous_day_cumulative_alias",
        }
        for label in _labels_between("10:31", "11:00")
    ]


def _previous_day_rows_for_first_window_preflight():
    rows = []
    for label in _labels_between("09:31", "10:00"):
        rows.append(
            {
                "asset_kind": "board",
                "identity_key": "board:TDX:881001",
                "trade_date": "20260702",
                "canonical_minute_label": label,
                "minute_label": label,
                "open": 8,
                "close": 8,
                "amount": 50,
                "source_marker": "a1_previous_day_cumulative_alias",
            }
        )
    for label in _labels_between("14:31", "15:00"):
        rows.append(
            {
                "asset_kind": "board",
                "identity_key": "board:TDX:881001",
                "trade_date": "20260702",
                "canonical_minute_label": label,
                "minute_label": label,
                "open": 7,
                "close": 9,
                "amount": 1,
                "source_marker": "a1_previous_day_cumulative_alias",
            }
        )
    return rows


def _passed_hint_idempotency_snapshot(source_payload, **overrides):
    counts = dict(source_payload.get("source_payload_counts") or {})
    rows_by_asset = {
        asset_kind: int(counts.get(f"{asset_kind}_rows") or 0)
        for asset_kind in ("index", "board")
    }
    for_trade_date = str(source_payload.get("for_trade_date") or "")
    subscription_run_id = str(source_payload.get("subscription_run_id") or "")
    source_condition_run_id = subscription_run_id.removeprefix(
        f"market_data_subscription_{for_trade_date}_"
    )
    source_trade_date = source_condition_run_id.split("_source_", 1)[0].removeprefix("condition_layer_")
    common = {
        "run_exists": 1,
        "run_status": "passed",
        "run_p0_count": 0,
        "run_for_trade_date": for_trade_date,
        "run_source_trade_date": source_trade_date,
        "run_source_condition_run_id": source_condition_run_id,
        "run_raw_json": {
            "proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
            "source_artifact_path": str(source_payload.get("source_artifact_path") or ""),
            "source_artifact_payload_hash": str(source_payload.get("payload_hash") or ""),
            "source_artifact_file_sha256": str(source_payload.get("source_artifact_file_sha256") or ""),
            "source_artifact_hash_policy": "payload_hash_canonical_file_sha256_trace",
            "rows_by_asset": rows_by_asset,
            "proof_rows_input_total": sum(rows_by_asset.values()),
            "metric_fact_exclusion_count": 0,
            "writes_outbox": False,
        },
        "quality_rows": 1,
        "quality_passed_rows": 1,
        "quality_p0_failures": 0,
        "canonical_quality_rows": 1,
        "canonical_quality_passed_rows": 1,
        "allowed_warning_rows": 0,
        "allowed_warning_valid_rows": 0,
        "unexpected_quality_rows": 0,
        "canonical_quality_actual_value": str(sum(rows_by_asset.values())),
        "allowed_warning_actual_value": "",
        "outbox_refs": 0,
        "inbox_refs": 0,
        "checkpoint_refs": 0,
        "n4_refs": 3,
        "n5_refs": 3,
        "n6_refs": 0,
    }
    for asset_kind in ("index", "board"):
        row_count = rows_by_asset[asset_kind]
        common.update(
            {
                f"{asset_kind}_rows": row_count,
                f"{asset_kind}_ready_rows": row_count,
                f"{asset_kind}_not_ready_rows": 0,
                f"{asset_kind}_invalid_ready_rows": 0,
                f"{asset_kind}_artifact_paths": (
                    [str(source_payload.get("source_artifact_path") or "")] if row_count else []
                ),
                f"{asset_kind}_artifact_hashes": (
                    [str(source_payload.get("payload_hash") or "")] if row_count else []
                ),
                f"{asset_kind}_trade_dates": (
                    [str(source_payload.get("for_trade_date") or "")] if row_count else []
                ),
                f"{asset_kind}_metric_minute_labels": (
                    [str(source_payload.get("actual_until_hhmm") or "")] if row_count else []
                ),
                f"{asset_kind}_subscription_run_ids": (
                    [str(source_payload.get("subscription_run_id") or "")] if row_count else []
                ),
                f"{asset_kind}_proof_kinds": (["index_board_1m_hint_projection_v1"] if row_count else []),
            }
        )
    common.update(overrides)
    return common


def _cumulative_row(identity_key, label, cumulative, *, elapsed_index):
    return {
        "asset_kind": "board",
        "identity_key": identity_key,
        "source_trade_date": "20260702",
        "canonical_minute_label": label,
        "cumulative_amount_yuan": cumulative,
        "code": identity_key.rsplit(":", 1)[-1],
        "exchange": "TDX",
        "elapsed_index": elapsed_index,
    }


def _previous_day_cumulative_rows_for_first_window(identity_key="board:TDX:881001"):
    rows = []
    cumulative = 0
    elapsed_index = 1
    for label in _labels_between("09:31", "10:00"):
        cumulative += 50
        rows.append(_cumulative_row(identity_key, label, cumulative, elapsed_index=elapsed_index))
        elapsed_index += 1
    for label in _labels_between("14:31", "15:00"):
        cumulative += 1
        rows.append(_cumulative_row(identity_key, label, cumulative, elapsed_index=elapsed_index))
        elapsed_index += 1
    return rows


def _previous_day_cumulative_rows_for_first_window_datetime_labels(identity_key="board:TDX:881001"):
    rows = []
    cumulative = 0
    elapsed_index = 1
    for label in _labels_between("09:31", "10:00"):
        cumulative += 50
        rows.append(
            _cumulative_row(
                identity_key,
                f"2026-07-02 {label}",
                cumulative,
                elapsed_index=elapsed_index,
            )
        )
        elapsed_index += 1
    for label in _labels_between("14:31", "15:00"):
        cumulative += 1
        rows.append(
            _cumulative_row(
                identity_key,
                f"2026-07-02 {label}",
                cumulative,
                elapsed_index=elapsed_index,
            )
        )
        elapsed_index += 1
    return rows


def _previous_day_last_30m_entity_rows(identity_key="board:TDX:881001"):
    return [
        {
            "asset_kind": "board",
            "identity_key": identity_key,
            "trade_date": "20260702",
            "minute_label": "14:31",
            "open": 7,
            "close": 8,
            "code": identity_key.rsplit(":", 1)[-1],
            "exchange": "TDX",
        },
        {
            "asset_kind": "board",
            "identity_key": identity_key,
            "trade_date": "20260702",
            "minute_label": "15:00",
            "open": 9,
            "close": 11,
            "code": identity_key.rsplit(":", 1)[-1],
            "exchange": "TDX",
        },
    ]


def _sample_execute_proof_row(index, *, projection_30m_type):
    return {
        "asset_kind": "board",
        "identity_key": f"board:TDX:881{index:03d}",
        "code": f"881{index:03d}",
        "name": f"行业{index}",
        "direction": "buy",
        "condition_key": "BUY_HINT",
        "original_condition_key": "BUY_HINT",
        "source_condition_pool_id": 1000 + index,
        "source_minute_target_scope_id": 2000 + index,
        "proof_kind": "index_board_1m_hint_projection_v1",
        "source_mode": "index_board_frequency8_1m",
        "metric_role": "hint_trigger_proof",
        "proof_owner": "N3",
        "proof_consumer": "N4",
        "not_n5_final_proof": True,
        "valid": True,
        "midday_bridge_policy": "hint_1300_as_1130_close_v1",
        "raw_minute_label": "10:44",
        "logical_minute_label": "10:44",
        "current_window_start": "10:31",
        "current_window_end": "11:00",
        "previous_completed_window_start": "10:01",
        "previous_completed_window_end": "10:30",
        "current_window_elapsed_count": 14,
        "full_window_count": 30,
        "current_30m_price": 10,
        "current_30m_elapsed_amount": 1000,
        "previous_day_same_elapsed_30m_amount": 900,
        "previous_day_full_30m_amount": 1800,
        "current_30m_virtual_amount": 2000,
        "reference_30m_amount": 1800,
        "reference_30m_entity_high": 11,
        "reference_30m_entity_low": 9,
        "projection_30m_type": projection_30m_type,
        "projection_30m_flag": projection_30m_type != "none",
        "blocked_reasons": [],
    }


def _write_execute_contract_artifacts(tmpdir, *, target_run_id=None, write_plan=None):
    from ashare_v3.market.hint_1m_projection_persistence import (
        build_hint_projection_rollback_sql,
        build_hint_projection_write_plan,
    )

    target_run_id = target_run_id or (
        "realtime_hint_projection_metric_20260701_until_1044__asset_index_board__"
        "index_board_1m_hint_projection_v1_midday_bridge_v1__"
        "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"
    )
    proof_rows = [
        *[_sample_execute_proof_row(index, projection_30m_type="volume_up") for index in range(1, 4)],
        *[_sample_execute_proof_row(index, projection_30m_type="none") for index in range(4, 7)],
    ]
    write_plan = write_plan or build_hint_projection_write_plan(
        projection_run_id=target_run_id,
        proof_rows=proof_rows,
        source_condition_run_id="condition_layer_20260630_source_20260630_for_20260701_v1",
        source_subscription_run_id="market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1",
        source_artifact_path="docs/intraday_live_current/20260701/N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json",
        source_artifact_sha256="payload-hash",
        source_artifact_payload_hash="payload-hash",
        source_artifact_file_sha256="file-hash",
        source_previous_day_minute_run_id=(
            "previous_day_minute_preload_20260630_for_20260701__"
            "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"
        ),
        source_context_run_id="trigger_context_snapshot_20260701_condition_layer_20260630_source_20260630_for_20260701_v1__atomic_rule_v1",
    )
    contract = {
        "result": "EXECUTE_READY_REAL_IO_CONTRACT",
        "target_run_id": target_run_id,
        "actual_until_hhmm": "1044",
        "proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
        "source_artifact_payload_hash": "payload-hash",
        "source_artifact_file_sha256": "file-hash",
        "write_plan": write_plan,
        "rollback_sql": build_hint_projection_rollback_sql(target_run_id),
        "writes_outbox": False,
        "database_written": False,
        "market_data_pulled": False,
    }
    preflight = {
        "result": "EXECUTE_READY_REAL_IO_CONTRACT",
        "target_run_id": target_run_id,
        "actual_until_hhmm": "1044",
        "proof_rows_total": 6,
        "rows_by_asset": {"board": 6},
        "metric_ready": {"ready": 6, "not_ready": 0},
        "projection_type_distribution": {"none": 3, "volume_up": 3},
        "stock_rows": 0,
        "rollback_ready": True,
        "writes_outbox": False,
        "database_written": False,
        "market_data_pulled": False,
    }
    contract_path = Path(tmpdir) / "contract.json"
    preflight_path = Path(tmpdir) / "preflight.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    preflight_path.write_text(json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return contract_path, preflight_path, write_plan


def _context_row(asset_kind, identity_key, *, condition_key="BUY_HINT", status="passed", code=None, exchange=None):
    code = code or identity_key.rsplit(":", 1)[-1]
    return {
        "trigger_context_id": f"{asset_kind}-{identity_key}-{condition_key}",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "exchange": exchange or ("TDX" if asset_kind == "board" else "SH"),
        "code": code,
        "display_code": code,
        "name": f"{asset_kind}-{code}",
        "direction": "buy" if condition_key == "BUY_HINT" else "sell",
        "condition_key": condition_key,
        "is_hint_scope": True,
        "quality_status": status,
        "for_trade_date": "20260630",
        "source_condition_pool_id": 1,
        "source_minute_target_scope_id": 2,
    }


class N3HintFrequency8SourceProviderTest(unittest.TestCase):
    def test_hint_proof_preflight_retargets_stale_source_target_to_actual_hhmm(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintProofPreflightBackend,
            N3HintProofPreflightProvider,
            compute_n3_hint_frequency8_source_payload_hash,
        )

        stale_target = (
            "realtime_hint_projection_metric_20260701_until_1043__asset_index_board__"
            "index_board_1m_hint_projection_v1_midday_bridge_v1__"
            "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"
        )
        expected_target = stale_target.replace("_until_1043__", "_until_1044__")
        payload = _hint_source_payload_for_preflight(target_run_id=stale_target)
        payload["payload_hash"] = compute_n3_hint_frequency8_source_payload_hash(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json"
            contract_path = Path(tmpdir) / "contract.json"
            preflight_path = Path(tmpdir) / "preflight.json"
            payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

            provider = N3HintProofPreflightProvider(
                backend=N3HintProofPreflightBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope(index=False, stock_hint_excluded_count=35, for_trade_date="20260701")),
                    previous_day_rows_loader=PreviousDayRowsLoader(_previous_day_rows_for_preflight()),
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            )
            result = provider.build_n3_hint_proof_preflight(
                args=_args(
                    for_trade_date="20260701",
                    target_run_id=stale_target,
                    n4_context_run_id="trigger_context_snapshot_20260701_condition_layer_20260630_source_20260630_for_20260701_v1__atomic_rule_v1",
                    subscription_run_id="market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1",
                    source_condition_run_id="condition_layer_20260630_source_20260630_for_20260701_v1",
                    source_artifact_path=str(payload_path),
                    contract_path=str(contract_path),
                    preflight_path=str(preflight_path),
                ),
                report={**_report(), "step_id": "n3_hint_proof_preflight"},
                dependencies=N3RealIODependencies(),
            )

            self.assertEqual(result["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
            self.assertEqual(result["target_run_id"], expected_target)
            self.assertEqual(result["received_target_run_id"], stale_target)
            self.assertTrue(result["retargeted_from_stale_input"])
            self.assertEqual(result["actual_until_hhmm"], "1044")
            self.assertEqual(result["proof_rows_total"], 1)
            self.assertEqual(result["rows_by_asset"], {"board": 1})
            self.assertEqual(result["stock_rows"], 0)
            self.assertEqual(result["source_artifact_payload_hash"], payload["payload_hash"])
            self.assertFalse(result["market_data_pulled"])
            self.assertFalse(result["database_written"])
            self.assertFalse(result["writes_outbox"])
            self.assertTrue(contract_path.exists())
            self.assertTrue(preflight_path.exists())

            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["target_run_id"], expected_target)
            self.assertEqual(preflight["target_run_id"], expected_target)
            metric_row = contract["write_plan"]["metric_rows"]["board"][0]
            self.assertEqual(metric_row["metric_minute_label"], "1044")
            self.assertEqual(metric_row["trace_json"]["midday_bridge_policy"], "hint_1300_as_1130_close_v1")

    def test_hint_proof_preflight_blocks_dirty_target_before_materialization(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintProofPreflightBackend,
            N3HintProofPreflightProvider,
            compute_n3_hint_frequency8_source_payload_hash,
        )

        target = (
            "realtime_hint_projection_metric_20260701_until_1044__asset_index_board__"
            "index_board_1m_hint_projection_v1_midday_bridge_v1__"
            "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"
        )
        payload = _hint_source_payload_for_preflight(target_run_id=target)
        payload["payload_hash"] = compute_n3_hint_frequency8_source_payload_hash(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "payload.json"
            contract_path = Path(tmpdir) / "contract.json"
            preflight_path = Path(tmpdir) / "preflight.json"
            payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

            provider = N3HintProofPreflightProvider(
                backend=N3HintProofPreflightBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                    previous_day_rows_loader=PreviousDayRowsLoader(_previous_day_rows_for_preflight()),
                    target_snapshot_loader=CleanTargetSnapshotLoader({"run_exists": 1}),
                )
            )
            result = provider.build_n3_hint_proof_preflight(
                args=_args(
                    for_trade_date="20260701",
                    target_run_id=target,
                    n4_context_run_id="trigger_context_snapshot_20260701_condition_layer_20260630_source_20260630_for_20260701_v1__atomic_rule_v1",
                    subscription_run_id="market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1",
                    source_artifact_path=str(payload_path),
                    contract_path=str(contract_path),
                    preflight_path=str(preflight_path),
                ),
                report={**_report(), "step_id": "n3_hint_proof_preflight"},
                dependencies=N3RealIODependencies(),
            )

            self.assertEqual(result["result"], "BLOCKED_N3_HINT_PROOF_PREFLIGHT")
            self.assertIn("dirty hint projection target", result["reason"])
            self.assertFalse(contract_path.exists())
            self.assertFalse(preflight_path.exists())
            self.assertFalse(result["database_written"])
            self.assertFalse(result["writes_outbox"])

    def test_hint_proof_preflight_first_30m_uses_previous_trade_date_last_30m_reference(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintProofPreflightBackend,
            N3HintProofPreflightProvider,
            compute_n3_hint_frequency8_source_payload_hash,
        )

        target = (
            "realtime_hint_projection_metric_20260703_until_0931__asset_index_board__"
            "index_board_1m_hint_projection_v1_midday_bridge_v1__"
            "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
        )
        payload = {
            "proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
            "hint_proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
            "source_mode": "index_board_frequency8_1m",
            "asset_scope": "index_board_only",
            "for_trade_date": "20260703",
            "target_run_id": target,
            "n4_context_run_id": "trigger_context_snapshot_20260703_condition_layer_20260702_source_20260702_for_20260703_v1__atomic_rule_v1",
            "subscription_run_id": "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1",
            "proof_input_time": "2026-07-03T09:31:00+08:00",
            "actual_until_hhmm": "0931",
            "index_board_1m_rows": [
                {
                    "asset_kind": "board",
                    "identity_key": "board:TDX:881001",
                    "exchange": "TDX",
                    "code": "881001",
                    "name": "行业板块",
                    "bar_time": "2026-07-03T09:31:00+08:00",
                    "datetime": "2026-07-03T09:31:00+08:00",
                    "minute_label": "09:31",
                    "open": 10,
                    "high": 10,
                    "low": 10,
                    "close": 10,
                    "amount": 100,
                    "source_marker": "mootdx_index_frequency_8",
                    "trade_date": "20260703",
                    "source_trade_date": "20260703",
                }
            ],
            "source_payload_counts": {"index_rows": 0, "board_rows": 1, "stock_rows": 0},
            "source_object_counts": {"index": 0, "board": 1, "stock_excluded": 0},
            "source_scope_identity_keys": {"index": [], "board": ["board:TDX:881001"]},
            "stock_rows": 0,
            "stock_excluded_count": 0,
            "midday_bridge_policy": "hint_1300_as_1130_close_v1",
            "database_written": False,
            "writes_outbox": False,
        }
        payload["payload_hash"] = compute_n3_hint_frequency8_source_payload_hash(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "N3_hint_index_board_1m_0931_midday_bridge_frequency8_payload.json"
            contract_path = Path(tmpdir) / "contract.json"
            preflight_path = Path(tmpdir) / "preflight.json"
            payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

            provider = N3HintProofPreflightProvider(
                backend=N3HintProofPreflightBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope(index=False, stock_hint_excluded_count=0, for_trade_date="20260703")),
                    previous_day_rows_loader=PreviousDayRowsLoader(_previous_day_rows_for_first_window_preflight()),
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            )
            result = provider.build_n3_hint_proof_preflight(
                args=_args(
                    for_trade_date="20260703",
                    target_run_id=target,
                    n4_context_run_id="trigger_context_snapshot_20260703_condition_layer_20260702_source_20260702_for_20260703_v1__atomic_rule_v1",
                    subscription_run_id="market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1",
                    source_condition_run_id="condition_layer_20260702_source_20260702_for_20260703_v1",
                    source_artifact_path=str(payload_path),
                    contract_path=str(contract_path),
                    preflight_path=str(preflight_path),
                ),
                report={**_report(), "step_id": "n3_hint_proof_preflight"},
                dependencies=N3RealIODependencies(),
            )

            self.assertEqual(result["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
            self.assertEqual(result["proof_rows_input_total"], 1)
            self.assertEqual(result["proof_rows_total"], 1)
            self.assertEqual(result["rows_by_asset"], {"board": 1})
            self.assertEqual(result["metric_ready"], {"ready": 1, "not_ready": 0})
            self.assertEqual(result["projection_type_distribution"], {"volume_up": 1})

            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            proof_row = contract["proof_rows"][0]
            self.assertTrue(proof_row["valid"], proof_row["blocked_reasons"])
            self.assertEqual(proof_row["previous_completed_window_start"], "14:31")
            self.assertEqual(proof_row["previous_completed_window_end"], "15:00")
            self.assertEqual(proof_row["previous_completed_window_source"], "previous_trade_date_last_30m")
            self.assertEqual(proof_row["reference_30m_entity_high"], 9.0)
            self.assertEqual(proof_row["reference_30m_entity_low"], 7.0)
            board_metric = contract["write_plan"]["metric_rows"]["board"][0]
            self.assertEqual(board_metric["previous_completed_window_start"], "14:31")
            self.assertEqual(board_metric["previous_completed_window_end"], "15:00")
            self.assertEqual(board_metric["trace_json"]["previous_completed_window_source"], "previous_trade_date_last_30m")

    def test_hint_proof_execute_consumes_materialized_write_plan_and_writes_rollback(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import N3HintProofExecuteBackend, N3HintProofExecuteProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            contract_path, preflight_path, _write_plan = _write_execute_contract_artifacts(tmpdir)
            rollback_path = Path(tmpdir) / "rollback.sql"
            report_path = Path(tmpdir) / "execute_report.json"
            conn = FakeExecuteConnection()
            provider = N3HintProofExecuteProvider(
                backend=N3HintProofExecuteBackend(
                    config={"database_url": "postgresql://not-used"},
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                    rollback_sql_path=str(rollback_path),
                )
            )

            with patch("scripts.n3_hint_frequency8_source_provider._connect_db", return_value=conn):
                result = provider.execute_n3_hint_projection_write_plan(
                    args=_args(
                        for_trade_date="20260701",
                        target_run_id=(
                            "realtime_hint_projection_metric_20260701_until_1044__asset_index_board__"
                            "index_board_1m_hint_projection_v1_midday_bridge_v1__"
                            "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"
                        ),
                        contract_path=str(contract_path),
                        preflight_path=str(preflight_path),
                        json_report_path=str(report_path),
                    ),
                    report={**_report(), "step_id": "n3_hint_proof_execute"},
                    dependencies=N3RealIODependencies(),
                )

            self.assertEqual(result["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
            self.assertEqual(result["rows_written"], {"index": 0, "board": 6, "stock": 0})
            self.assertEqual(result["projection_type_distribution"], {"none": 3, "volume_up": 3})
            self.assertTrue(result["database_written"])
            self.assertFalse(result["writes_outbox"])
            self.assertEqual(result["stock_rows"], 0)
            self.assertTrue(rollback_path.exists())
            self.assertIn("DELETE FROM board_realtime_hint_projection_metric", rollback_path.read_text(encoding="utf-8"))
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["target_run_id"], result["target_run_id"])
            sql_text = "\n".join(sql for sql, _params in conn.statements).lower()
            self.assertIn("insert into common_market_data_run", sql_text)
            self.assertIn("insert into common_market_data_quality_item", sql_text)
            self.assertIn("insert into board_realtime_hint_projection_metric", sql_text)
            self.assertNotIn("stock_realtime_hint_projection_metric", sql_text)
            self.assertNotIn("common_event_outbox", sql_text)

    def test_hint_proof_execute_fails_closed_for_stock_or_outbox_write_plan(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import N3HintProofExecuteBackend, N3HintProofExecuteProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            _contract_path, _preflight_path, write_plan = _write_execute_contract_artifacts(tmpdir)
            write_plan = dict(write_plan)
            write_plan["stock_rows"] = 1
            write_plan["writes_outbox"] = True
            contract_path, preflight_path, _ = _write_execute_contract_artifacts(tmpdir, write_plan=write_plan)
            conn = FakeExecuteConnection()
            provider = N3HintProofExecuteProvider(
                backend=N3HintProofExecuteBackend(
                    config={"database_url": "postgresql://not-used"},
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            )

            with patch("scripts.n3_hint_frequency8_source_provider._connect_db", return_value=conn):
                result = provider.execute_n3_hint_projection_write_plan(
                    args=_args(
                        for_trade_date="20260701",
                        target_run_id=write_plan["projection_run_id"],
                        contract_path=str(contract_path),
                        preflight_path=str(preflight_path),
                    ),
                    report={**_report(), "step_id": "n3_hint_proof_execute"},
                    dependencies=N3RealIODependencies(),
                )

            self.assertEqual(result["result"], "BLOCKED_N3_HINT_PROOF_EXECUTE")
            self.assertIn("stock_rows_forbidden", result["reason"])
            self.assertFalse(result["database_written"])
            self.assertEqual(conn.statements, [])

    def test_hint_proof_execute_fails_closed_for_stale_target_mismatch(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import N3HintProofExecuteBackend, N3HintProofExecuteProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            contract_path, preflight_path, _write_plan = _write_execute_contract_artifacts(tmpdir)
            stale_target = (
                "realtime_hint_projection_metric_20260701_until_1043__asset_index_board__"
                "index_board_1m_hint_projection_v1_midday_bridge_v1__"
                "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"
            )
            conn = FakeExecuteConnection()
            provider = N3HintProofExecuteProvider(
                backend=N3HintProofExecuteBackend(
                    config={"database_url": "postgresql://not-used"},
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            )

            with patch("scripts.n3_hint_frequency8_source_provider._connect_db", return_value=conn):
                result = provider.execute_n3_hint_projection_write_plan(
                    args=_args(
                        for_trade_date="20260701",
                        target_run_id=stale_target,
                        contract_path=str(contract_path),
                        preflight_path=str(preflight_path),
                    ),
                    report={**_report(), "step_id": "n3_hint_proof_execute"},
                    dependencies=N3RealIODependencies(),
                )

            self.assertEqual(result["result"], "BLOCKED_N3_HINT_PROOF_EXECUTE")
            self.assertIn("target_run_id_mismatch", result["reason"])
            self.assertFalse(result["database_written"])
            self.assertEqual(conn.statements, [])

    def test_hint_proof_execute_fails_closed_for_dirty_target_before_persistence(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import N3HintProofExecuteBackend, N3HintProofExecuteProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            contract_path, preflight_path, write_plan = _write_execute_contract_artifacts(tmpdir)
            conn = FakeExecuteConnection()
            provider = N3HintProofExecuteProvider(
                backend=N3HintProofExecuteBackend(
                    config={"database_url": "postgresql://not-used"},
                    target_snapshot_loader=CleanTargetSnapshotLoader({"run_exists": 1}),
                )
            )

            with patch("scripts.n3_hint_frequency8_source_provider._connect_db", return_value=conn):
                result = provider.execute_n3_hint_projection_write_plan(
                    args=_args(
                        for_trade_date="20260701",
                        target_run_id=write_plan["projection_run_id"],
                        contract_path=str(contract_path),
                        preflight_path=str(preflight_path),
                    ),
                    report={**_report(), "step_id": "n3_hint_proof_execute"},
                    dependencies=N3RealIODependencies(),
                )

            self.assertEqual(result["result"], "BLOCKED_N3_HINT_PROOF_EXECUTE")
            self.assertIn("dirty hint projection target", result["reason"])
            self.assertFalse(result["database_written"])
            self.assertEqual(conn.statements, [])

    def test_db_scope_loader_builds_board_scope_and_excludes_stock_hint(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import _load_n3_hint_frequency8_scope_with_connection

        rows_by_table = {
            "stock_trigger_context_snapshot": [
                _context_row("stock", f"stock:SH:600{i:03d}", code=f"600{i:03d}") for i in range(265)
            ],
            "index_trigger_context_snapshot": [],
            "board_trigger_context_snapshot": [
                _context_row("board", f"board:TDX:881{i:03d}", code=f"881{i:03d}") for i in range(24)
            ],
        }
        conn = FakeScopeConnection(rows_by_table=rows_by_table)

        scope = _load_n3_hint_frequency8_scope_with_connection(
            conn=conn,
            for_trade_date="20260630",
            n4_context_run_id="trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1",
        )

        self.assertEqual(scope["n4_context_status"], "passed")
        self.assertEqual(scope["for_trade_date"], "20260630")
        self.assertEqual(scope["board_hint_row_count"], 24)
        self.assertEqual(scope["index_hint_row_count"], 0)
        self.assertEqual(scope["stock_hint_row_count"], 265)
        self.assertEqual(scope["board_object_count"], 24)
        self.assertEqual(scope["index_object_count"], 0)
        self.assertEqual(scope["stock_hint_excluded_count"], 265)
        self.assertEqual(scope["index_board_1m_count"], 24)
        self.assertEqual(scope["stock_minute_bar_scope_count"], 0)
        self.assertEqual(len(scope["board_1m_objects"]), 24)
        self.assertEqual(scope["stock_1m_objects"], [])

    def test_db_scope_loader_fails_closed_for_context_status_and_duplicate_ambiguity(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import _load_n3_hint_frequency8_scope_with_connection

        not_passed = _load_n3_hint_frequency8_scope_with_connection(
            conn=FakeScopeConnection(context_status="failed"),
            for_trade_date="20260630",
            n4_context_run_id="ctx",
        )
        self.assertEqual(not_passed["result"], "BLOCKED_N3_HINT_SOURCE_SCOPE_NOT_READY")
        self.assertIn("n4_context_status=failed", not_passed["reason"])

        duplicate_rows = [
            _context_row("board", "board:TDX:881001", code="881001"),
            _context_row("board", "board:TDX:881001", code="881999"),
        ]
        duplicate = _load_n3_hint_frequency8_scope_with_connection(
            conn=FakeScopeConnection(rows_by_table={"board_trigger_context_snapshot": duplicate_rows}),
            for_trade_date="20260630",
            n4_context_run_id="ctx",
        )
        self.assertEqual(duplicate["result"], "BLOCKED_N3_HINT_SOURCE_SCOPE_NOT_READY")
        self.assertIn("duplicate_identity_ambiguity:board:board:TDX:881001", duplicate["reason"])

    def test_previous_day_reference_loader_merges_a1_last_30m_entity_open_close(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import _load_n3_hint_previous_day_reference_rows_with_connection

        conn = FakePreviousDayReferenceConnection(
            cumulative_rows=_previous_day_cumulative_rows_for_first_window(),
            entity_rows=_previous_day_last_30m_entity_rows(),
        )
        target_run_id = (
            "realtime_hint_projection_metric_20260703_until_0931__asset_index_board__"
            "index_board_1m_hint_projection_v1_midday_bridge_v1__"
            "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
        )

        result = _load_n3_hint_previous_day_reference_rows_with_connection(
            conn=conn,
            scope=_scope(index=False, stock_hint_excluded_count=0, for_trade_date="20260703"),
            target_run_id=target_run_id,
        )

        self.assertNotIn("result", result)
        rows_by_label = {row["minute_label"]: row for row in result["previous_day_1m_rows"]}
        self.assertEqual(rows_by_label["09:31"]["amount"], 50)
        self.assertNotIn("open", rows_by_label["09:31"])
        self.assertEqual(rows_by_label["14:31"]["open"], 7)
        self.assertEqual(rows_by_label["15:00"]["close"], 11)
        self.assertEqual(rows_by_label["14:31"]["source_marker"], "a1_previous_day_cumulative_alias")
        self.assertEqual(rows_by_label["14:31"]["entity_reference_source"], "previous_day_minute_bar_1m")
        self.assertEqual(result["previous_day_entity_reference_rows"], 2)
        self.assertEqual(result["previous_day_entity_reference_rows_merged"], 2)
        self.assertTrue(any("board_previous_day_minute_cumulative" in sql for sql, _params in conn.statements))
        self.assertTrue(any("board_minute_bar_1m" in sql for sql, _params in conn.statements))

    def test_previous_day_reference_loader_normalizes_datetime_cumulative_labels(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import (
            _cumulative_rows_to_1m_reference_rows,
            _load_n3_hint_previous_day_reference_rows_with_connection,
        )

        normalized_rows = _cumulative_rows_to_1m_reference_rows(
            [
                _cumulative_row("board:TDX:881001", "2026-07-02 09:31", 50, elapsed_index=1),
                _cumulative_row("board:TDX:881001", "2026-07-02T10:00:00+08:00", 100, elapsed_index=2),
                _cumulative_row("board:TDX:881001", "2026-07-02 13:00", 125, elapsed_index=3),
            ],
            expected_asset_kind="board",
        )

        self.assertEqual([row["minute_label"] for row in normalized_rows], ["09:31", "10:00", "11:30"])
        self.assertEqual(normalized_rows[0]["raw_cumulative_minute_label"], "2026-07-02 09:31")
        self.assertEqual(normalized_rows[1]["raw_cumulative_minute_label"], "2026-07-02T10:00:00+08:00")
        self.assertEqual(normalized_rows[2]["raw_cumulative_minute_label"], "2026-07-02 13:00")

        target_run_id = (
            "realtime_hint_projection_metric_20260703_until_0931__asset_index_board__"
            "index_board_1m_hint_projection_v1_midday_bridge_v1__"
            "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
        )
        result = _load_n3_hint_previous_day_reference_rows_with_connection(
            conn=FakePreviousDayReferenceConnection(
                cumulative_rows=_previous_day_cumulative_rows_for_first_window_datetime_labels(),
                entity_rows=_previous_day_last_30m_entity_rows(),
            ),
            scope=_scope(index=False, stock_hint_excluded_count=0, for_trade_date="20260703"),
            target_run_id=target_run_id,
        )

        rows_by_label = {row["minute_label"]: row for row in result["previous_day_1m_rows"]}
        self.assertEqual(rows_by_label["09:31"]["amount"], 50)
        self.assertEqual(rows_by_label["09:31"]["raw_cumulative_minute_label"], "2026-07-02 09:31")
        self.assertEqual(rows_by_label["14:31"]["open"], 7)
        self.assertEqual(rows_by_label["15:00"]["close"], 11)
        self.assertEqual(rows_by_label["14:31"]["raw_cumulative_minute_label"], "2026-07-02 14:31")
        self.assertEqual(result["previous_day_entity_reference_rows"], 2)
        self.assertEqual(result["previous_day_entity_reference_rows_merged"], 2)

    def test_previous_day_reference_loader_does_not_invent_missing_a1_entity_open_close(self) -> None:
        from ashare_v3.market.hint_1m_projection_proof import build_index_board_1m_hint_projection_proof
        from scripts.n3_hint_frequency8_source_provider import _load_n3_hint_previous_day_reference_rows_with_connection

        target_run_id = (
            "realtime_hint_projection_metric_20260703_until_0931__asset_index_board__"
            "index_board_1m_hint_projection_v1_midday_bridge_v1__"
            "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
        )
        result = _load_n3_hint_previous_day_reference_rows_with_connection(
            conn=FakePreviousDayReferenceConnection(
                cumulative_rows=_previous_day_cumulative_rows_for_first_window(),
                entity_rows=[],
            ),
            scope=_scope(index=False, stock_hint_excluded_count=0, for_trade_date="20260703"),
            target_run_id=target_run_id,
        )

        rows_by_label = {row["minute_label"]: row for row in result["previous_day_1m_rows"]}
        self.assertNotIn("open", rows_by_label["14:31"])
        self.assertEqual(result["previous_day_entity_reference_rows"], 0)
        self.assertEqual(result["previous_day_entity_reference_rows_merged"], 0)

        proof = build_index_board_1m_hint_projection_proof(
            asset_kind="board",
            identity_key="board:TDX:881001",
            for_trade_date="20260703",
            previous_trade_date="20260702",
            proof_input_time="2026-07-03T09:31:00+08:00",
            current_day_1m_rows=[
                {
                    "asset_kind": "board",
                    "identity_key": "board:TDX:881001",
                    "trade_date": "20260703",
                    "minute_label": "09:31",
                    "open": 10,
                    "close": 10,
                    "amount": 100,
                }
            ],
            previous_day_1m_rows=result["previous_day_1m_rows"],
            projection_run_id=target_run_id,
        )
        self.assertFalse(proof["valid"])
        self.assertIn("missing_previous_trade_date_last_30m_open_close", proof["blocked_reasons"])

    def test_target_snapshot_loader_uses_structured_event_refs_without_json_text_scans(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import _load_n3_hint_target_snapshot_with_connection

        conn = FakeTargetSnapshotConnection(
            table_counts={
                "common_market_data_run": 0,
                "common_market_data_quality_item": 0,
                "index_realtime_hint_projection_metric": 0,
                "board_realtime_hint_projection_metric": 0,
                "common_event_outbox": 2,
                "common_event_inbox": 3,
                "common_event_consumer_checkpoint": 5,
                "common_trigger_run": 0,
                "common_trigger_state": 0,
                "common_trigger_match": 0,
                "common_action_run": 0,
                "common_action_event": 0,
                "user_projection_run": 1,
                "user_signal_projection": 2,
                "user_signal_card": 3,
            },
            columns_by_table={
                "common_trigger_run": ("run_id",),
                "common_trigger_state": ("source_run_id",),
                "common_trigger_match": ("source_projection_run_id",),
                "common_action_run": ("source_run_id",),
                "common_action_event": ("trigger_run_id",),
                "user_projection_run": ("user_projection_run_id", "source_action_run_id"),
                "user_signal_projection": ("user_projection_run_id", "source_action_run_id"),
                "user_signal_card": ("user_projection_run_id", "source_action_run_id"),
            },
        )

        snapshot = _load_n3_hint_target_snapshot_with_connection(
            conn=conn,
            target_run_id="n3_hint_index_board_1m_source_payload_20260703_0931_midday_bridge_v1",
        )

        self.assertEqual(snapshot["outbox_refs"], 2)
        self.assertEqual(snapshot["inbox_refs"], 3)
        self.assertEqual(snapshot["checkpoint_refs"], 5)
        self.assertEqual(snapshot["n6_refs"], 6)
        executed_sql = "\n".join(sql for sql, _params in conn.statements).lower()
        for forbidden_fragment in (
            "payload_json::text",
            "raw_json::text",
            "checkpoint_payload::text",
            "details::text",
            " like ",
        ):
            self.assertNotIn(forbidden_fragment, executed_sql)
        self.assertIn(
            "from common_event_outbox where source_layer=%s and event_type = any(%s) and source_run_id=%s",
            " ".join(executed_sql.split()),
        )
        self.assertIn(
            "from common_event_inbox where source_layer=%s and source_run_id=%s",
            " ".join(executed_sql.split()),
        )
        self.assertIn("user_projection_run_id=%s", " ".join(executed_sql.split()))
        self.assertIn("source_action_run_id=%s", " ".join(executed_sql.split()))

    def test_target_snapshot_outbox_refs_use_existing_outbox_index_prefix(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import _load_n3_hint_target_snapshot_with_connection

        target_run_id = "n3_hint_index_board_1m_source_payload_20260703_0931_midday_bridge_v1"
        conn = FakeTargetSnapshotConnection(
            table_counts={
                "common_market_data_run": 0,
                "common_market_data_quality_item": 0,
                "index_realtime_hint_projection_metric": 0,
                "board_realtime_hint_projection_metric": 0,
                "common_event_outbox": 2,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
            },
        )

        snapshot = _load_n3_hint_target_snapshot_with_connection(conn=conn, target_run_id=target_run_id)

        self.assertEqual(snapshot["outbox_refs"], 2)
        outbox_statements = [
            (" ".join(sql.lower().split()), params)
            for sql, params in conn.statements
            if "from common_event_outbox" in " ".join(sql.lower().split())
            and "checkpoint" not in " ".join(sql.lower().split())
            and "from common_event_inbox" not in " ".join(sql.lower().split())
        ]
        self.assertEqual(len(outbox_statements), 1)
        outbox_sql, outbox_params = outbox_statements[0]
        self.assertIn("source_layer=%s", outbox_sql)
        self.assertIn("event_type = any(%s)", outbox_sql)
        self.assertIn("source_run_id=%s", outbox_sql)
        self.assertEqual(outbox_params[0], "N3_market_data")
        self.assertIn("MarketSnapshotUpdated", outbox_params[1])
        self.assertIn("MarketDisplaySnapshotUpdated", outbox_params[1])
        self.assertEqual(outbox_params[2], target_run_id)

    def test_target_snapshot_inbox_refs_use_direct_source_run_reference(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import _load_n3_hint_target_snapshot_with_connection

        target_run_id = "n3_hint_index_board_1m_source_payload_20260703_0931_midday_bridge_v1"
        conn = FakeTargetSnapshotConnection(
            table_counts={
                "common_market_data_run": 0,
                "common_market_data_quality_item": 0,
                "index_realtime_hint_projection_metric": 0,
                "board_realtime_hint_projection_metric": 0,
                "common_event_outbox": 0,
                "common_event_inbox": 3,
                "common_event_consumer_checkpoint": 0,
            },
        )

        snapshot = _load_n3_hint_target_snapshot_with_connection(conn=conn, target_run_id=target_run_id)

        self.assertEqual(snapshot["inbox_refs"], 3)
        inbox_statements = [
            (" ".join(sql.lower().split()), params)
            for sql, params in conn.statements
            if "from common_event_inbox" in " ".join(sql.lower().split())
        ]
        self.assertEqual(len(inbox_statements), 1)
        inbox_sql, inbox_params = inbox_statements[0]
        self.assertIn("from common_event_inbox", inbox_sql)
        self.assertIn("source_layer=%s", inbox_sql)
        self.assertIn("source_run_id=%s", inbox_sql)
        self.assertNotIn("from common_event_outbox", inbox_sql)
        self.assertEqual(inbox_params[0], "N3_market_data")
        self.assertEqual(inbox_params[1], target_run_id)

    def test_target_snapshot_loader_does_not_fallback_to_text_when_optional_ref_columns_missing(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import _load_n3_hint_target_snapshot_with_connection

        conn = FakeTargetSnapshotConnection(
            table_counts={
                "common_market_data_run": 0,
                "common_market_data_quality_item": 0,
                "index_realtime_hint_projection_metric": 0,
                "board_realtime_hint_projection_metric": 0,
                "common_event_outbox": 0,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
                "common_trigger_run": 0,
                "common_action_run": 0,
                "user_projection_run": 0,
            },
            columns_by_table={},
        )

        snapshot = _load_n3_hint_target_snapshot_with_connection(conn=conn, target_run_id="target_run")

        self.assertEqual(snapshot["n4_refs"], 0)
        self.assertEqual(snapshot["n5_refs"], 0)
        self.assertEqual(snapshot["n6_refs"], 0)
        executed_sql = "\n".join(sql for sql, _params in conn.statements).lower()
        self.assertNotIn("::text", executed_sql)
        self.assertNotIn(" like ", executed_sql)

    def test_default_backend_uses_db_scope_loader_then_blocks_on_missing_market_fetcher(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import N3HintFrequency8SourceBackend, N3HintFrequency8SourceProvider

        conn = FakeScopeConnection(
            rows_by_table={
                "stock_trigger_context_snapshot": [_context_row("stock", "stock:SH:600058", code="600058")],
                "board_trigger_context_snapshot": [_context_row("board", "board:TDX:881001", code="881001")],
            }
        )
        provider = N3HintFrequency8SourceProvider(
            backend=N3HintFrequency8SourceBackend(
                config={"database_url": "postgresql://not-used"},
                market_fetcher=None,
                artifact_writer=None,
            )
        )

        with patch("scripts.n3_hint_frequency8_source_provider._connect_db", return_value=conn):
            payload = provider.fetch_n3_hint_frequency8_source(
                args=_args(),
                report=_report(),
                dependencies=N3RealIODependencies(),
            )

        self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_MARKET_FETCHER")
        self.assertIn("market fetch dependency is required", payload["reason"])
        self.assertTrue(any("BEGIN READ ONLY" in statement for statement in conn.statements))
        self.assertTrue(any("ROLLBACK" in statement for statement in conn.statements))
        self.assertFalse(any(statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for statement in conn.statements))
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["writes_outbox"])

    def test_adapter_without_index_board_fetch_method_blocks_before_market_pull(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import fetch_n3_hint_frequency8_market_rows_from_adapter

        payload = fetch_n3_hint_frequency8_market_rows_from_adapter(
            args=_args(),
            scope=_scope(index=False),
            adapter=object(),
        )

        self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_MARKET_FETCHER")
        self.assertIn("market fetch dependency is required", payload["reason"])
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["writes_outbox"])

    def test_lazy_market_fetch_adapter_construction_does_not_call_client_factory(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import N3HintFrequency8MarketFetchAdapter

        calls = []

        def factory():
            calls.append("factory")
            return FakeMootdxClient()

        adapter = N3HintFrequency8MarketFetchAdapter(client_factory=factory)

        self.assertEqual(calls, [])
        self.assertTrue(callable(getattr(adapter, "fetch_index_board_1m_rows", None)))

    def test_lazy_market_fetch_adapter_fetches_index_board_only_and_preserves_datetime(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8MarketFetchAdapter,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
        )

        client = FakeMootdxClient(
            rows_by_symbol={
                "000001": [_raw_row("13:00")],
                "881001": [_raw_row("13:00", amount=200)],
            }
        )
        provider = N3HintFrequency8SourceProvider(
            backend=N3HintFrequency8SourceBackend(
                config={"database_url": "postgresql://not-used"},
                scope_loader=ScopeLoader(_scope()),
                market_fetcher=N3HintFrequency8MarketFetchAdapter(client_factory=lambda: client),
                artifact_writer=None,
                target_snapshot_loader=CleanTargetSnapshotLoader(),
            )
        )

        payload = provider.fetch_n3_hint_frequency8_source(
            args=_args(),
            report=_report(),
            dependencies=N3RealIODependencies(),
        )

        self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_ARTIFACT_WRITER")
        self.assertEqual(
            client.index_calls,
            [
                {"symbol": "000001", "frequency": 8, "start": 0, "offset": 800, "market": 1},
                {"symbol": "881001", "frequency": 8, "start": 0, "offset": 800, "market": None},
            ],
        )
        self.assertEqual(client.quote_calls, [])

    def test_payload_validation_rejects_missing_scoped_object(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import N3HintFrequency8SourceBackend, N3HintFrequency8SourceProvider

        provider = N3HintFrequency8SourceProvider(
            backend=N3HintFrequency8SourceBackend(
                config={"database_url": "postgresql://not-used"},
                scope_loader=ScopeLoader(_scope()),
                market_fetcher=MarketAdapter(rows_by_identity={"index:SH:000001": [_raw_row("13:00")]}),
                artifact_writer=None,
            )
        )

        payload = provider.fetch_n3_hint_frequency8_source(
            args=_args(),
            report=_report(),
            dependencies=N3RealIODependencies(),
        )

        self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_PAYLOAD_INVALID")
        self.assertIn("missing_scoped_object", payload["blocked_reasons"])
        self.assertFalse(payload["artifact_written"])
        self.assertFalse(payload["database_written"])

    def test_mocked_scope_fetch_and_temp_artifact_writer_produce_pass_contract(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceArtifactWriter,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
            compute_n3_hint_frequency8_source_payload_hash,
        )

        scope_loader = ScopeLoader(_scope())
        market = MarketAdapter(
            rows_by_identity={
                "index:SH:000001": [_raw_row("13:00")],
                "board:TDX:881001": [_raw_row("13:00", amount=200)],
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = N3HintFrequency8SourceProvider(
                backend=N3HintFrequency8SourceBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=scope_loader,
                    market_fetcher=market,
                    artifact_writer=N3HintFrequency8SourceArtifactWriter(output_root=tmpdir),
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            )
            payload = provider.fetch_n3_hint_frequency8_source(
                args=_args(),
                report=_report(),
                dependencies=N3RealIODependencies(),
            )

            self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
            self.assertEqual(scope_loader.calls, 1)
            self.assertEqual(len(market.index_board_calls), 2)
            self.assertEqual(market.stock_calls, 0)
            self.assertEqual(payload["actual_until_hhmm"], "1300")
            self.assertEqual(payload["proof_input_time"], "2026-06-30T13:00:00+08:00")
            self.assertEqual(payload["source_payload_counts"], {"index_rows": 1, "board_rows": 1, "stock_rows": 0})
            self.assertEqual(payload["source_object_counts"], {"index": 1, "board": 1, "stock_excluded": 3})
            self.assertEqual(payload["payload_hash"], compute_n3_hint_frequency8_source_payload_hash(payload))
            self.assertTrue(payload["source_artifact_path"].endswith("N3_hint_index_board_1m_1300_midday_bridge_frequency8_payload.json"))
            self.assertTrue(Path(payload["source_artifact_path"]).exists())
            self.assertTrue(Path(payload["source_report_path"]).exists())
            written = json.loads(Path(payload["source_artifact_path"]).read_text())
            self.assertEqual(written["payload_hash"], payload["payload_hash"])
            self.assertEqual(written["index_board_1m_rows"][0]["minute_label"], "13:00")
            self.assertNotIn("canonical_stock_quote_proof_minute", written["index_board_1m_rows"][0])
            self.assertFalse(payload["database_written"])
            self.assertFalse(payload["writes_outbox"])
            self.assertFalse(payload["touches_n4_n5_n6"])

    def test_source_fetch_waits_when_target_minute_is_ahead_of_common_latest_source(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceArtifactWriter,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
        )

        market = MarketAdapter(
            rows_by_identity={
                "index:SH:000001": [_raw_row("13:49")],
                "board:TDX:881001": [_raw_row("13:50", amount=200)],
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = N3HintFrequency8SourceProvider(
                backend=N3HintFrequency8SourceBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope()),
                    market_fetcher=market,
                    artifact_writer=N3HintFrequency8SourceArtifactWriter(output_root=tmpdir),
                )
            )
            payload = provider.fetch_n3_hint_frequency8_source(
                args=_args(),
                report=_report(),
                dependencies=N3RealIODependencies(),
            )

            self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_LATEST_BEFORE_TARGET")
            self.assertEqual(payload["status"], "waiting")
            self.assertEqual(payload["execution_mode"], "noop")
            self.assertEqual(payload["requested_target_minute_label"], "13:50")
            self.assertEqual(payload["common_latest_available_minute_label"], "13:49")
            self.assertEqual(payload["source_time_alignment_status"], "source_latest_before_target")
            self.assertEqual(payload["source_time_lagging_identity_samples"][0]["identity_key"], "index:SH:000001")
            self.assertFalse(payload["artifact_written"])
            self.assertFalse(payload["database_written"])
            self.assertFalse(payload["writes_outbox"])
            self.assertFalse(payload["touches_n4_n5_n6"])
            self.assertEqual(list(Path(tmpdir).glob("*.json")), [])

    def test_source_fetch_records_common_latest_trace_when_sources_are_complete(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceArtifactWriter,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            provider = N3HintFrequency8SourceProvider(
                backend=N3HintFrequency8SourceBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope()),
                    market_fetcher=MarketAdapter(
                        rows_by_identity={
                            "index:SH:000001": [_raw_row("13:50")],
                            "board:TDX:881001": [_raw_row("13:50", amount=200)],
                        }
                    ),
                    artifact_writer=N3HintFrequency8SourceArtifactWriter(output_root=tmpdir),
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            )
            payload = provider.fetch_n3_hint_frequency8_source(
                args=_args(),
                report=_report(),
                dependencies=N3RealIODependencies(),
            )

            self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
            self.assertEqual(payload["actual_until_hhmm"], "1350")
            self.assertEqual(payload["requested_target_minute_label"], "13:50")
            self.assertEqual(payload["common_latest_available_minute_label"], "13:50")
            self.assertEqual(payload["source_time_alignment_status"], "source_latest_matches_target")
            written = json.loads(Path(payload["source_artifact_path"]).read_text())
            self.assertEqual(written["source_time_alignment_status"], "source_latest_matches_target")

    def test_default_backend_binds_local_artifact_writer(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
            compute_n3_hint_frequency8_source_payload_hash,
        )

        market = MarketAdapter(rows_by_identity={"board:TDX:881001": [_raw_row_for_date("20260701", "10:21")]})
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = N3HintFrequency8SourceProvider(
                backend=N3HintFrequency8SourceBackend(
                    config={"database_url": "postgresql://not-used", "artifact_output_root": tmpdir},
                    scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                    market_fetcher=market,
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            )

            payload = provider.fetch_n3_hint_frequency8_source(
                args=_args(for_trade_date="20260701"),
                report=_report(),
                dependencies=N3RealIODependencies(),
            )

            self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
            self.assertEqual(payload["actual_until_hhmm"], "1021")
            self.assertTrue(payload["source_artifact_path"].startswith(str(Path(tmpdir) / "20260701")))
            self.assertTrue(payload["source_artifact_path"].endswith("N3_hint_index_board_1m_1021_midday_bridge_frequency8_payload.json"))
            self.assertTrue(payload["source_report_path"].endswith("N3_hint_index_board_1m_1021_midday_bridge_frequency8_fetch_report.json"))
            written_payload = json.loads(Path(payload["source_artifact_path"]).read_text())
            written_report = json.loads(Path(payload["source_report_path"]).read_text())
            self.assertEqual(written_payload["stock_rows"], 0)
            self.assertEqual(written_payload["payload_hash"], compute_n3_hint_frequency8_source_payload_hash(written_payload))
            self.assertEqual(written_report["normalization_trace"]["normalized_row_count"], 1)
            self.assertTrue(written_report["market_data_pulled"])
            self.assertFalse(written_report["database_written"])
            self.assertFalse(written_report["writes_outbox"])
            self.assertFalse(written_report["consumes_outbox"])
            self.assertFalse(written_report["updates_inbox_or_checkpoint"])
            self.assertFalse(written_report["starts_worker"])
            self.assertFalse(written_report["touches_n4_n5_n6"])

    def test_multiday_frequency8_rows_are_normalized_before_validation(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceArtifactWriter,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
            compute_n3_hint_frequency8_source_payload_hash,
        )

        market = MarketAdapter(
            rows_by_identity={
                "board:TDX:881001": [
                    _raw_row_for_date("20260625", "10:20"),
                    _raw_row_for_date("20260626", "11:30"),
                    _raw_row_for_date("20260630", "10:20"),
                    _raw_row_for_date("20260701", "10:20"),
                    _raw_row_for_date("20260701", "10:21"),
                ]
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = N3HintFrequency8SourceProvider(
                backend=N3HintFrequency8SourceBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                    market_fetcher=market,
                    artifact_writer=N3HintFrequency8SourceArtifactWriter(output_root=tmpdir),
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            )

            payload = provider.fetch_n3_hint_frequency8_source(
                args=_args(for_trade_date="20260701"),
                report=_report(),
                dependencies=N3RealIODependencies(),
            )

            self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
            self.assertEqual(payload["actual_until_hhmm"], "1021")
            self.assertEqual(payload["source_payload_counts"], {"index_rows": 0, "board_rows": 2, "stock_rows": 0})
            self.assertEqual(
                [row["minute_label"] for row in payload["index_board_1m_rows"]],
                ["10:20", "10:21"],
            )
            self.assertEqual({row["trade_date"] for row in payload["index_board_1m_rows"]}, {"20260701"})
            self.assertNotIn("11:30", {row["minute_label"] for row in payload["index_board_1m_rows"]})
            trace = payload["normalization_trace"]
            self.assertEqual(trace["raw_row_count"], 5)
            self.assertEqual(trace["normalized_row_count"], 2)
            self.assertEqual(trace["rows_dropped_date_mismatch"], 3)
            self.assertEqual(trace["rows_dropped_1130"], 0)
            self.assertEqual(trace["duplicate_rows_collapsed"], 0)
            self.assertEqual(trace["duplicate_conflict_count"], 0)
            self.assertEqual(trace["for_trade_date"], "20260701")
            self.assertEqual(
                trace["dates_seen"],
                ["20260625", "20260626", "20260630", "20260701"],
            )
            self.assertEqual(payload["payload_hash"], compute_n3_hint_frequency8_source_payload_hash(payload))
            written = json.loads(Path(payload["source_artifact_path"]).read_text())
            self.assertEqual(written["payload_hash"], compute_n3_hint_frequency8_source_payload_hash(written))
            self.assertEqual(written["normalization_trace"]["normalized_row_count"], 2)

    def test_exact_duplicate_object_minute_collapses_before_artifact_write(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceArtifactWriter,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
        )

        duplicate = _raw_row_for_date("20260701", "10:20", amount=100)
        market = MarketAdapter(rows_by_identity={"board:TDX:881001": [duplicate, dict(duplicate)]})
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = N3HintFrequency8SourceProvider(
                backend=N3HintFrequency8SourceBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                    market_fetcher=market,
                    artifact_writer=N3HintFrequency8SourceArtifactWriter(output_root=tmpdir),
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            )

            payload = provider.fetch_n3_hint_frequency8_source(
                args=_args(for_trade_date="20260701"),
                report=_report(),
                dependencies=N3RealIODependencies(),
            )

            self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
            self.assertEqual(len(payload["index_board_1m_rows"]), 1)
            self.assertEqual(payload["normalization_trace"]["duplicate_rows_collapsed"], 1)
            self.assertEqual(payload["normalization_trace"]["duplicate_conflict_count"], 0)

    def test_conflicting_duplicate_object_minute_blocks_before_artifact_writer(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import N3HintFrequency8SourceBackend, N3HintFrequency8SourceProvider

        market = MarketAdapter(
            rows_by_identity={
                "board:TDX:881001": [
                    _raw_row_for_date("20260701", "10:20", amount=100),
                    _raw_row_for_date("20260701", "10:20", amount=101),
                ]
            }
        )
        provider = N3HintFrequency8SourceProvider(
            backend=N3HintFrequency8SourceBackend(
                config={"database_url": "postgresql://not-used"},
                scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                market_fetcher=market,
                artifact_writer=object(),
            )
        )

        payload = provider.fetch_n3_hint_frequency8_source(
            args=_args(for_trade_date="20260701"),
            report=_report(),
            dependencies=N3RealIODependencies(),
        )

        self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_PAYLOAD_INVALID")
        self.assertIn("duplicate_object_minute_conflict", payload["blocked_reasons"])
        self.assertEqual(payload["normalization_trace"]["duplicate_conflict_count"], 1)
        self.assertFalse(payload["artifact_written"])
        self.assertFalse(payload["database_written"])

    def test_current_day_raw_1130_still_blocks(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import N3HintFrequency8SourceBackend, N3HintFrequency8SourceProvider

        provider = N3HintFrequency8SourceProvider(
            backend=N3HintFrequency8SourceBackend(
                config={"database_url": "postgresql://not-used"},
                scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                market_fetcher=MarketAdapter(rows_by_identity={"board:TDX:881001": [_raw_row_for_date("20260701", "11:30")]}),
                artifact_writer=object(),
            )
        )

        payload = provider.fetch_n3_hint_frequency8_source(
            args=_args(for_trade_date="20260701"),
            report=_report(),
            dependencies=N3RealIODependencies(),
        )

        self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_PAYLOAD_INVALID")
        self.assertIn("canonical_1130_forbidden", payload["blocked_reasons"])
        self.assertEqual(payload["normalization_trace"]["rows_dropped_1130"], 0)

    def test_stock_only_hint_scope_fails_closed(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import N3HintFrequency8SourceBackend, N3HintFrequency8SourceProvider

        provider = N3HintFrequency8SourceProvider(
            backend=N3HintFrequency8SourceBackend(
                config={"database_url": "postgresql://not-used"},
                scope_loader=ScopeLoader(_scope(index=False, board=False, stock_hint_excluded_count=9)),
                market_fetcher=MarketAdapter(),
                artifact_writer=None,
            )
        )
        payload = provider.fetch_n3_hint_frequency8_source(args=_args(), report=_report(), dependencies=N3RealIODependencies())

        self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_SCOPE_NOT_READY")
        self.assertIn("hint_index_board_scope_empty", payload["reason"])
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["artifact_written"])

    def test_payload_validation_rejects_fake_duplicate_and_rows_after_proof_time(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import N3HintFrequency8SourceBackend, N3HintFrequency8SourceProvider

        cases = [
            ("fake_source_marker", [_raw_row("13:00", marker="synthetic_mootdx_index_frequency_8")]),
            ("duplicate_object_minute_conflict", [_raw_row("13:00", amount=100), _raw_row("13:00", amount=101)]),
            (
                "row_after_proof_input_time",
                {
                    "proof_input_time": "2026-06-30T13:00:00+08:00",
                    "index_board_1m_rows": [
                        {
                            "asset_kind": "index",
                            "identity_key": "index:SH:000001",
                            "bar_time": "2026-06-30T13:01:00+08:00",
                            "open": 1,
                            "high": 2,
                            "low": 0.5,
                            "close": 1.5,
                            "amount": 100,
                            "source_marker": "mootdx_index_frequency_8",
                        }
                    ],
                },
            ),
        ]
        for expected_reason, raw_rows in cases:
            with self.subTest(expected_reason=expected_reason):
                if isinstance(raw_rows, dict):
                    market_fetcher = type(
                        "HighLevelFetcher",
                        (),
                        {"fetch_n3_hint_frequency8_market_rows": lambda self, **_kwargs: raw_rows},
                    )()
                else:
                    market_fetcher = MarketAdapter(rows_by_identity={"index:SH:000001": raw_rows})
                provider = N3HintFrequency8SourceProvider(
                    backend=N3HintFrequency8SourceBackend(
                        config={"database_url": "postgresql://not-used"},
                        scope_loader=ScopeLoader(_scope(board=False)),
                        market_fetcher=market_fetcher,
                        artifact_writer=None,
                    )
                )
                payload = provider.fetch_n3_hint_frequency8_source(
                    args=_args(),
                    report=_report(),
                    dependencies=N3RealIODependencies(),
                )

                self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_PAYLOAD_INVALID")
                self.assertIn(expected_reason, payload["blocked_reasons"])
                self.assertFalse(payload["artifact_written"])
                self.assertFalse(payload["database_written"])

    def test_passed_target_returns_noop_without_overwriting_candidate_drift(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            HINT_SOURCE_IDEMPOTENT_NOOP_RESULT,
            N3HintFrequency8SourceArtifactWriter,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
        )

        args = _args(for_trade_date="20260701")
        with tempfile.TemporaryDirectory() as tmpdir:
            first = N3HintFrequency8SourceProvider(
                backend=N3HintFrequency8SourceBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                    market_fetcher=MarketAdapter(
                        rows_by_identity={"board:TDX:881001": [_raw_row_for_date("20260701", "10:21", amount=100)]}
                    ),
                    artifact_writer=N3HintFrequency8SourceArtifactWriter(output_root=tmpdir),
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            ).fetch_n3_hint_frequency8_source(args=args, report=_report(), dependencies=N3RealIODependencies())
            payload_path = Path(first["source_artifact_path"])
            report_path = Path(first["source_report_path"])
            before = {
                "payload": payload_path.read_bytes(),
                "report": report_path.read_bytes(),
                "payload_mtime": payload_path.stat().st_mtime_ns,
                "report_mtime": report_path.stat().st_mtime_ns,
                "payload_inode": payload_path.stat().st_ino,
                "report_inode": report_path.stat().st_ino,
            }
            snapshot_loader = CleanTargetSnapshotLoader(_passed_hint_idempotency_snapshot(first))
            forbidden_writer = FailIfCalledArtifactWriter()
            second = N3HintFrequency8SourceProvider(
                backend=N3HintFrequency8SourceBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                    market_fetcher=MarketAdapter(
                        rows_by_identity={"board:TDX:881001": [_raw_row_for_date("20260701", "10:21", amount=999)]}
                    ),
                    artifact_writer=forbidden_writer,
                    target_snapshot_loader=snapshot_loader,
                )
            ).fetch_n3_hint_frequency8_source(args=args, report=_report(), dependencies=N3RealIODependencies())

            self.assertEqual(second["result"], HINT_SOURCE_IDEMPOTENT_NOOP_RESULT)
            self.assertEqual(second["status"], "noop")
            self.assertEqual(second["idempotency_decision"], "idempotent_pass")
            self.assertFalse(second["execute_contract_ready"])
            self.assertFalse(second["idempotent_target_execute_contract_ready"])
            self.assertTrue(second["candidate_differs_from_persisted"])
            self.assertEqual(second["payload_hash"], first["payload_hash"])
            self.assertEqual(second["downstream_refs"]["n4_refs"], 3)
            self.assertEqual(forbidden_writer.calls, 0)
            self.assertEqual(len(snapshot_loader.target_run_ids), 1)
            self.assertIn("_until_1021__", snapshot_loader.target_run_ids[0])
            self.assertEqual(payload_path.read_bytes(), before["payload"])
            self.assertEqual(report_path.read_bytes(), before["report"])
            self.assertEqual(payload_path.stat().st_mtime_ns, before["payload_mtime"])
            self.assertEqual(report_path.stat().st_mtime_ns, before["report_mtime"])
            self.assertEqual(payload_path.stat().st_ino, before["payload_inode"])
            self.assertEqual(report_path.stat().st_ino, before["report_inode"])

            from scripts import run_n3_hint_index_board_1m_source_fetch_once as source_child

            wrapper_report_path = Path(tmpdir) / "tmp" / "source_child_report.json"
            with patch("builtins.print"):
                returncode = source_child.main(
                    [
                        "--for-trade-date",
                        "20260701",
                        "--n4-context-run-id",
                        args.n4_context_run_id,
                        "--subscription-run-id",
                        args.subscription_run_id,
                        "--source-condition-run-id",
                        "condition_layer_20260629_source_20260629_for_20260701_v1",
                        "--target-run-id",
                        "n3_hint_index_board_1m_source_payload_20260701_until_source_returned_v1",
                        "--hint-proof-kind",
                        MIDDAY_BRIDGE_PROOF_KIND,
                        "--json-report-path",
                        str(wrapper_report_path),
                        "--execute",
                        "--user-confirmed",
                    ],
                    layer_runner=lambda **_kwargs: second,
                )
            self.assertEqual(returncode, 0)
            self.assertTrue(wrapper_report_path.is_file())
            self.assertEqual(payload_path.read_bytes(), before["payload"])
            self.assertEqual(report_path.read_bytes(), before["report"])
            self.assertEqual(payload_path.stat().st_mtime_ns, before["payload_mtime"])
            self.assertEqual(report_path.stat().st_mtime_ns, before["report_mtime"])
            self.assertEqual(payload_path.stat().st_ino, before["payload_inode"])
            self.assertEqual(report_path.stat().st_ino, before["report_inode"])

    def test_source_lineage_identity_must_be_canonical_before_artifact_write(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
        )

        mutations = {
            "source_candidate": {"target_run_id": "wrong"},
            "n4_context": {"n4_context_run_id": "wrong"},
        }
        for name, overrides in mutations.items():
            with self.subTest(name=name):
                writer = FailIfCalledArtifactWriter()
                result = N3HintFrequency8SourceProvider(
                    backend=N3HintFrequency8SourceBackend(
                        config={"database_url": "postgresql://not-used"},
                        scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                        market_fetcher=MarketAdapter(
                            rows_by_identity={
                                "board:TDX:881001": [_raw_row_for_date("20260701", "10:21")]
                            }
                        ),
                        artifact_writer=writer,
                        target_snapshot_loader=CleanTargetSnapshotLoader(),
                    )
                ).fetch_n3_hint_frequency8_source(
                    args=_args(for_trade_date="20260701", **overrides),
                    report=_report(),
                    dependencies=N3RealIODependencies(),
                )
                self.assertEqual(result["result"], "BLOCKED_N3_HINT_SOURCE_IDEMPOTENCY")
                self.assertIn("source_lineage_identity_mismatch", result["reason"])
                self.assertEqual(writer.calls, 0)

    def test_absent_target_reuses_exact_pair_and_blocks_different_candidate(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceArtifactWriter,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
        )

        args = _args(for_trade_date="20260701")
        with tempfile.TemporaryDirectory() as tmpdir:
            def run(amount):
                return N3HintFrequency8SourceProvider(
                    backend=N3HintFrequency8SourceBackend(
                        config={"database_url": "postgresql://not-used"},
                        scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                        market_fetcher=MarketAdapter(
                            rows_by_identity={
                                "board:TDX:881001": [_raw_row_for_date("20260701", "10:21", amount=amount)]
                            }
                        ),
                        artifact_writer=N3HintFrequency8SourceArtifactWriter(output_root=tmpdir),
                        target_snapshot_loader=CleanTargetSnapshotLoader(),
                    )
                ).fetch_n3_hint_frequency8_source(args=args, report=_report(), dependencies=N3RealIODependencies())

            first = run(100)
            payload_path = Path(first["source_artifact_path"])
            report_path = Path(first["source_report_path"])
            before = (payload_path.read_bytes(), report_path.read_bytes(), payload_path.stat().st_mtime_ns, report_path.stat().st_mtime_ns)
            same = run(100)
            self.assertEqual(same["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
            self.assertFalse(same["artifact_written"])
            self.assertTrue(same["artifact_reused"])
            self.assertEqual(
                (payload_path.read_bytes(), report_path.read_bytes(), payload_path.stat().st_mtime_ns, report_path.stat().st_mtime_ns),
                before,
            )
            different = run(101)
            self.assertEqual(different["result"], "BLOCKED_N3_HINT_SOURCE_ARTIFACT_WRITER")
            self.assertIn("artifact_pair_contract_mismatch", different["reason"])
            self.assertEqual(
                (payload_path.read_bytes(), report_path.read_bytes(), payload_path.stat().st_mtime_ns, report_path.stat().st_mtime_ns),
                before,
            )

    def test_existing_target_contract_tampering_remains_fail_closed(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceArtifactWriter,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
            classify_n3_hint_existing_target,
        )

        args = _args(for_trade_date="20260701")
        with tempfile.TemporaryDirectory() as tmpdir:
            source_payload = N3HintFrequency8SourceProvider(
                backend=N3HintFrequency8SourceBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                    market_fetcher=MarketAdapter(
                        rows_by_identity={"board:TDX:881001": [_raw_row_for_date("20260701", "10:21")]}
                    ),
                    artifact_writer=N3HintFrequency8SourceArtifactWriter(output_root=tmpdir),
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            ).fetch_n3_hint_frequency8_source(args=args, report=_report(), dependencies=N3RealIODependencies())
            base = _passed_hint_idempotency_snapshot(source_payload)
            from ashare_v3.market.hint_1m_projection_persistence import build_hint_projection_run_id

            target_run_id = build_hint_projection_run_id(
                trade_date=source_payload["for_trade_date"],
                until_hhmm=source_payload["actual_until_hhmm"],
                source_subscription_run_id=source_payload["subscription_run_id"],
                proof_kind=MIDDAY_BRIDGE_PROOF_KIND,
            )
            base["quality_rows"] = 2
            base["allowed_warning_rows"] = 1
            base["allowed_warning_valid_rows"] = 1
            base["allowed_warning_actual_value"] = "1"
            base["canonical_quality_actual_value"] = "2"
            base["run_raw_json"]["proof_rows_input_total"] = 2
            base["run_raw_json"]["metric_fact_exclusion_count"] = 1
            passed = classify_n3_hint_existing_target(
                target_run_id=target_run_id,
                snapshot=base,
                candidate_payload=source_payload,
            )
            self.assertEqual(passed["decision"], "idempotent_pass")

            mutations = {
                "failed_run": lambda value: value.update(run_status="failed"),
                "run_date": lambda value: value.update(run_for_trade_date="20260702"),
                "run_source_trade_date": lambda value: value.update(run_source_trade_date="20260628"),
                "run_source_condition": lambda value: value.update(run_source_condition_run_id="condition_layer_wrong"),
                "run_proof_kind": lambda value: value["run_raw_json"].update(proof_kind="wrong"),
                "quality_p0": lambda value: value.update(quality_p0_failures=1),
                "canonical_quality_missing": lambda value: value.update(canonical_quality_rows=0),
                "canonical_quality_not_passed": lambda value: value.update(canonical_quality_passed_rows=0),
                "unexpected_quality": lambda value: value.update(unexpected_quality_rows=1),
                "warning_shape": lambda value: value.update(allowed_warning_valid_rows=0),
                "canonical_quality_total": lambda value: value.update(canonical_quality_actual_value="3"),
                "warning_total": lambda value: value.update(allowed_warning_actual_value="2"),
                "proof_rows_total": lambda value: value["run_raw_json"].update(proof_rows_input_total=3),
                "exclusion_total": lambda value: value["run_raw_json"].update(metric_fact_exclusion_count=2),
                "writes_outbox": lambda value: value["run_raw_json"].update(writes_outbox=True),
                "hash_policy": lambda value: value["run_raw_json"].update(source_artifact_hash_policy="wrong"),
                "row_count": lambda value: value.update(board_rows=2),
                "ready_distribution": lambda value: value.update(board_invalid_ready_rows=1),
                "subscription": lambda value: value.update(board_subscription_run_ids=["wrong"]),
                "minute": lambda value: value.update(board_metric_minute_labels=["1022"]),
                "metric_hash": lambda value: value.update(board_artifact_hashes=["wrong"]),
                "n3_outbox_ref": lambda value: value.update(outbox_refs=1),
                "n3_inbox_ref": lambda value: value.update(inbox_refs=1),
                "n3_checkpoint_ref": lambda value: value.update(checkpoint_refs=1),
                "unexpected_n6_direct_ref": lambda value: value.update(n6_refs=1),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    snapshot = json.loads(json.dumps(base))
                    mutate(snapshot)
                    result = classify_n3_hint_existing_target(
                        target_run_id=target_run_id,
                        snapshot=snapshot,
                        candidate_payload=source_payload,
                    )
                    self.assertEqual(result["decision"], "blocked")

            partial_absent = dict(CleanTargetSnapshotLoader().snapshot)
            partial_absent["board_rows"] = 1
            self.assertEqual(
                classify_n3_hint_existing_target(
                    target_run_id=target_run_id,
                    snapshot=partial_absent,
                    candidate_payload=source_payload,
                )["decision"],
                "blocked",
            )

    def test_passed_target_with_all_proof_rows_legitimately_excluded_can_noop(self) -> None:
        from ashare_v3.market.hint_1m_projection_persistence import build_hint_projection_run_id
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceArtifactWriter,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
            classify_n3_hint_existing_target,
        )

        args = _args(for_trade_date="20260701")
        with tempfile.TemporaryDirectory() as tmpdir:
            source_payload = N3HintFrequency8SourceProvider(
                backend=N3HintFrequency8SourceBackend(
                    config={"database_url": "postgresql://not-used"},
                    scope_loader=ScopeLoader(_scope(index=False, for_trade_date="20260701")),
                    market_fetcher=MarketAdapter(
                        rows_by_identity={
                            "board:TDX:881001": [_raw_row_for_date("20260701", "10:21")]
                        }
                    ),
                    artifact_writer=N3HintFrequency8SourceArtifactWriter(output_root=tmpdir),
                    target_snapshot_loader=CleanTargetSnapshotLoader(),
                )
            ).fetch_n3_hint_frequency8_source(
                args=args,
                report=_report(),
                dependencies=N3RealIODependencies(),
            )
            snapshot = _passed_hint_idempotency_snapshot(source_payload)
            snapshot.update(
                {
                    "quality_rows": 2,
                    "allowed_warning_rows": 1,
                    "allowed_warning_valid_rows": 1,
                    "allowed_warning_actual_value": "1",
                    "canonical_quality_actual_value": "1",
                    "index_rows": 0,
                    "index_ready_rows": 0,
                    "index_not_ready_rows": 0,
                    "index_invalid_ready_rows": 0,
                    "board_rows": 0,
                    "board_ready_rows": 0,
                    "board_not_ready_rows": 0,
                    "board_invalid_ready_rows": 0,
                    "n4_refs": 0,
                    "n5_refs": 0,
                }
            )
            for asset_kind in ("index", "board"):
                for suffix in (
                    "artifact_paths",
                    "artifact_hashes",
                    "trade_dates",
                    "metric_minute_labels",
                    "subscription_run_ids",
                    "proof_kinds",
                ):
                    snapshot[f"{asset_kind}_{suffix}"] = []
            snapshot["run_raw_json"]["rows_by_asset"] = {}
            snapshot["run_raw_json"]["proof_rows_input_total"] = 1
            snapshot["run_raw_json"]["metric_fact_exclusion_count"] = 1
            target_run_id = build_hint_projection_run_id(
                trade_date=source_payload["for_trade_date"],
                until_hhmm=source_payload["actual_until_hhmm"],
                source_subscription_run_id=source_payload["subscription_run_id"],
                proof_kind=MIDDAY_BRIDGE_PROOF_KIND,
            )

            result = classify_n3_hint_existing_target(
                target_run_id=target_run_id,
                snapshot=snapshot,
                candidate_payload=source_payload,
            )

            self.assertEqual(result["decision"], "idempotent_pass")
            self.assertEqual(result["reason"], "noop_existing_hint_target_passed")

    def test_artifact_pair_rejects_identity_and_report_side_effect_tampering_with_rebound_file_sha(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8SourceArtifactWriter,
            inspect_n3_hint_artifact_pair,
        )

        source_target_run_id = (
            "n3_hint_index_board_1m_source_payload_20260701_until_source_returned_v1"
        )
        payload = _hint_source_payload_for_preflight(target_run_id=source_target_run_id)
        fetch_report = {
            "actual_until_hhmm": payload["actual_until_hhmm"],
            "proof_kind": payload["proof_kind"],
            "market_data_pulled": True,
            "database_written": False,
            "writes_outbox": False,
            "consumes_outbox": False,
            "updates_inbox_or_checkpoint": False,
            "starts_worker": False,
            "touches_n4_n5_n6": False,
        }
        mutations = {
            "payload_trade_date": ("payload", "for_trade_date", "20260702"),
            "payload_subscription": ("payload", "subscription_run_id", "wrong"),
            "payload_source_target": ("payload", "target_run_id", "wrong"),
            "payload_n4_context": ("payload", "n4_context_run_id", "wrong"),
            "payload_hash_policy": ("payload", "source_artifact_hash_policy", "wrong"),
            "payload_database_written": ("payload", "database_written", True),
            "payload_writes_outbox": ("payload", "writes_outbox", True),
            "report_result": ("report", "result", "wrong"),
            "report_actual_until_hhmm": ("report", "actual_until_hhmm", "1043"),
            "report_proof_kind": ("report", "proof_kind", "wrong"),
            "report_artifact_written": ("report", "artifact_written", False),
            "report_database_written": ("report", "database_written", True),
            "report_writes_outbox": ("report", "writes_outbox", True),
            "report_consumes_outbox": ("report", "consumes_outbox", True),
            "report_updates_checkpoint": ("report", "updates_inbox_or_checkpoint", True),
            "report_starts_worker": ("report", "starts_worker", True),
            "report_touches_downstream": ("report", "touches_n4_n5_n6", True),
        }
        for name, (document_kind, field, replacement) in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmpdir:
                artifact = N3HintFrequency8SourceArtifactWriter(output_root=tmpdir).write_n3_hint_frequency8_artifacts(
                    args=_args(for_trade_date="20260701"),
                    report=_report(),
                    dependencies=None,
                    payload=payload,
                    fetch_report=fetch_report,
                    config={},
                )
                payload_path = Path(artifact["payload_path"])
                report_path = Path(artifact["report_path"])
                persisted_payload = json.loads(payload_path.read_text(encoding="utf-8"))
                persisted_report = json.loads(report_path.read_text(encoding="utf-8"))
                target = persisted_payload if document_kind == "payload" else persisted_report
                target[field] = replacement
                payload_bytes = json.dumps(
                    persisted_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    default=str,
                ).encode("utf-8")
                rebound_file_sha = hashlib.sha256(payload_bytes).hexdigest()
                persisted_report["file_sha256"] = rebound_file_sha
                report_bytes = json.dumps(
                    persisted_report,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    default=str,
                ).encode("utf-8")
                payload_path.write_bytes(payload_bytes)
                report_path.write_bytes(report_bytes)
                inspected = inspect_n3_hint_artifact_pair(
                    payload_path=payload_path,
                    report_path=report_path,
                    expected_payload_hash=artifact["payload_hash"],
                    expected_file_sha256=rebound_file_sha,
                    expected_for_trade_date=payload["for_trade_date"],
                    expected_actual_until_hhmm=payload["actual_until_hhmm"],
                    expected_subscription_run_id=payload["subscription_run_id"],
                    expected_hint_proof_kind=payload["hint_proof_kind"],
                    expected_source_target_run_id=payload["target_run_id"],
                    expected_n4_context_run_id=payload["n4_context_run_id"],
                )
                self.assertEqual(inspected["status"], "blocked")

    def test_write_once_writer_blocks_partial_invalid_symlink_and_cleans_second_create_failure(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import N3HintFrequency8SourceArtifactWriter

        payload = _hint_source_payload_for_preflight(
            target_run_id="n3_hint_index_board_1m_source_payload_20260701_until_source_returned_v1"
        )

        def write(writer):
            return writer.write_n3_hint_frequency8_artifacts(
                args=_args(for_trade_date="20260701"),
                report=_report(),
                dependencies=None,
                payload=payload,
                fetch_report={"market_data_pulled": True},
                config={},
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3HintFrequency8SourceArtifactWriter(output_root=tmpdir)
            first = write(writer)
            payload_path = Path(first["payload_path"])
            report_path = Path(first["report_path"])
            original_payload = payload_path.read_bytes()
            report_path.unlink()
            partial = write(writer)
            self.assertEqual(partial["result"], "BLOCKED_N3_HINT_SOURCE_ARTIFACT_WRITER")
            self.assertIn("artifact_pair_partial", partial["reason"])
            self.assertEqual(payload_path.read_bytes(), original_payload)
            self.assertFalse(report_path.exists())

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3HintFrequency8SourceArtifactWriter(output_root=tmpdir)
            first = write(writer)
            payload_path = Path(first["payload_path"])
            report_path = Path(first["report_path"])
            payload_path.write_text("{invalid", encoding="utf-8")
            invalid_bytes = payload_path.read_bytes()
            invalid = write(writer)
            self.assertEqual(invalid["result"], "BLOCKED_N3_HINT_SOURCE_ARTIFACT_WRITER")
            self.assertIn("artifact_json_invalid", invalid["reason"])
            self.assertEqual(payload_path.read_bytes(), invalid_bytes)
            self.assertTrue(report_path.exists())

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "20260701"
            output_dir.mkdir(parents=True)
            payload_path = output_dir / "N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json"
            report_path = output_dir / "N3_hint_index_board_1m_1044_midday_bridge_frequency8_fetch_report.json"
            target = output_dir / "target.json"
            target.write_text("{}", encoding="utf-8")
            payload_path.symlink_to(target)
            report_path.write_text("{}", encoding="utf-8")
            symlink = write(N3HintFrequency8SourceArtifactWriter(output_root=tmpdir))
            self.assertEqual(symlink["result"], "BLOCKED_N3_HINT_SOURCE_ARTIFACT_WRITER")
            self.assertIn("payload_artifact_symlink", symlink["reason"])
            self.assertTrue(payload_path.is_symlink())

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = N3HintFrequency8SourceArtifactWriter(output_root=tmpdir)
            original_open = Path.open

            def fail_report_open(path, mode="r", *args, **kwargs):
                if mode == "xb" and path.name.endswith("_fetch_report.json"):
                    raise OSError("simulated report create failure")
                return original_open(path, mode, *args, **kwargs)

            with patch.object(Path, "open", new=fail_report_open):
                failed = write(writer)
            self.assertEqual(failed["result"], "BLOCKED_N3_HINT_SOURCE_ARTIFACT_WRITER")
            output_dir = Path(tmpdir) / "20260701"
            self.assertEqual(list(output_dir.glob("*.json")), [])

    def test_idempotency_loader_uses_repeatable_read_read_only_transaction(self) -> None:
        from scripts.n3_hint_frequency8_source_provider import load_n3_hint_idempotency_snapshot_from_db

        conn = FakeExecuteConnection()
        with patch("scripts.n3_hint_frequency8_source_provider._connect_db", return_value=conn), patch(
            "scripts.n3_hint_frequency8_source_provider._load_n3_hint_idempotency_snapshot_with_connection",
            return_value={"run_exists": 0},
        ) as loader:
            snapshot = load_n3_hint_idempotency_snapshot_from_db(
                args=_args(),
                dependencies=None,
                config={"database_url": "postgresql://not-used"},
                target_run_id="target-run",
            )

        self.assertEqual(snapshot["run_exists"], 0)
        self.assertEqual(
            [" ".join(sql.split()) for sql, _params in conn.statements],
            ["BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY", "SET LOCAL TIME ZONE 'Asia/Shanghai'", "ROLLBACK"],
        )
        loader.assert_called_once_with(conn=conn, target_run_id="target-run")

    def test_real_runner_normalizers_preserve_noop_specific_execute_boundary(self) -> None:
        from scripts.n3_combined_child_production_hooks import _normalize_success
        from scripts.n3_combined_child_real_runners import (
            N3RealIODependencies,
            _normalize_real_runner_payload,
        )

        args = SimpleNamespace(target_run_id="source-candidate", source_run_id="")
        raw = {
            "result": "NOOP_N3_HINT_TARGET_ALREADY_PASSED",
            "status": "noop",
            "execution_mode": "noop",
            "execute_contract_ready": False,
            "idempotent_target_execute_contract_ready": False,
            "artifact_written": False,
            "database_written": False,
        }
        hook_payload = _normalize_success(
            "n3_hint_source_fetch",
            args=args,
            report={"target_absence_checked": True},
            payload=raw,
        )
        runner_payload = _normalize_real_runner_payload(
            step_id="n3_hint_source_fetch",
            args=args,
            report={"target_absence_checked": True},
            dependencies=N3RealIODependencies(),
            raw_payload=hook_payload,
        )

        self.assertTrue(runner_payload["execute_contract_ready"])
        self.assertFalse(runner_payload["idempotent_target_execute_contract_ready"])
        self.assertEqual(runner_payload["status"], "noop")
        self.assertEqual(runner_payload["result"], "NOOP_N3_HINT_TARGET_ALREADY_PASSED")


if __name__ == "__main__":
    unittest.main()
