import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

from ashare_v3.market import v3_realtime_virtual_metric_writer as writer
from ashare_v3.market.realtime_virtual_metric import (
    _build_formal_amount_chain_fields,
    build_previous_day_cumulative_summary_rows,
)

SOURCE_SNAPSHOT_RUN_ID = (
    "realtime_daily_snapshot_20260612_standard_outbox_until_1500__"
    "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
)
SOURCE_TODAY_MINUTE_RUN_ID = (
    "today_minute_bar_1m_20260612_until_1500__"
    "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
)
SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID = (
    "previous_day_minute_preload_20260611_for_20260612__"
    "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
)
LIVE_CURRENT_1M_SOURCE_RUN_ID = (
    "live_current_1m_source_20260612_until_0931__"
    "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
)
B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID = (
    "realtime_daily_snapshot_20260612_until_0931__"
    "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
)


def minute_bar(code: str, dt: str, open_: float, close: float, amount: float) -> dict:
    return {
        "code": code,
        "datetime": dt,
        "open": open_,
        "high": max(open_, close),
        "low": min(open_, close),
        "close": close,
        "amount": amount,
    }


def previous_same_window_minutes(code: str, *, open_: float, close: float, amount: float) -> list[dict]:
    start = datetime(2026, 6, 11, 9, 31)
    return [
        minute_bar(
            code,
            (start + timedelta(minutes=offset)).strftime("%Y-%m-%d %H:%M"),
            open_,
            close,
            amount + offset,
        )
        for offset in range(30)
    ]


def full_intraday_minutes(code: str, trade_date: str, *, amount: float) -> list[dict]:
    day = datetime.strptime(trade_date, "%Y-%m-%d")
    labels: list[datetime] = []
    labels.extend(day.replace(hour=9, minute=31) + timedelta(minutes=offset) for offset in range(120))
    labels.extend(day.replace(hour=13, minute=1) + timedelta(minutes=offset) for offset in range(120))
    rows: list[dict] = []
    for index, dt in enumerate(labels):
        open_ = 50 + index * 0.01
        close = open_ + 0.2
        if dt.strftime("%H:%M") == "14:47":
            open_ = 55
            close = 56.22
        rows.append(minute_bar(code, dt.strftime("%Y-%m-%d %H:%M"), open_, close, amount))
    return rows


def mini_contract(expected_total: int = 2) -> dict:
    return {
        "result": "CONTRACT_PASS",
        "target_run_id": "action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1",
        "projection_schema_version": "v3.realtime_virtual_metric.writer.contract.v1",
        "source_scope": {
            "for_trade_date": "20260612",
            "source_trade_date": "20260611",
            "source_condition_run_id": "condition_layer_20260611_source_20260611_for_20260612_v1",
            "source_subscription_run_id": "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
            "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID,
            "source_today_minute_run_id": SOURCE_TODAY_MINUTE_RUN_ID,
            "source_previous_day_minute_run_id": SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID,
        },
        "expected_rows": {
            "total": expected_total,
            "metric_ready": expected_total,
            "metric_not_ready": 0,
            "by_signal_type": {"B_BUY": expected_total - 1, "S_SELL": 1},
        },
        "allowed_write_tables": [
            "common_market_data_run",
            "common_market_data_quality_item",
            "stock_action_confirmation_projection_metric",
            "index_action_confirmation_projection_metric",
            "board_action_confirmation_projection_metric",
        ],
        "forbidden_write_tables": [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger_match",
            "common_action_event",
            "user_signal_projection",
        ],
    }


def n3p_contract(expected_total: int = 2) -> dict:
    contract = mini_contract(expected_total=expected_total)
    contract["metric_family"] = "realtime_action_confirmation_metric"
    contract["run_id_contract"] = "n3p.realtime_action_confirmation_metric.v1"
    contract["target_run_id"] = writer.build_n3p_realtime_action_confirmation_metric_run_id(
        for_trade_date="20260612",
        until_hhmm="0931",
        asset_kind="all",
        suffix="market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
    )
    contract["until_minute_label"] = "2026-06-12 09:31"
    contract["db_backed_input_contract"] = {
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID,
        "source_today_minute_run_id": SOURCE_TODAY_MINUTE_RUN_ID,
        "source_previous_day_minute_run_id": SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID,
        "source_condition_run_id": "condition_layer_20260611_source_20260611_for_20260612_v1",
        "source_subscription_run_id": "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
        "n2_period_context_source": "trigger_context_snapshot_or_condition_scope",
        "asset_kinds": ["stock", "index", "board"],
    }
    return contract


def live_n3p_contract(expected_total: int = 2) -> dict:
    contract = n3p_contract(expected_total=expected_total)
    contract["source_scope"]["source_mode"] = "live_current_1m"
    contract["source_scope"]["c1_dependency"] = False
    contract["source_scope"]["source_live_minute_run_id"] = LIVE_CURRENT_1M_SOURCE_RUN_ID
    contract["source_scope"].pop("source_today_minute_run_id", None)
    contract["db_backed_input_contract"]["source_mode"] = "live_current_1m"
    contract["db_backed_input_contract"]["c1_dependency"] = False
    contract["db_backed_input_contract"]["source_live_minute_run_id"] = LIVE_CURRENT_1M_SOURCE_RUN_ID
    contract["db_backed_input_contract"].pop("source_today_minute_run_id", None)
    return contract


def b1_source_returned_n3p_contract(*, until_hhmm: str = "0955", expected_total: int = 2) -> dict:
    contract = n3p_contract(expected_total=expected_total)
    contract["target_run_id"] = writer.build_n3p_realtime_action_confirmation_metric_run_id(
        for_trade_date="20260612",
        until_hhmm=until_hhmm,
        asset_kind="all",
        suffix=(
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1__"
            "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
        ),
    )
    contract["until_minute_label"] = f"2026-06-12 {until_hhmm[:2]}:{until_hhmm[2:]}"
    contract["source_scope"]["source_mode"] = "b1_source_returned_snapshot"
    contract["source_scope"]["c1_dependency"] = False
    contract["source_scope"]["source_snapshot_run_id"] = B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID
    contract["source_scope"].pop("source_today_minute_run_id", None)
    contract["source_scope"]["source_time_policy"] = {"mode": "source_returned_time"}
    contract["source_scope"]["proof_input_time"] = "2026-06-12T09:55:00+08:00"
    contract["source_scope"]["proof_input_time_source"] = "B1_source_snapshot_time"
    contract["source_scope"]["raw_target_minute_label"] = "2026-06-12 09:31"
    contract["db_backed_input_contract"]["source_mode"] = "b1_source_returned_snapshot"
    contract["db_backed_input_contract"]["c1_dependency"] = False
    contract["db_backed_input_contract"]["source_snapshot_run_id"] = B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID
    contract["db_backed_input_contract"].pop("source_today_minute_run_id", None)
    contract["db_backed_input_contract"]["source_time_policy"] = {"mode": "source_returned_time"}
    contract["db_backed_input_contract"]["source_snapshot_time"] = "2026-06-12T09:55:00+08:00"
    contract["db_backed_input_contract"]["observed_at"] = "2026-06-12T09:55:00.482130+08:00"
    contract["db_backed_input_contract"]["raw_target_minute_label"] = "2026-06-12 09:31"
    contract["db_backed_input_contract"]["target_until_hhmm_source"] = "B1_source_snapshot_time"
    return contract


def live_sparse_n3p_contract() -> dict:
    contract = live_n3p_contract(expected_total=1)
    contract["expected_rows"]["by_signal_type"] = {"S_SELL": 1}
    return contract


def clean_target_counts() -> dict:
    return {
        "common_market_data_run": 0,
        "stock_action_confirmation_projection_metric": 0,
        "index_action_confirmation_projection_metric": 0,
        "board_action_confirmation_projection_metric": 0,
        "common_market_data_quality_item": 0,
        "common_event_outbox": 0,
        "common_event_inbox": 0,
        "common_event_consumer_checkpoint": 0,
    }


class RecordingCursor:
    def __init__(self, *, existing_run: bool = False) -> None:
        self.existing_run = existing_run
        self.executed: list[tuple[str, tuple]] = []
        self._last_selects_run = False

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))
        self._last_selects_run = sql.strip().upper().startswith("SELECT 1 FROM COMMON_MARKET_DATA_RUN")

    def fetchone(self):
        if self._last_selects_run and self.existing_run:
            return {"exists": 1}
        return None


class RecordingCumulativeCursor:
    def __init__(self, rows_by_asset: dict[str, list[dict]]) -> None:
        self.rows_by_asset = rows_by_asset
        self.executed: list[tuple[str, tuple]] = []
        self._last_rows: list[dict] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))
        table_to_asset = {
            "stock_previous_day_minute_cumulative": "stock",
            "index_previous_day_minute_cumulative": "index",
            "board_previous_day_minute_cumulative": "board",
        }
        self._last_rows = []
        for table, asset in table_to_asset.items():
            if table in sql:
                self._last_rows = list(self.rows_by_asset.get(asset, []))
                break

    def fetchall(self) -> list[dict]:
        return self._last_rows


def mixed_realtime_source_payload_registration_contract() -> dict:
    contract = b1_source_returned_n3p_contract(expected_total=1)
    contract["source_scope"]["source_model"] = writer.N3P_TRIGGER_PROOF_REALTIME_SOURCE_MODEL
    contract["source_scope"]["source_payload_run_id"] = "n3p_mixed_realtime_source_payload_20260629_until_1455_v1"
    contract["source_scope"]["source_artifact_path"] = (
        "docs/intraday_live_current/20260629/N3P_mixed_realtime_1455_source_fetch_payload.json"
    )
    contract["source_scope"]["source_payload_hash"] = (
        "26e815c00e3dc0a06ad737c0d515c9ec0cf22fc26fc70f4859a056addeef8933"
    )
    contract["source_scope"]["source_origin"] = "local_mootdx_fetch_artifact"
    contract["source_scope"]["writes_outbox"] = False
    contract["db_backed_input_contract"]["source_payload_run_id"] = contract["source_scope"]["source_payload_run_id"]
    contract["db_backed_input_contract"]["source_model"] = writer.N3P_TRIGGER_PROOF_REALTIME_SOURCE_MODEL
    contract["db_backed_input_contract"]["writes_outbox"] = False
    return contract


def source_payload() -> dict:
    previous_buy = previous_same_window_minutes("300776", open_=140, close=141, amount=10)
    previous_sell = previous_same_window_minutes("881002", open_=2600, close=2599, amount=10)
    current = [
        minute_bar("300776", "2026-06-12 09:31", 145, 151, 100),
        minute_bar("881002", "2026-06-12 09:31", 2595, 2538, 100),
    ]
    higher_context = {
        "D": {
            "current_open": 145,
            "previous_open": 140,
            "previous_close": 145,
            "previous_amount": 1000,
            "previous_avg_amount": 1000,
            "current_amount_seed": 100,
            "current_amount_total_seed": 100,
            "current_trade_days_seed": 1,
            "elapsed_units": 1,
            "total_units": 1,
        },
        "W": {
            "current_open": 144,
            "previous_open": 139,
            "previous_close": 143,
            "previous_amount": 5000,
            "previous_avg_amount": 1000,
            "current_amount_seed": 200,
            "current_amount_total_seed": 800,
            "current_trade_days_seed": 4,
            "elapsed_units": 4,
            "total_units": 5,
        },
        "M": {
            "current_open": 143,
            "previous_open": 138,
            "previous_close": 142,
            "previous_amount": 20000,
            "previous_avg_amount": 1000,
            "current_amount_seed": 300,
            "current_amount_total_seed": 5400,
            "current_trade_days_seed": 18,
            "elapsed_units": 18,
            "total_units": 20,
        },
        "Q": {
            "current_open": 142,
            "previous_open": 137,
            "previous_close": 141,
            "previous_amount": 60000,
            "previous_avg_amount": 1000,
            "current_amount_seed": 400,
            "current_amount_total_seed": 22800,
            "current_trade_days_seed": 57,
            "elapsed_units": 57,
            "total_units": 60,
        },
        "Y": {
            "current_open": 141,
            "previous_open": 136,
            "previous_close": 140,
            "previous_amount": 240000,
            "previous_avg_amount": 1000,
            "current_amount_seed": 500,
            "current_amount_total_seed": 56500,
            "current_trade_days_seed": 113,
            "elapsed_units": 113,
            "total_units": 240,
        },
    }
    return {
        "source_records": {
            "300776": [*previous_buy, current[0]],
            "881002": [*previous_sell, current[1]],
        },
        "candidates": [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300776",
                "exchange": "SZ",
                "code": "300776",
                "display_code": "300776",
                "name": "帝尔激光",
                "signal_type": "B_BUY",
                "condition_key": "BUY:Y,D",
                "minute_label": "2026-06-12 09:31",
                "observed_at": "2026-06-12 09:25:30",
                "higher_period_context": higher_context,
            },
            {
                "asset_kind": "board",
                "identity_key": "board:TDX:881002",
                "exchange": "TDX",
                "code": "881002",
                "display_code": "881002",
                "name": "煤炭开采",
                "signal_type": "S_SELL",
                "condition_key": "SELL:Y,D",
                "minute_label": "2026-06-12 09:31",
                "observed_at": "2026-06-12 09:25:30",
                "higher_period_context": higher_context,
            },
        ],
    }


def b1_source_returned_payload(*, candidate_minute_label: str = "2026-06-12 09:55") -> dict:
    payload = source_payload()
    payload["source_records"]["300776"][-1]["datetime"] = "2026-06-12 09:55"
    payload["source_records"]["881002"][-1]["datetime"] = "2026-06-12 09:55"
    for candidate in payload["candidates"]:
        candidate["minute_label"] = candidate_minute_label
        candidate["observed_at"] = "2026-06-12T09:55:00.482130+08:00"
        candidate["source_time_policy"] = "source_returned_time"
        candidate["proof_input_time"] = "2026-06-12T09:55:00+08:00"
        candidate["proof_input_time_source"] = "B1_source_snapshot_time"
        candidate["source_snapshot_time"] = "2026-06-12T09:55:00+08:00"
        candidate["raw_target_minute_label"] = "2026-06-12 09:31"
        candidate["source_snapshot_run_id"] = B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID
    return payload


def b1_snapshot_row_881002(*, proof_input_time: str = "2026-06-12T09:55:00+08:00") -> dict:
    return {
        "snapshot_id": 81002,
        "source_snapshot_row_id": "board:TDX:881002@0955",
        "asset_kind": "board",
        "identity_key": "board:TDX:881002",
        "exchange": "TDX",
        "code": "881002",
        "display_code": "881002",
        "name": "煤炭开采",
        "source_snapshot_run_id": B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID,
        "source_snapshot_time": proof_input_time,
        "observed_at": "2026-06-12T09:55:00.482130+08:00",
        "fetched_at": "2026-06-12T09:55:00.482130+08:00",
        "source_time_policy": "source_returned_time",
        "raw_target_minute_label": "2026-06-12 09:31",
        "open": 2600,
        "high": 2602,
        "low": 2535,
        "close": 2538,
        "amount": 100,
        "raw_json": {"snapshot_fixture": "b1_source_returned"},
    }


def b1_snapshot_row_300776(*, proof_input_time: str = "2026-06-12T09:55:00+08:00") -> dict:
    return {
        "snapshot_id": 300776,
        "source_snapshot_row_id": "stock:SZ:300776@0955",
        "asset_kind": "stock",
        "identity_key": "stock:SZ:300776",
        "exchange": "SZ",
        "code": "300776",
        "display_code": "300776",
        "name": "帝尔激光",
        "source_snapshot_run_id": B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID,
        "source_snapshot_time": proof_input_time,
        "observed_at": proof_input_time,
        "fetched_at": proof_input_time,
        "source_time_policy": "source_returned_time",
        "raw_target_minute_label": "2026-06-12 09:31",
        "open": 145,
        "high": 152,
        "low": 144,
        "close": 151,
        "amount": 1000,
        "raw_json": {"snapshot_fixture": "b1_source_returned"},
    }


def canonical_trade_minute_labels(trade_date: str = "2026-06-11") -> list[str]:
    labels: list[str] = []
    for hour, minute_start, minute_end in ((9, 31, 59), (10, 0, 59), (11, 0, 29), (13, 0, 59), (14, 0, 59), (15, 0, 0)):
        for minute in range(minute_start, minute_end + 1):
            labels.append(f"{trade_date} {hour:02d}:{minute:02d}")
    return labels


def canonical_previous_day_minutes(code: str, *, amount: float = 10.0, trade_date: str = "2026-06-11") -> list[dict]:
    return [minute_bar(code, label, 100, 101, amount) for label in canonical_trade_minute_labels(trade_date)]


def previous_day_minutes_with_midday_bridge_1130(
    code: str, *, amount: float = 10.0, trade_date: str = "2026-06-11"
) -> list[dict]:
    rows: list[dict] = []
    for label in canonical_trade_minute_labels(trade_date):
        raw_label = f"{trade_date} 11:30" if label.endswith(" 13:00") else label
        rows.append(minute_bar(code, raw_label, 100, 101, amount))
    return rows


def previous_day_cumulative_rows(
    code: str,
    *,
    asset_kind: str,
    identity_key: str,
    amount: float = 10.0,
    trade_date: str = "2026-06-11",
) -> list[dict]:
    return build_previous_day_cumulative_summary_rows(
        previous_day_minutes_with_midday_bridge_1130(code, amount=amount, trade_date=trade_date),
        asset_kind=asset_kind,
        identity_key=identity_key,
        source_previous_day_minute_run_id=SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID,
    )


def previous_day_cumulative_db_row(
    *,
    asset_kind: str = "stock",
    identity_key: str = "stock:SZ:300776",
    code: str = "300776",
    canonical_minute_label: str = "2026-06-11 09:55",
    source_run_id: str = SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID,
    cumulative_amount_yuan: float = 250.0,
    full_day_amount_yuan: float = 2400.0,
    source_amount_unit: str = "thousand_yuan",
    unit_conversion_factor: float = 1000.0,
    duplicate_count: int = 1,
) -> dict:
    return {
        "source_previous_day_minute_run_id": source_run_id,
        "for_trade_date": "20260612",
        "source_trade_date": "20260611",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "code": code,
        "exchange": "SZ" if code.startswith("3") else "TDX",
        "canonical_minute_label": canonical_minute_label,
        "canonical_bar_time": canonical_minute_label,
        "raw_bar_time": canonical_minute_label,
        "elapsed_count": 25,
        "full_count": 240,
        "cumulative_amount_yuan": cumulative_amount_yuan,
        "full_day_amount_yuan": full_day_amount_yuan,
        "source_amount_unit": source_amount_unit,
        "canonical_amount_unit": "yuan",
        "unit_conversion_factor": unit_conversion_factor,
        "normalization_policy": "previous_day_midday_bridge_1130_to_1300_v1",
        "raw_json": {"raw_bar_time": canonical_minute_label},
        "trace_json": {"raw_first_label": "2026-06-11 09:31", "raw_last_label": "2026-06-11 15:00"},
        "duplicate_count": duplicate_count,
    }


def canonical_current_day_minutes(
    code: str,
    *,
    through_label: str = "2026-06-12 09:55",
    amount: float = 40.0,
    trade_date: str = "2026-06-12",
) -> list[dict]:
    through_dt = datetime.strptime(through_label, "%Y-%m-%d %H:%M")
    rows: list[dict] = []
    for label in canonical_trade_minute_labels(trade_date):
        if datetime.strptime(label, "%Y-%m-%d %H:%M") > through_dt:
            break
        rows.append(minute_bar(code, label, 2500, 2538, amount))
    return rows


def n4_context_row_board_881002(
    *,
    condition_key: str,
    direction: str,
    pool_id: int,
    scope_id: int,
    include_baseline: bool = True,
) -> dict:
    row = {
        "run_id": "trigger_context_snapshot_20260612_condition_layer_20260611_source_20260611_for_20260612_v1__atomic_rule_v1",
        "trigger_context_id": 88000 + pool_id,
        "source_condition_run_id": "condition_layer_20260611_source_20260611_for_20260612_v1",
        "source_condition_pool_id": pool_id,
        "source_condition_basis_id": 76000 + pool_id,
        "source_minute_target_scope_id": scope_id,
        "asset_kind": "board",
        "identity_key": "board:TDX:881002",
        "board_identity_key": "board:TDX:881002",
        "condition_key": condition_key,
        "direction": direction,
        "signal_type": "B_BUY" if direction == "buy" else "S_SELL",
        "quality_status": "passed",
        "source_trade_date": "20260611",
        "for_trade_date": "20260612",
        "raw_json": {},
    }
    if include_baseline:
        row["raw_json"]["period_trigger_baseline_json"] = period_trigger_baseline_688596()
    return row


def n4_context_row_stock_300776(
    *,
    condition_key: str = "BUY:Y,D",
    direction: str = "buy",
    pool_id: int = 211001,
    scope_id: int = 199001,
) -> dict:
    row = n4_context_row_board_881002(
        condition_key=condition_key,
        direction=direction,
        pool_id=pool_id,
        scope_id=scope_id,
    )
    row.update(
        {
            "trigger_context_id": 77000 + pool_id,
            "asset_kind": "stock",
            "identity_key": "stock:SZ:300776",
            "stock_identity_key": "stock:SZ:300776",
            "board_identity_key": None,
        }
    )
    return row


def b1_source_returned_selection_payload(
    *,
    snapshots: list[dict] | None = None,
    contexts: list[dict] | None = None,
) -> dict:
    base = b1_source_returned_payload()
    return {
        "source_records": {"881002": base["source_records"]["881002"]},
        "b1_snapshot_rows": snapshots if snapshots is not None else [b1_snapshot_row_881002()],
        "n4_context_snapshot_rows": contexts
        if contexts is not None
        else [
            n4_context_row_board_881002(
                condition_key="BUY:Q,M,W,D",
                direction="buy",
                pool_id=23901,
                scope_id=22859,
            )
        ],
    }


def b1_realtime_trigger_proof_payload(*, proof_input_time: str = "2026-06-12T09:55:00+08:00") -> dict:
    return {
        "b1_snapshot_rows": [
            b1_snapshot_row_300776(proof_input_time=proof_input_time),
            b1_snapshot_row_881002(proof_input_time=proof_input_time),
        ],
        "n4_context_snapshot_rows": [
            n4_context_row_stock_300776(),
            n4_context_row_board_881002(
                condition_key="BUY:Q,M,W,D",
                direction="buy",
                pool_id=23901,
                scope_id=22859,
            ),
        ],
        "previous_day_minute_rows": [
            *canonical_previous_day_minutes("300776", amount=10),
            *canonical_previous_day_minutes("881002", amount=10),
        ],
        "stock_quote_rows": [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300776",
                "exchange": "SZ",
                "code": "300776",
                "price": 151,
                "open": 145,
                "high": 152,
                "low": 144,
                "amount": 1000,
                "servertime": "09:55:10.000",
                "source_marker": "mootdx_quotes",
            }
        ],
        "index_board_1m_rows": [
            {
                **row,
                "asset_kind": "board",
                "identity_key": "board:TDX:881002",
                "source_adapter_method": "index",
                "source_frequency": 8,
                "source_marker": "mootdx_index_frequency_8",
            }
            for row in canonical_current_day_minutes("881002", amount=40)
        ],
    }


def period_trigger_baseline_688596() -> dict:
    return {
        "baseline_source": "condition_layer",
        "baseline_version": "v3.period_trigger_baseline.v1",
        "amount_metric_rule": "attachment_dwmqy_avg_chain",
        "periods": {
            "D": {
                "current_open_seed": "49.33",
                "previous_open": "47.00",
                "previous_close": "49.33",
                "previous_entity_high": "49.33",
                "previous_entity_low": "46.85",
                "current_trade_days_seed": 1,
                "current_amount_seed": "1322015.037",
                "current_amount_total_seed": "1322015.037",
                "previous_amount": "1322015.037",
                "previous_avg_amount": "1322015.037",
                "previous_amount_baseline": "1322015.037",
                "period_baseline_ready": True,
                "previous_transition": "flat",
                "freshness_status": "fresh",
                "baseline_source_trade_date": "20260625",
            },
            "W": {
                "current_open_seed": "46.10",
                "previous_open": "45.00",
                "previous_close": "46.10",
                "previous_entity_high": "46.10",
                "previous_entity_low": "45.00",
                "current_trade_days_seed": 4,
                "current_amount_seed": "1032506.486",
                "current_amount_total_seed": "4130025.944",
                "previous_amount": "1054494.07275",
                "previous_avg_amount": "1054494.07275",
                "previous_amount_baseline": "1054494.07275",
                "period_baseline_ready": True,
                "previous_transition": "low_volume_up",
                "freshness_status": "fresh",
                "baseline_source_trade_date": "20260625",
            },
            "M": {
                "current_open_seed": "40.56",
                "previous_open": "33.00",
                "previous_close": "40.56",
                "previous_entity_high": "40.56",
                "previous_entity_low": "32.90",
                "current_trade_days_seed": 18,
                "current_amount_seed": "1019904.230666666667",
                "current_amount_total_seed": "18358276.152",
                "previous_amount": "1062320.559277777778",
                "previous_avg_amount": "1062320.559277777778",
                "previous_amount_baseline": "1062320.559277777778",
                "period_baseline_ready": True,
                "previous_transition": "low_volume_up",
                "freshness_status": "fresh",
                "baseline_source_trade_date": "20260625",
            },
            "Q": {
                "current_open_seed": "31.94",
                "previous_open": "27.80",
                "previous_close": "31.94",
                "previous_entity_high": "31.94",
                "previous_entity_low": "27.79",
                "current_trade_days_seed": 57,
                "current_amount_seed": "729619.607350877193",
                "current_amount_total_seed": "41588317.619",
                "previous_amount": "284073.571589285714",
                "previous_avg_amount": "284073.571589285714",
                "previous_amount_baseline": "284073.571589285714",
                "period_baseline_ready": True,
                "previous_transition": "volume_up",
                "freshness_status": "fresh",
                "baseline_source_trade_date": "20260625",
            },
            "Y": {
                "current_open_seed": "34.93",
                "previous_open": "31.60",
                "previous_close": "34.93",
                "previous_entity_high": "34.93",
                "previous_entity_low": "31.56",
                "current_trade_days_seed": 113,
                "current_amount_seed": "508818.03210619469",
                "current_amount_total_seed": "57496437.628",
                "previous_amount": "275110.741469135802",
                "previous_avg_amount": "275110.741469135802",
                "previous_amount_baseline": "275110.741469135802",
                "period_baseline_ready": True,
                "previous_transition": "volume_up",
                "freshness_status": "fresh",
                "baseline_source_trade_date": "20260625",
            },
        },
    }


def n4_context_row_688596() -> dict:
    return {
        "run_id": "trigger_context_snapshot_20260626_condition_layer_20260625_source_20260625_for_20260626_v1__atomic_rule_v1",
        "trigger_context_id": 121310,
        "source_condition_run_id": "condition_layer_20260625_source_20260625_for_20260626_v1",
        "source_condition_pool_id": 211486,
        "source_condition_basis_id": 266802,
        "source_minute_target_scope_id": 199999,
        "asset_kind": "stock",
        "identity_key": "stock:SH:688596",
        "stock_identity_key": "stock:SH:688596",
        "condition_key": "BUY:M,W,D",
        "direction": "buy",
        "condition_periods": ["M", "W", "D"],
        "quality_status": "passed",
        "source_trade_date": "20260625",
        "for_trade_date": "20260626",
        "raw_json": {
            "period_trigger_baseline_json": period_trigger_baseline_688596(),
        },
    }


def live_688596_payload(*, include_n4_context: bool = True) -> dict:
    previous = full_intraday_minutes("688596", "2026-06-25", amount=100)
    current = full_intraday_minutes("688596", "2026-06-26", amount=2_000_000_000)
    payload = {
        "source_records": {
            "688596": [*previous, *current],
        },
        "candidates": [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:688596",
                "exchange": "SH",
                "code": "688596",
                "display_code": "688596",
                "name": "688596",
                "signal_type": "B_BUY",
                "condition_key": "BUY:M,W,D",
                "minute_label": "2026-06-26 14:47",
                "observed_at": "2026-06-26 14:47:30",
            }
        ],
    }
    if include_n4_context:
        payload["n4_context_snapshot_rows"] = [n4_context_row_688596()]
    return payload


def sparse_no_trade_exception(index: int = 0) -> dict:
    suffix = "" if index == 0 else f":{index:02d}"
    code = "688260" if index == 0 else f"6882{index:02d}"
    return {
        "asset_kind": "stock",
        "identity_key": f"stock:SH:688260{suffix}",
        "exchange": "SH",
        "code": code,
        "display_code": code,
        "name": "sparse-no-trade",
        "reason": "adapter_sparse_no_trade",
        "source_adapter": "mootdx",
        "subscription_id": 169056 + index,
        "latest_row_minute": "2026-06-26 09:31",
        "expected_target_minute": "2026-06-26 13:55",
        "latest_row": {
            "bar_time": "2026-06-26 09:31:00+08:00",
            "open": 144,
            "high": 144,
            "low": 144,
            "close": 144,
            "volume": 0,
            "amount": 0,
        },
        "writes_fake_bar": False,
        "uses_previous_minute_as_target": False,
        "metric_ready": False,
    }


def live_sparse_no_trade_payload(exception_count: int = 1) -> dict:
    payload = source_payload()
    payload["source_records"] = {"881002": payload["source_records"]["881002"]}
    payload["candidates"] = [payload["candidates"][1]]
    payload["live_current_sparse_no_trade_exceptions"] = [
        sparse_no_trade_exception(index) for index in range(exception_count)
    ]
    return payload


class V3RealtimeVirtualMetricWriterRunnerTest(unittest.TestCase):
    def test_materialized_source_payload_overlay_is_contract_driven(self) -> None:
        contract = {
            "materialized_source_payload_overlay": {
                "candidates": [{"identity_key": "stock:SH:600000"}],
                "n4_context_snapshot_rows": [{"identity_key": "stock:SH:600000"}],
                "previous_day_cumulative_rows": [{"identity_key": "stock:SH:600000", "canonical_minute_label": "09:46"}],
                "previous_day_minute_rows": [],
                "require_previous_day_cumulative_rows": True,
            }
        }
        source_payload = {"stock_quote_rows": [{"identity_key": "stock:SH:600000"}]}

        materialized = writer.materialize_source_payload_from_contract(contract, source_payload)

        self.assertEqual(materialized["stock_quote_rows"], source_payload["stock_quote_rows"])
        self.assertEqual(materialized["candidates"], contract["materialized_source_payload_overlay"]["candidates"])
        self.assertEqual(
            materialized["previous_day_cumulative_rows"],
            contract["materialized_source_payload_overlay"]["previous_day_cumulative_rows"],
        )
        self.assertTrue(materialized["require_previous_day_cumulative_rows"])

    def test_materialized_source_payload_overlay_conflict_fails_closed(self) -> None:
        contract = {
            "materialized_source_payload_overlay": {
                "candidates": [{"identity_key": "stock:SH:600000"}],
            }
        }
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "materialized_source_payload_overlay_conflict:candidates"):
            writer.materialize_source_payload_from_contract(
                contract,
                {"candidates": [{"identity_key": "stock:SZ:000001"}]},
            )

    def test_mixed_realtime_source_payload_registration_inserts_source_run_only(self) -> None:
        cur = RecordingCursor()
        contract = mixed_realtime_source_payload_registration_contract()
        payload = {
            "stock_quote_rows": [{"code": "300776"}],
            "index_board_1m_rows": [{"code": "881002"}, {"code": "000001"}],
            "previous_day_cumulative_rows": [{"identity_key": "stock:SZ:300776"}],
        }

        inserted = writer.ensure_mixed_realtime_source_payload_run(
            cur=cur,
            contract=contract,
            source_payload=payload,
            started_at="2026-06-29T14:55:10+08:00",
        )

        self.assertEqual(inserted, 1)
        executed_sql = "\n".join(sql for sql, _params in cur.executed)
        self.assertIn("INSERT INTO common_market_data_run", executed_sql)
        self.assertIn("INSERT INTO common_market_data_quality_item", executed_sql)
        self.assertNotIn("common_event_outbox", executed_sql)
        self.assertNotIn("action_confirmation_projection_metric", executed_sql)
        run_insert = next(params for sql, params in cur.executed if "INSERT INTO common_market_data_run" in sql)
        self.assertEqual(run_insert[0], "n3p_mixed_realtime_source_payload_20260629_until_1455_v1")
        self.assertEqual(run_insert[9], "2026-06-29T14:55:10+08:00")
        self.assertEqual(run_insert[10], "2026-06-29T14:55:10+08:00")
        raw_json = run_insert[-1].obj
        self.assertEqual(raw_json["stage"], "N3P_mixed_realtime_source_payload_registration")
        self.assertEqual(raw_json["source_model"], writer.N3P_TRIGGER_PROOF_REALTIME_SOURCE_MODEL)
        self.assertFalse(raw_json["writes_outbox"])
        self.assertTrue(raw_json["not_n5_final_proof"])
        self.assertEqual(raw_json["source_payload_counts"]["stock_quote_rows"], 1)
        self.assertEqual(raw_json["source_payload_counts"]["index_board_1m_rows"], 2)

    def test_mixed_realtime_source_payload_registration_noops_when_run_exists(self) -> None:
        cur = RecordingCursor(existing_run=True)

        inserted = writer.ensure_mixed_realtime_source_payload_run(
            cur=cur,
            contract=mixed_realtime_source_payload_registration_contract(),
            source_payload={"stock_quote_rows": []},
            started_at="2026-06-29T14:55:10+08:00",
        )

        self.assertEqual(inserted, 0)
        executed_sql = "\n".join(sql for sql, _params in cur.executed)
        self.assertIn("SELECT 1 FROM common_market_data_run", executed_sql)
        self.assertNotIn("INSERT INTO common_market_data_run", executed_sql)

    def test_mixed_realtime_source_payload_registration_blocks_outbox_contract(self) -> None:
        cur = RecordingCursor()
        contract = mixed_realtime_source_payload_registration_contract()
        contract["source_scope"]["writes_outbox"] = True

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "source_payload_writes_outbox_forbidden"):
            writer.ensure_mixed_realtime_source_payload_run(
                cur=cur,
                contract=contract,
                source_payload={},
                started_at="2026-06-29T14:55:10+08:00",
            )

        self.assertFalse(cur.executed)

    def test_n3p_run_id_builder_and_parser_fail_closed(self) -> None:
        run_id = writer.build_n3p_realtime_action_confirmation_metric_run_id(
            for_trade_date="20260612",
            until_hhmm="0931",
            asset_kind="stock",
            suffix="market_data_subscription_20260612_v1",
        )

        parsed = writer.parse_n3p_realtime_action_confirmation_metric_run_id(run_id)

        self.assertEqual(parsed["for_trade_date"], "20260612")
        self.assertEqual(parsed["until_hhmm"], "0931")
        self.assertEqual(parsed["asset_kind"], "stock")
        self.assertEqual(parsed["suffix"], "market_data_subscription_20260612_v1")
        self.assertEqual(parsed["metric_family"], "realtime_action_confirmation_metric")

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "invalid_n3p_run_id"):
            writer.parse_n3p_realtime_action_confirmation_metric_run_id(
                "today_minute_bar_1m_20260612_until_0931__market_data_subscription"
            )
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "invalid_n3p_asset_kind"):
            writer.build_n3p_realtime_action_confirmation_metric_run_id(
                for_trade_date="20260612",
                until_hhmm="0931",
                asset_kind="bad",
            )

    def test_n3p_asset_unit_fix_run_id_contract_is_exact_and_fail_closed(self) -> None:
        suffix = (
            "live_current_1m_amount_chain_v2_asset_unit_fix_v1__"
            "market_data_subscription_20260626_condition_layer_20260625_source_20260625_for_20260626_v1"
        )
        run_id = writer.build_n3p_realtime_action_confirmation_metric_run_id(
            for_trade_date="20260626",
            until_hhmm="1447",
            asset_kind="all",
            suffix=suffix,
        )

        parsed = writer.parse_n3p_realtime_action_confirmation_metric_run_id(run_id)

        self.assertEqual(
            run_id,
            "realtime_action_confirmation_metric_20260626_until_1447__asset_all__"
            "live_current_1m_amount_chain_v2_asset_unit_fix_v1__"
            "market_data_subscription_20260626_condition_layer_20260625_source_20260625_for_20260626_v1",
        )
        self.assertEqual(parsed["source_variant"], "live_current_1m_amount_chain_v2_asset_unit_fix_v1")
        self.assertEqual(parsed["suffix"], suffix)

        legacy = writer.parse_n3p_realtime_action_confirmation_metric_run_id(
            writer.build_n3p_realtime_action_confirmation_metric_run_id(
                for_trade_date="20260612",
                until_hhmm="0931",
                asset_kind="stock",
                suffix="market_data_subscription_20260612_v1",
            )
        )
        amount_chain_v2 = writer.parse_n3p_realtime_action_confirmation_metric_run_id(
            writer.build_n3p_realtime_action_confirmation_metric_run_id(
                for_trade_date="20260626",
                until_hhmm="1447",
                asset_kind="all",
                suffix=(
                    "live_current_1m_amount_chain_v2__"
                    "market_data_subscription_20260626_condition_layer_20260625_source_20260625_for_20260626_v1"
                ),
            )
        )
        self.assertEqual(legacy["source_variant"], "default")
        self.assertEqual(amount_chain_v2["source_variant"], "live_current_1m_amount_chain_v2")

        unsafe_suffixes = [
            "live_current_1m_amount_chain_v2_asset_unit_fix_v2__market_data_subscription_20260626_v1",
            "live_current_1m_amount_chain_v3__market_data_subscription_20260626_v1",
            "live_current_1m_amount_chain_v2_asset_unit_fix_v1",
            "live_current_1m_amount_chain_v2_asset_unit_fix_v1__not_market_data_subscription_20260626_v1",
        ]
        for unsafe_suffix in unsafe_suffixes:
            with self.subTest(unsafe_suffix=unsafe_suffix):
                with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "invalid_n3p_run_id"):
                    writer.parse_n3p_realtime_action_confirmation_metric_run_id(
                        writer.build_n3p_realtime_action_confirmation_metric_run_id(
                            for_trade_date="20260626",
                            until_hhmm="1447",
                            asset_kind="all",
                            suffix=unsafe_suffix,
                        )
                    )
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "invalid_n3p_run_id"):
            writer.parse_n3p_realtime_action_confirmation_metric_run_id(
                "realtime_action_confirmation_metric_20260626_until_2460__asset_all__"
                "live_current_1m_amount_chain_v2_asset_unit_fix_v1__market_data_subscription_20260626_v1"
            )

    def test_n3p_b1_source_returned_run_id_contract_is_exact_and_fail_closed(self) -> None:
        suffix = (
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1__"
            "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
        )
        run_id = writer.build_n3p_realtime_action_confirmation_metric_run_id(
            for_trade_date="20260629",
            until_hhmm="0955",
            asset_kind="all",
            suffix=suffix,
        )

        parsed = writer.parse_n3p_realtime_action_confirmation_metric_run_id(run_id)

        self.assertEqual(
            run_id,
            "realtime_action_confirmation_metric_20260629_until_0955__asset_all__"
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1__"
            "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1",
        )
        self.assertEqual(parsed["source_variant"], "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1")
        self.assertEqual(
            parsed["source_subscription_run_id"],
            "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1",
        )
        self.assertEqual(parsed["until_hhmm"], "0955")

        unsafe_suffixes = [
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v2__market_data_subscription_20260629_v1",
            "b1_source_returned_snapshot_amount_chain_v3_asset_unit_fix_v1__market_data_subscription_20260629_v1",
            "live_current_1m_amount_chain_v3__market_data_subscription_20260629_v1",
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1",
        ]
        for unsafe_suffix in unsafe_suffixes:
            with self.subTest(unsafe_suffix=unsafe_suffix):
                with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "invalid_n3p_run_id"):
                    writer.build_n3p_realtime_action_confirmation_metric_run_id(
                        for_trade_date="20260629",
                        until_hhmm="0955",
                        asset_kind="all",
                        suffix=unsafe_suffix,
                    )
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "invalid_n3p_run_id"):
            writer.parse_n3p_realtime_action_confirmation_metric_run_id(
                "realtime_action_confirmation_metric_20260629_until_2460__asset_all__"
                "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1__market_data_subscription_20260629_v1"
            )

    def test_n3p_current_period_avg_supersession_run_id_contract_is_exact_and_fail_closed(self) -> None:
        source_variant = "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
        suffix = (
            f"{source_variant}__"
            "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
        )
        run_id = writer.build_n3p_realtime_action_confirmation_metric_run_id(
            for_trade_date="20260629",
            until_hhmm="1455",
            asset_kind="all",
            suffix=suffix,
        )

        parsed = writer.parse_n3p_realtime_action_confirmation_metric_run_id(run_id)

        self.assertEqual(
            run_id,
            "realtime_action_confirmation_metric_20260629_until_1455__asset_all__"
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
            "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1",
        )
        self.assertEqual(parsed["source_variant"], source_variant)
        self.assertEqual(
            parsed["source_subscription_run_id"],
            "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1",
        )

        legacy = writer.parse_n3p_realtime_action_confirmation_metric_run_id(
            writer.build_n3p_realtime_action_confirmation_metric_run_id(
                for_trade_date="20260629",
                until_hhmm="1455",
                asset_kind="all",
                suffix=(
                    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1__"
                    "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
                ),
            )
        )
        self.assertEqual(
            legacy["source_variant"],
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1",
        )

        unsafe_suffixes = [
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v2__market_data_subscription_20260629_v1",
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v2_current_period_avg_v1__market_data_subscription_20260629_v1",
            "b1_source_returned_snapshot_amount_chain_v3_asset_unit_fix_v1_current_period_avg_v1__market_data_subscription_20260629_v1",
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1",
        ]
        for unsafe_suffix in unsafe_suffixes:
            with self.subTest(unsafe_suffix=unsafe_suffix):
                with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "invalid_n3p_run_id"):
                    writer.build_n3p_realtime_action_confirmation_metric_run_id(
                        for_trade_date="20260629",
                        until_hhmm="1455",
                        asset_kind="all",
                        suffix=unsafe_suffix,
                    )

    def test_n3p_trigger_proof_rollback_sql_is_scoped_and_guarded(self) -> None:
        target_run_id = writer.build_n3p_realtime_action_confirmation_metric_run_id(
            for_trade_date="20260701",
            until_hhmm="1429",
            asset_kind="all",
            suffix=(
                "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                "market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1"
            ),
        )

        sql = writer.build_n3p_trigger_proof_rollback_sql(
            target_run_id=target_run_id,
            source_payload_run_id="n3p_mixed_realtime_source_payload_20260701_until_1429_v1",
        )

        self.assertIn(target_run_id, sql)
        self.assertIn("delivering", sql)
        self.assertIn("delivered", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("common_trigger_run", sql)
        self.assertIn("common_action_run", sql)
        self.assertIn("user", sql)
        self.assertIn("sim", sql)
        self.assertIn("DELETE FROM stock_action_confirmation_projection_metric", sql)
        self.assertIn("DELETE FROM index_action_confirmation_projection_metric", sql)
        self.assertIn("DELETE FROM board_action_confirmation_projection_metric", sql)
        self.assertIn("DELETE FROM common_market_data_quality_item", sql)
        self.assertIn("DELETE FROM common_market_data_run", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertNotIn("DELETE FROM common_event_inbox", sql)
        self.assertNotIn("DELETE FROM common_trigger_run", sql)
        self.assertNotIn("DELETE FROM common_action_run", sql)
        self.assertNotIn("DELETE FROM n3p_mixed_realtime_source_payload", sql)

    def test_target_absence_clean_passes_and_dirty_blocks(self) -> None:
        clean = writer.build_target_absence_report(
            target_run_id=n3p_contract()["target_run_id"],
            counts=clean_target_counts(),
        )
        self.assertEqual(clean["status"], "passed")

        dirty_counts = clean_target_counts()
        dirty_counts["stock_action_confirmation_projection_metric"] = 1
        dirty = writer.build_target_absence_report(
            target_run_id=n3p_contract()["target_run_id"],
            counts=dirty_counts,
        )

        self.assertEqual(dirty["status"], "blocked")
        self.assertEqual(dirty["blocked_reason"], "BLOCKED_TARGET_NOT_EMPTY")
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "BLOCKED_TARGET_NOT_EMPTY"):
            writer.assert_target_absent(dirty)

    def test_db_backed_input_contract_contains_required_b1_c1_p1_n2_refs(self) -> None:
        report = writer.build_db_backed_input_contract_report(n3p_contract())

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["for_trade_date"], "20260612")
        self.assertEqual(report["until_hhmm"], "0931")
        self.assertEqual(report["input_refs"]["source_snapshot_run_id"], SOURCE_SNAPSHOT_RUN_ID)
        self.assertEqual(report["input_refs"]["source_today_minute_run_id"], SOURCE_TODAY_MINUTE_RUN_ID)
        self.assertEqual(report["input_refs"]["source_previous_day_minute_run_id"], SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID)
        self.assertEqual(
            report["input_refs"]["source_condition_run_id"],
            "condition_layer_20260611_source_20260611_for_20260612_v1",
        )
        self.assertEqual(report["asset_kinds"], ["stock", "index", "board"])

        broken = n3p_contract()
        broken["db_backed_input_contract"].pop("source_today_minute_run_id")
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "BLOCKED_NEED_INPUT_RESOLVER"):
            writer.build_db_backed_input_contract_report(broken)

    def test_live_current_1m_input_contract_does_not_require_c1_run(self) -> None:
        report = writer.build_db_backed_input_contract_report(live_n3p_contract())

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["source_mode"], "live_current_1m")
        self.assertFalse(report["c1_dependency"])
        self.assertEqual(report["input_refs"]["source_live_minute_run_id"], LIVE_CURRENT_1M_SOURCE_RUN_ID)
        self.assertEqual(report["input_refs"]["source_today_minute_run_id"], LIVE_CURRENT_1M_SOURCE_RUN_ID)
        self.assertEqual(report["source_today_minute_run_id_compat"], LIVE_CURRENT_1M_SOURCE_RUN_ID)
        self.assertTrue(report["no_c1_table_rows_read"])
        self.assertTrue(report["no_c1_table_rows_written"])

    def test_b1_source_returned_input_contract_does_not_require_today_minute_run(self) -> None:
        report = writer.build_db_backed_input_contract_report(b1_source_returned_n3p_contract())

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["source_mode"], "b1_source_returned_snapshot")
        self.assertFalse(report["c1_dependency"])
        self.assertEqual(report["until_hhmm"], "0955")
        self.assertEqual(report["input_refs"]["source_snapshot_run_id"], B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID)
        self.assertEqual(report["input_refs"]["source_today_minute_run_id"], B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID)
        self.assertEqual(report["source_today_minute_run_id_compat"], B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID)
        self.assertEqual(report["source_today_minute_run_id_compat_policy"], "b1_source_returned_snapshot_alias")
        self.assertEqual(report["source_time_policy"], "source_returned_time")
        self.assertEqual(report["proof_input_time"], "2026-06-12T09:55:00+08:00")
        self.assertEqual(report["proof_input_time_source"], "B1_source_snapshot_time")
        self.assertEqual(report["raw_target_minute_label"], "2026-06-12 09:31")
        self.assertTrue(report["no_c1_table_rows_read"])
        self.assertTrue(report["no_c1_table_rows_written"])

    def test_b1_source_returned_input_contract_blocks_until_hhmm_mismatch(self) -> None:
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "b1_source_returned_until_hhmm_mismatch"):
            writer.build_db_backed_input_contract_report(b1_source_returned_n3p_contract(until_hhmm="0931"))

    def test_b1_source_returned_input_contract_blocks_conflicting_today_alias(self) -> None:
        contract = b1_source_returned_n3p_contract()
        contract["db_backed_input_contract"]["source_today_minute_run_id"] = SOURCE_TODAY_MINUTE_RUN_ID

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "b1_source_returned_today_alias_mismatch"):
            writer.build_db_backed_input_contract_report(contract)

    def test_n3p_plan_output_contains_contract_fields_and_side_effect_guard(self) -> None:
        report = writer.run_virtual_metric_writer(
            contract=n3p_contract(),
            preflight={"result": "PREFLIGHT_PASS"},
            source_payload=source_payload(),
            execute=False,
            user_confirmed=False,
            target_absence_counts=clean_target_counts(),
        )

        self.assertEqual(report["run_id"], n3p_contract()["target_run_id"])
        self.assertEqual(report["for_trade_date"], "20260612")
        self.assertEqual(report["until_minute"], "0931")
        self.assertEqual(report["target_absence"]["status"], "passed")
        self.assertEqual(report["metric_counts_by_asset"]["stock"], 1)
        self.assertEqual(report["metric_counts_by_asset"]["board"], 1)
        self.assertEqual(report["closed_minute_summary"]["closed_1m_false"], 2)
        self.assertFalse(report["side_effect_guard"]["outbox_written"])
        self.assertFalse(report["side_effect_guard"]["outbox_inbox_checkpoint_consumed_or_updated"])
        self.assertFalse(report["side_effect_guard"]["n4_n5_executed"])
        self.assertEqual(report["final_status"], "passed")

    def test_n3p_metric_rows_preserve_closed_minute_proof_for_closed_minute(self) -> None:
        payload = source_payload()
        for candidate in payload["candidates"]:
            candidate["observed_at"] = "2026-06-12 09:32:01"

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(n3p_contract(), payload)
        stock_row = rows_by_asset["stock"][0]

        self.assertEqual(stock_row["metric_time_label"], "2026-06-12 09:31")
        self.assertEqual(stock_row["metric_minute_label"], "09:31")
        self.assertTrue(stock_row["is_closed_1m"])
        self.assertTrue(stock_row["metric_ready"])
        self.assertEqual(stock_row["source_today_minute_run_id"], SOURCE_TODAY_MINUTE_RUN_ID)
        self.assertEqual(
            stock_row["raw_json"]["closed_minute_proof"]["selected_metric_time"],
            "2026-06-12T09:31:00+08:00",
        )
        self.assertTrue(stock_row["trace_json"]["closed_minute_proof"]["is_closed_1m"])

        report = writer.run_virtual_metric_writer(
            contract=n3p_contract(),
            preflight={"result": "PREFLIGHT_PASS"},
            source_payload=payload,
            execute=False,
            user_confirmed=False,
            target_absence_counts=clean_target_counts(),
        )
        self.assertEqual(report["closed_minute_summary"]["closed_1m_true"], 2)
        self.assertEqual(report["closed_minute_summary"]["closed_1m_false"], 0)

    def test_live_current_1m_metric_rows_use_live_source_run_for_c1_fk_compat(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(live_n3p_contract(), source_payload())
        stock_row = rows_by_asset["stock"][0]

        self.assertFalse(stock_row["is_closed_1m"])
        self.assertTrue(stock_row["metric_ready"])
        self.assertEqual(stock_row["source_today_minute_run_id"], LIVE_CURRENT_1M_SOURCE_RUN_ID)
        self.assertEqual(stock_row["source_fact_ids"]["source_live_minute_run_id"], LIVE_CURRENT_1M_SOURCE_RUN_ID)
        self.assertEqual(stock_row["source_fact_ids"]["source_mode"], "live_current_1m")
        self.assertFalse(stock_row["source_fact_ids"]["c1_dependency"])
        self.assertTrue(stock_row["source_fact_ids"]["no_c1_table_rows_read"])
        self.assertTrue(stock_row["source_fact_ids"]["no_c1_table_rows_written"])
        self.assertEqual(stock_row["raw_json"]["closed_minute_proof"]["source_mode"], "live_current_1m")
        self.assertTrue(stock_row["raw_json"]["closed_minute_proof"]["no_c1_table_rows_read"])
        self.assertTrue(stock_row["raw_json"]["closed_minute_proof"]["no_c1_table_rows_written"])
        self.assertEqual(stock_row["trace_json"]["source_live_minute_kind"], "live_current_1m")
        self.assertFalse(stock_row["trace_json"]["c1_dependency"])
        self.assertTrue(stock_row["trace_json"]["no_c1_table_rows_read"])
        self.assertTrue(stock_row["trace_json"]["no_c1_table_rows_written"])

        report = writer.run_virtual_metric_writer(
            contract=live_n3p_contract(),
            preflight={"result": "PREFLIGHT_PASS"},
            source_payload=source_payload(),
            execute=False,
            user_confirmed=False,
            target_absence_counts=clean_target_counts(),
        )
        self.assertEqual(report["db_backed_input_contract"]["source_mode"], "live_current_1m")
        self.assertFalse(report["db_backed_input_contract"]["c1_dependency"])
        self.assertEqual(report["source_mode"], "live_current_1m")
        self.assertFalse(report["c1_dependency"])
        self.assertTrue(report["no_c1_table_rows_read"])
        self.assertTrue(report["no_c1_table_rows_written"])
        self.assertEqual(report["rows_by_asset"]["stock"], 1)
        self.assertEqual(report["rows_by_asset"]["board"], 1)
        self.assertEqual(report["metric_ready_count"], 2)
        self.assertEqual(report["closed_minute_summary"]["closed_1m_false"], 2)

    def test_b1_source_returned_rows_keep_snapshot_time_trace_and_alias_today_minute_fk(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            b1_source_returned_n3p_contract(),
            b1_source_returned_payload(),
        )
        stock_row = rows_by_asset["stock"][0]

        self.assertEqual(stock_row["metric_minute_label"], "09:55")
        self.assertEqual(stock_row["source_snapshot_run_id"], B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID)
        self.assertEqual(stock_row["source_today_minute_run_id"], B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID)
        self.assertEqual(stock_row["source_fact_ids"]["source_mode"], "b1_source_returned_snapshot")
        self.assertEqual(
            stock_row["source_fact_ids"]["source_today_minute_run_id_compat"],
            B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID,
        )
        self.assertEqual(
            stock_row["source_fact_ids"]["source_today_minute_run_id_compat_policy"],
            "b1_source_returned_snapshot_alias",
        )
        self.assertEqual(stock_row["source_fact_ids"]["proof_input_time"], "2026-06-12T09:55:00+08:00")
        self.assertEqual(stock_row["raw_json"]["source_time_policy"], "source_returned_time")
        self.assertEqual(stock_row["raw_json"]["proof_input_time_source"], "B1_source_snapshot_time")
        self.assertEqual(
            stock_row["raw_json"]["source_returned_time_lineage"]["raw_target_minute_label"],
            "2026-06-12 09:31",
        )
        self.assertEqual(
            stock_row["raw_json"]["source_returned_time_lineage"]["source_snapshot_time"],
            "2026-06-12T09:55:00+08:00",
        )
        self.assertTrue(stock_row["raw_json"]["source_returned_time_lineage"]["forbid_source_time_relabel"])
        self.assertFalse(stock_row["source_fact_ids"]["c1_dependency"])
        self.assertTrue(stock_row["source_fact_ids"]["no_c1_table_rows_read"])
        self.assertTrue(stock_row["source_fact_ids"]["no_c1_table_rows_written"])

    def test_b1_source_returned_snapshot_missing_previous_5m_is_trigger_proof_ready_only(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            b1_source_returned_n3p_contract(),
            b1_source_returned_payload(),
        )
        stock_row = rows_by_asset["stock"][0]

        self.assertTrue(stock_row["metric_ready"])
        self.assertEqual(stock_row["metric_quality_status"], "passed")
        self.assertTrue(stock_row["raw_json"]["trigger_proof_ready"])
        self.assertEqual(stock_row["raw_json"]["trigger_proof_ready_reason"], "n4_ordinary_trigger_proof_ready")
        self.assertFalse(stock_row["raw_json"]["action_confirmation_ready"])
        self.assertEqual(stock_row["raw_json"]["action_confirmation_ready_reason"], "not_n5_final_proof")
        self.assertFalse(stock_row["raw_json"]["previous_5m_required_for_trigger_proof"])
        self.assertEqual(stock_row["raw_json"]["previous_5m_status"], "not_required_for_trigger_proof")
        self.assertEqual(stock_row["raw_json"]["segment_30m_status"], "not_required_for_trigger_proof")
        self.assertEqual(stock_row["raw_json"]["segment_120m_status"], "not_required_for_trigger_proof")
        self.assertEqual(stock_row["previous_5m_period_source"], "not_available")
        self.assertEqual(stock_row["previous_30m_period_source"], "not_available")
        self.assertEqual(stock_row["previous_120m_period_source"], "not_available")
        compat = stock_row["raw_json"]["trigger_proof_segment_source_db_compat"]
        self.assertEqual(compat["db_facing_value"], "not_available")
        self.assertEqual(compat["reason"], "trigger_proof_does_not_use_action_confirmation_segments")
        self.assertEqual(compat["previous_30m_period_source"], "previous_trade_date_last_period")
        self.assertIn("previous_5m_not_found", stock_row["raw_json"]["action_confirmation_blocked_reasons"])
        self.assertNotIn("previous_5m_not_found", stock_row["trace_json"].get("blocked_reasons") or [])
        self.assertEqual(stock_row["trace_json"]["metric_role"], "trigger_proof")
        self.assertEqual(stock_row["trace_json"]["proof_owner"], "N3")
        self.assertEqual(stock_row["trace_json"]["proof_consumer"], "N4")
        self.assertTrue(stock_row["trace_json"]["not_n5_final_proof"])

    def test_n3p_stock_quote_batches_cap_at_80_symbols(self) -> None:
        symbols = [f"{idx:06d}" for idx in range(1, 166)]

        batches = writer.build_n3p_stock_quote_symbol_batches(symbols)

        self.assertEqual([len(batch) for batch in batches], [80, 80, 5])
        self.assertEqual(batches[0][0], "000001")
        self.assertEqual(batches[-1][-1], "000165")

    def test_b1_realtime_trigger_proof_stock_quote_amount_is_cumulative_elapsed_amount(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            b1_source_returned_n3p_contract(expected_total=2),
            b1_realtime_trigger_proof_payload(),
        )
        stock_row = rows_by_asset["stock"][0]

        self.assertTrue(stock_row["metric_ready"])
        self.assertEqual(stock_row["current_price"], 151)
        self.assertAlmostEqual(stock_row["today_virt_amount"], 9600.0)
        proof = stock_row["trace_json"]["virtual_amount_policy"]["periods"]["D"]
        self.assertEqual(proof["current_elapsed_amount"], 1000)
        self.assertEqual(proof["current_elapsed_count"], 25)
        self.assertEqual(proof["current_period_amount_source_kind"], "stock_quotes_cumulative_amount")
        self.assertEqual(stock_row["raw_json"]["n3p_realtime_source_model"], "n3p_trigger_proof_realtime_v1")
        self.assertEqual(stock_row["raw_json"]["amount_source_kind"], "stock_quotes_cumulative_amount")
        self.assertTrue(stock_row["trace_json"]["not_n5_final_proof"])

    def test_b1_realtime_trigger_proof_zero_stock_quote_is_not_ready(self) -> None:
        payload = b1_realtime_trigger_proof_payload(proof_input_time="2026-06-12T09:31:00+08:00")
        payload["stock_quote_rows"][0].update(
            {
                "proof_input_time": "2026-06-12T09:31:00+08:00",
                "source_time": "2026-06-12T09:20:00+08:00",
                "canonical_stock_quote_proof_minute": "09:31",
                "price": 0,
                "open": 0,
                "high": 0,
                "low": 0,
                "volume": 0,
                "amount": 1000,
                "servertime": "09:20:00.000",
            }
        )

        contract = b1_source_returned_n3p_contract(until_hhmm="0931", expected_total=2)
        contract["source_scope"]["proof_input_time"] = "2026-06-12T09:31:00+08:00"
        contract["db_backed_input_contract"]["source_snapshot_time"] = "2026-06-12T09:31:00+08:00"
        contract["db_backed_input_contract"]["observed_at"] = "2026-06-12T09:31:00+08:00"

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        stock_row = rows_by_asset["stock"][0]
        board_row = rows_by_asset["board"][0]

        self.assertFalse(stock_row["metric_ready"])
        self.assertFalse(stock_row["raw_json"]["trigger_proof_ready"])
        self.assertFalse(stock_row["raw_json"]["action_confirmation_ready"])
        self.assertIn("stock_quote_zero_price_ohlc_volume", stock_row["trace_json"]["blocked_reasons"])
        self.assertIn(
            "stock_quote_zero_price_ohlc_volume",
            stock_row["raw_json"]["action_confirmation_blocked_reasons"],
        )
        self.assertTrue(stock_row["trace_json"]["source_trace"]["source_quote_zero_price_ohlc_volume"])
        self.assertTrue(stock_row["raw_json"]["source_quote_zero_price_ohlc_volume"])
        self.assertEqual(stock_row["raw_json"]["source_quote_servertime"], "09:20:00.000")
        self.assertEqual(stock_row["raw_json"]["canonical_proof_minute"], "09:31")
        self.assertEqual(stock_row["raw_json"]["stock_quote_source_values"]["price"], 0)
        self.assertTrue(board_row["metric_ready"])

    def test_b1_realtime_trigger_proof_non_zero_stock_quote_can_remain_ready(self) -> None:
        payload = b1_realtime_trigger_proof_payload(proof_input_time="2026-06-12T09:31:00+08:00")
        payload["stock_quote_rows"][0].update(
            {
                "proof_input_time": "2026-06-12T09:31:00+08:00",
                "source_time": "2026-06-12T09:25:00+08:00",
                "canonical_stock_quote_proof_minute": "09:31",
                "price": 151,
                "open": 145,
                "high": 152,
                "low": 144,
                "volume": 100,
                "amount": 1000,
                "servertime": "09:25:00.000",
            }
        )

        contract = b1_source_returned_n3p_contract(until_hhmm="0931", expected_total=2)
        contract["source_scope"]["proof_input_time"] = "2026-06-12T09:31:00+08:00"
        contract["db_backed_input_contract"]["source_snapshot_time"] = "2026-06-12T09:31:00+08:00"
        contract["db_backed_input_contract"]["observed_at"] = "2026-06-12T09:31:00+08:00"

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        stock_row = rows_by_asset["stock"][0]

        self.assertTrue(stock_row["metric_ready"])
        self.assertFalse(stock_row["raw_json"]["source_quote_zero_price_ohlc_volume"])
        self.assertNotIn("stock_quote_zero_price_ohlc_volume", stock_row["trace_json"]["blocked_reasons"])

    def test_b1_realtime_trigger_proof_can_read_indexed_previous_day_rows(self) -> None:
        payload = b1_realtime_trigger_proof_payload()
        stock_previous_rows = [
            row for row in payload.pop("previous_day_minute_rows") if row.get("code") == "300776"
        ]
        payload["previous_day_minute_rows_by_identity"] = {
            "stock|stock:SZ:300776": stock_previous_rows,
            "board|board:TDX:881002": previous_day_minutes_with_midday_bridge_1130("881002", amount=10),
        }

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            b1_source_returned_n3p_contract(expected_total=2),
            payload,
        )

        self.assertTrue(rows_by_asset["stock"][0]["metric_ready"])
        self.assertTrue(rows_by_asset["board"][0]["metric_ready"])

    def test_b1_realtime_trigger_proof_board_1m_rows_sum_to_elapsed_amount(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            b1_source_returned_n3p_contract(expected_total=2),
            b1_realtime_trigger_proof_payload(),
        )
        board_row = rows_by_asset["board"][0]

        self.assertTrue(board_row["metric_ready"])
        self.assertEqual(board_row["current_price"], 2538)
        self.assertAlmostEqual(board_row["today_virt_amount"], 9600.0)
        proof = board_row["trace_json"]["virtual_amount_policy"]["periods"]["D"]
        self.assertEqual(proof["current_elapsed_amount"], 1000)
        self.assertEqual(proof["current_elapsed_count"], 25)
        self.assertEqual(proof["current_period_amount_source_kind"], "index_board_1m_cumulative_amount")
        self.assertEqual(board_row["raw_json"]["source_1m_adapter_method"], "index")
        self.assertEqual(board_row["raw_json"]["source_1m_frequency"], 8)

    def test_b1_realtime_trigger_proof_elapsed_labels_skip_midday_fake_1130(self) -> None:
        payload = b1_realtime_trigger_proof_payload(proof_input_time="2026-06-12T13:00:00+08:00")
        payload["stock_quote_rows"][0]["servertime"] = "13:00:05.000"
        payload["stock_quote_rows"][0]["amount"] = 2400
        payload["index_board_1m_rows"] = [
            {
                **row,
                "asset_kind": "board",
                "identity_key": "board:TDX:881002",
                "source_adapter_method": "index",
                "source_frequency": 8,
                "source_marker": "mootdx_index_frequency_8",
            }
            for row in canonical_current_day_minutes("881002", through_label="2026-06-12 13:00", amount=20)
        ]
        contract = b1_source_returned_n3p_contract(until_hhmm="1300", expected_total=2)
        contract["source_scope"]["proof_input_time"] = "2026-06-12T13:00:00+08:00"
        contract["db_backed_input_contract"]["source_snapshot_time"] = "2026-06-12T13:00:00+08:00"
        contract["db_backed_input_contract"]["observed_at"] = "2026-06-12T13:00:00+08:00"
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        board_row = rows_by_asset["board"][0]
        proof = board_row["trace_json"]["virtual_amount_policy"]["periods"]["D"]

        self.assertEqual(proof["current_elapsed_count"], 120)
        self.assertEqual(proof["previous_day_same_elapsed_refs"][-1], "2026-06-11 13:00")
        self.assertNotIn("2026-06-11 11:30", proof["previous_day_same_elapsed_refs"])
        self.assertAlmostEqual(board_row["today_virt_amount"], 4800.0)

    def test_b1_realtime_trigger_proof_normalizes_a1_previous_day_midday_bridge_1130_to_1300(self) -> None:
        payload = b1_realtime_trigger_proof_payload(proof_input_time="2026-06-12T13:00:00+08:00")
        payload["stock_quote_rows"][0]["servertime"] = "13:00:05.000"
        payload["stock_quote_rows"][0]["amount"] = 2400
        payload["previous_day_minute_rows"] = [
            *previous_day_minutes_with_midday_bridge_1130("300776", amount=10),
            *previous_day_minutes_with_midday_bridge_1130("881002", amount=10),
        ]
        payload["index_board_1m_rows"] = [
            {
                **row,
                "asset_kind": "board",
                "identity_key": "board:TDX:881002",
                "source_adapter_method": "index",
                "source_frequency": 8,
                "source_marker": "mootdx_index_frequency_8",
            }
            for row in canonical_current_day_minutes("881002", through_label="2026-06-12 13:00", amount=20)
        ]
        contract = b1_source_returned_n3p_contract(until_hhmm="1300", expected_total=2)
        contract["source_scope"]["proof_input_time"] = "2026-06-12T13:00:00+08:00"
        contract["db_backed_input_contract"]["source_snapshot_time"] = "2026-06-12T13:00:00+08:00"
        contract["db_backed_input_contract"]["observed_at"] = "2026-06-12T13:00:00+08:00"

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        board_row = rows_by_asset["board"][0]
        proof = board_row["trace_json"]["virtual_amount_policy"]["periods"]["D"]

        self.assertTrue(board_row["metric_ready"])
        self.assertEqual(len(proof["previous_day_same_full_refs"]), 240)
        self.assertIn("2026-06-11 13:00", proof["previous_day_same_full_refs"])
        self.assertNotIn("2026-06-11 11:30", proof["previous_day_same_full_refs"])
        self.assertAlmostEqual(board_row["today_virt_amount"], 4800.0)
        self.assertEqual(
            proof["previous_day_label_normalization_trace"][0]["normalization_policy"],
            "previous_day_midday_bridge_1130_to_1300_v1",
        )
        self.assertEqual(proof["previous_day_label_normalization_trace"][0]["raw_bar_time"], "2026-06-11 11:30")
        self.assertEqual(proof["previous_day_label_normalization_trace"][0]["canonical_bar_time"], "2026-06-11 13:00")

    def test_b1_realtime_trigger_proof_uses_previous_day_cumulative_rows_without_raw_scan(self) -> None:
        raw_payload = b1_realtime_trigger_proof_payload()
        raw_rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            b1_source_returned_n3p_contract(expected_total=2),
            raw_payload,
        )
        payload = b1_realtime_trigger_proof_payload()
        payload.pop("previous_day_minute_rows")
        payload["previous_day_cumulative_rows"] = [
            *previous_day_cumulative_rows(
                "300776",
                asset_kind="stock",
                identity_key="stock:SZ:300776",
                amount=10,
            ),
            *previous_day_cumulative_rows(
                "881002",
                asset_kind="board",
                identity_key="board:TDX:881002",
                amount=10,
            ),
        ]
        contract = b1_source_returned_n3p_contract(expected_total=2)
        contract["source_scope"]["require_previous_day_cumulative_rows"] = True

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        board_row = rows_by_asset["board"][0]
        raw_board_row = raw_rows_by_asset["board"][0]
        proof = board_row["trace_json"]["virtual_amount_policy"]["periods"]["D"]

        self.assertTrue(board_row["metric_ready"])
        self.assertAlmostEqual(board_row["today_virt_amount"], raw_board_row["today_virt_amount"])
        self.assertTrue(proof["previous_day_cumulative_source"])
        self.assertEqual(proof["canonical_minute_label"], "2026-06-11 09:55")
        self.assertEqual(proof["previous_day_elapsed_amount"], 250.0)
        self.assertEqual(proof["previous_day_full_amount"], 2400.0)
        self.assertEqual(proof["elapsed_count"], 25)
        self.assertEqual(proof["full_count"], 240)
        self.assertEqual(proof["source_previous_day_minute_run_id"], SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID)
        self.assertEqual(proof["normalization_policy"], "previous_day_midday_bridge_1130_to_1300_v1")
        self.assertEqual(board_row["raw_json"]["previous_day_cumulative_source"], True)

    def test_previous_day_cumulative_db_loader_aliases_rows_for_builder(self) -> None:
        rows_by_asset = {
            "stock": [
                previous_day_cumulative_db_row(),
            ],
            "index": [
                previous_day_cumulative_db_row(
                    asset_kind="index",
                    identity_key="index:SH:000001",
                    code="000001",
                    source_amount_unit="yuan",
                    unit_conversion_factor=1.0,
                )
            ],
            "board": [
                previous_day_cumulative_db_row(
                    asset_kind="board",
                    identity_key="board:TDX:881002",
                    code="881002",
                    source_amount_unit="yuan",
                    unit_conversion_factor=1.0,
                )
            ],
        }
        cur = RecordingCumulativeCursor(rows_by_asset)

        loaded = writer.load_previous_day_cumulative_rows_from_db(
            cur,
            source_previous_day_minute_run_id=SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID,
            for_trade_date="20260612",
            source_trade_date="20260611",
            proof_minute_label="2026-06-12 09:55",
            asset_scope={
                "stock": ["stock:SZ:300776"],
                "index": ["index:SH:000001"],
                "board": ["board:TDX:881002"],
            },
        )

        self.assertEqual(len(loaded), 3)
        stock_row = next(row for row in loaded if row["asset_kind"] == "stock")
        index_row = next(row for row in loaded if row["asset_kind"] == "index")
        board_row = next(row for row in loaded if row["asset_kind"] == "board")
        self.assertEqual(stock_row["previous_day_elapsed_amount"], 250.0)
        self.assertEqual(stock_row["previous_day_full_amount"], 2400.0)
        self.assertNotIn("cumulative_amount_yuan", stock_row)
        self.assertEqual(stock_row["source_amount_unit"], "thousand_yuan")
        self.assertEqual(stock_row["unit_conversion_factor"], 1000.0)
        self.assertEqual(index_row["source_amount_unit"], "yuan")
        self.assertEqual(index_row["unit_conversion_factor"], 1.0)
        self.assertEqual(board_row["source_amount_unit"], "yuan")
        self.assertEqual(board_row["unit_conversion_factor"], 1.0)
        executed_sql = "\n".join(sql for sql, _params in cur.executed)
        self.assertIn("stock_previous_day_minute_cumulative", executed_sql)
        self.assertIn("index_previous_day_minute_cumulative", executed_sql)
        self.assertIn("board_previous_day_minute_cumulative", executed_sql)

        payload = b1_realtime_trigger_proof_payload()
        payload.pop("previous_day_minute_rows")
        payload["previous_day_cumulative_rows"] = loaded
        contract = b1_source_returned_n3p_contract(expected_total=2)
        contract["source_scope"]["require_previous_day_cumulative_rows"] = True

        rows = writer.build_rows_by_asset_from_source_payload(contract, payload)
        proof = rows["board"][0]["trace_json"]["virtual_amount_policy"]["periods"]["D"]
        self.assertTrue(rows["board"][0]["metric_ready"])
        self.assertTrue(proof["previous_day_cumulative_source"])
        self.assertEqual(proof["previous_day_elapsed_amount"], 250.0)
        self.assertEqual(proof["source_previous_day_minute_run_id"], SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID)

    def test_previous_day_cumulative_db_loader_fails_closed(self) -> None:
        base = previous_day_cumulative_db_row()
        cases = [
            (
                {},
                "previous_day_cumulative_row_missing",
            ),
            (
                {"stock": [{**base, "duplicate_count": 2}]},
                "previous_day_cumulative_duplicate",
            ),
            (
                {"stock": [{**base, "cumulative_amount_yuan": 0}]},
                "previous_day_cumulative_non_positive_amount",
            ),
            (
                {"stock": [{**base, "asset_kind": "board"}]},
                "previous_day_cumulative_asset_kind_mismatch",
            ),
            (
                {"stock": [{**base, "canonical_minute_label": "2026-06-11 09:54"}]},
                "previous_day_cumulative_canonical_minute_mismatch",
            ),
            (
                {"stock": [{**base, "source_previous_day_minute_run_id": "wrong"}]},
                "previous_day_cumulative_source_run_mismatch",
            ),
        ]
        for rows_by_asset, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, reason):
                    writer.load_previous_day_cumulative_rows_from_db(
                        RecordingCumulativeCursor(rows_by_asset),
                        source_previous_day_minute_run_id=SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID,
                        for_trade_date="20260612",
                        source_trade_date="20260611",
                        proof_minute_label="09:55",
                        asset_scope={"stock": ["stock:SZ:300776"]},
                    )

    def test_b1_realtime_trigger_proof_requires_previous_day_cumulative_rows_when_contract_requires_it(self) -> None:
        payload = b1_realtime_trigger_proof_payload()
        payload.pop("previous_day_minute_rows")
        contract = b1_source_returned_n3p_contract(expected_total=2)
        contract["source_scope"]["require_previous_day_cumulative_rows"] = True

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "previous_day_cumulative_rows_missing"):
            writer.build_rows_by_asset_from_source_payload(contract, payload)

    def test_b1_realtime_trigger_proof_blocks_a1_previous_day_1130_and_1300_duplicate(self) -> None:
        payload = b1_realtime_trigger_proof_payload(proof_input_time="2026-06-12T13:00:00+08:00")
        payload["stock_quote_rows"][0]["servertime"] = "13:00:05.000"
        payload["previous_day_minute_rows"] = [
            *canonical_previous_day_minutes("300776", amount=10),
            *canonical_previous_day_minutes("881002", amount=10),
            minute_bar("881002", "2026-06-11 11:30", 100, 101, 10),
        ]
        payload["index_board_1m_rows"] = [
            {
                **row,
                "asset_kind": "board",
                "identity_key": "board:TDX:881002",
                "source_adapter_method": "index",
                "source_frequency": 8,
                "source_marker": "mootdx_index_frequency_8",
            }
            for row in canonical_current_day_minutes("881002", through_label="2026-06-12 13:00", amount=20)
        ]
        contract = b1_source_returned_n3p_contract(until_hhmm="1300", expected_total=2)
        contract["source_scope"]["proof_input_time"] = "2026-06-12T13:00:00+08:00"
        contract["db_backed_input_contract"]["source_snapshot_time"] = "2026-06-12T13:00:00+08:00"
        contract["db_backed_input_contract"]["observed_at"] = "2026-06-12T13:00:00+08:00"

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "previous_day_midday_bridge_duplicate"):
            writer.build_rows_by_asset_from_source_payload(contract, payload)

    def test_b1_realtime_trigger_proof_missing_stock_quote_amount_fails_closed(self) -> None:
        payload = b1_realtime_trigger_proof_payload()
        payload["stock_quote_rows"][0]["amount"] = None

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            b1_source_returned_n3p_contract(expected_total=2),
            payload,
        )
        stock_row = rows_by_asset["stock"][0]

        self.assertFalse(stock_row["metric_ready"])
        self.assertFalse(stock_row["raw_json"]["trigger_proof_ready"])
        self.assertIn("current_amount_missing", stock_row["trace_json"]["blocked_reasons"])

    def test_b1_source_returned_snapshot_missing_current_price_still_blocks(self) -> None:
        payload = b1_source_returned_payload()
        payload["source_records"]["300776"][-1]["close"] = None

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            b1_source_returned_n3p_contract(),
            payload,
        )
        stock_row = rows_by_asset["stock"][0]

        self.assertFalse(stock_row["metric_ready"])
        self.assertFalse(stock_row["raw_json"]["trigger_proof_ready"])
        self.assertIn("current_price_missing", stock_row["trace_json"]["blocked_reasons"])

    def test_b1_source_returned_snapshot_missing_current_amount_still_blocks(self) -> None:
        payload = b1_source_returned_payload()
        payload["source_records"]["300776"][-1]["amount"] = None

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            b1_source_returned_n3p_contract(),
            payload,
        )
        stock_row = rows_by_asset["stock"][0]

        self.assertFalse(stock_row["metric_ready"])
        self.assertFalse(stock_row["raw_json"]["trigger_proof_ready"])
        self.assertIn("current_amount_missing", stock_row["trace_json"]["blocked_reasons"])

    def test_live_current_1m_missing_previous_5m_remains_not_ready(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            live_n3p_contract(),
            b1_source_returned_payload(),
        )
        stock_row = rows_by_asset["stock"][0]

        self.assertFalse(stock_row["metric_ready"])
        self.assertIn("previous_5m_not_found", stock_row["trace_json"]["blocked_reasons"])
        self.assertNotIn("trigger_proof_ready", stock_row["raw_json"])

    def test_b1_source_returned_rows_block_candidate_minute_label_lookahead(self) -> None:
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "b1_source_returned_candidate_time_mismatch"):
            writer.build_rows_by_asset_from_source_payload(
                b1_source_returned_n3p_contract(),
                b1_source_returned_payload(candidate_minute_label="2026-06-12 09:31"),
            )

    def test_b1_source_returned_rows_block_missing_proof_input_time(self) -> None:
        contract = b1_source_returned_n3p_contract()
        contract["source_scope"].pop("proof_input_time", None)
        contract["db_backed_input_contract"].pop("source_snapshot_time", None)
        contract["db_backed_input_contract"].pop("observed_at", None)
        contract["db_backed_input_contract"].pop("fetched_at", None)

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "b1_source_returned_proof_input_time_missing"):
            writer.build_rows_by_asset_from_source_payload(
                contract,
                b1_source_returned_selection_payload(),
            )

    def test_b1_source_returned_rows_block_conflicting_candidate_today_alias(self) -> None:
        payload = b1_source_returned_payload()
        payload["candidates"][0]["source_today_minute_run_id"] = SOURCE_TODAY_MINUTE_RUN_ID

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "b1_source_returned_today_alias_mismatch"):
            writer.build_rows_by_asset_from_source_payload(b1_source_returned_n3p_contract(), payload)

    def test_b1_source_returned_payload_selection_expands_object_snapshot_to_condition_candidates(self) -> None:
        contexts = [
            n4_context_row_board_881002(
                condition_key="BUY:Q,M,W,D",
                direction="buy",
                pool_id=23901,
                scope_id=22859,
            ),
            n4_context_row_board_881002(
                condition_key="SELL:Y,Q,M",
                direction="sell",
                pool_id=23902,
                scope_id=22860,
            ),
        ]
        payload = b1_source_returned_selection_payload(contexts=contexts)

        selected = writer.build_b1_source_returned_payload_selection(
            b1_source_returned_n3p_contract(expected_total=2),
            payload,
        )

        report = selected["b1_source_returned_payload_selection_report"]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["b1_snapshot_object_count"], 1)
        self.assertEqual(report["n4_context_row_count"], 2)
        self.assertEqual(report["selected_candidate_count"], 2)
        self.assertEqual(report["selected_counts_by_asset"]["board"], 2)
        self.assertEqual(report["duplicate_count"], 0)
        self.assertEqual(report["missing_snapshot_count"], 0)
        self.assertEqual(report["missing_context_count"], 0)
        self.assertEqual(report["proof_input_minute_label"], "0955")

        candidates = selected["candidates"]
        self.assertEqual([candidate["condition_key"] for candidate in candidates], ["BUY:Q,M,W,D", "SELL:Y,Q,M"])
        self.assertEqual([candidate["source_condition_pool_id"] for candidate in candidates], [23901, 23902])
        self.assertEqual([candidate["source_minute_target_scope_id"] for candidate in candidates], [22859, 22860])
        self.assertEqual({candidate["proof_input_minute_label"] for candidate in candidates}, {"0955"})
        self.assertTrue(all(candidate["higher_period_context"] for candidate in candidates))

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            b1_source_returned_n3p_contract(expected_total=2),
            payload,
        )
        self.assertEqual(len(rows_by_asset["board"]), 2)
        self.assertEqual(
            {row["raw_json"]["condition_key"] for row in rows_by_asset["board"]},
            {"BUY:Q,M,W,D", "SELL:Y,Q,M"},
        )

    def test_b1_source_returned_payload_selection_blocks_duplicate_stable_candidate_key(self) -> None:
        context = n4_context_row_board_881002(
            condition_key="BUY:Q,M,W,D",
            direction="buy",
            pool_id=23901,
            scope_id=22859,
        )
        payload = b1_source_returned_selection_payload(contexts=[context, dict(context)])

        with self.assertRaisesRegex(
            writer.VirtualMetricWriterBlocked,
            "BLOCKED_N3P_B1_PAYLOAD_SELECTION_DUPLICATE",
        ):
            writer.build_b1_source_returned_payload_selection(b1_source_returned_n3p_contract(), payload)

    def test_b1_source_returned_payload_selection_blocks_missing_snapshot(self) -> None:
        payload = b1_source_returned_selection_payload(snapshots=[])

        with self.assertRaisesRegex(
            writer.VirtualMetricWriterBlocked,
            "BLOCKED_N3P_B1_PAYLOAD_SELECTION_MISSING_SNAPSHOT",
        ):
            writer.build_b1_source_returned_payload_selection(b1_source_returned_n3p_contract(), payload)

    def test_b1_source_returned_payload_selection_blocks_context_missing_baseline(self) -> None:
        payload = b1_source_returned_selection_payload(
            contexts=[
                n4_context_row_board_881002(
                    condition_key="BUY:Q,M,W,D",
                    direction="buy",
                    pool_id=23901,
                    scope_id=22859,
                    include_baseline=False,
                )
            ]
        )

        with self.assertRaisesRegex(
            writer.VirtualMetricWriterBlocked,
            "BLOCKED_N3P_B1_PAYLOAD_SELECTION_MISSING_CONTEXT",
        ):
            writer.build_b1_source_returned_payload_selection(b1_source_returned_n3p_contract(), payload)

    def test_b1_source_returned_payload_selection_blocks_proof_minute_relabel_risk(self) -> None:
        payload = b1_source_returned_selection_payload(
            snapshots=[b1_snapshot_row_881002(proof_input_time="2026-06-12T09:31:00+08:00")]
        )

        with self.assertRaisesRegex(
            writer.VirtualMetricWriterBlocked,
            "BLOCKED_N3P_SOURCE_TIME_RELABEL_RISK",
        ):
            writer.build_b1_source_returned_payload_selection(b1_source_returned_n3p_contract(), payload)

    def test_b1_source_returned_payload_selection_blocks_pool_scope_mismatch(self) -> None:
        snapshot = b1_snapshot_row_881002()
        snapshot["source_condition_pool_ids"] = [23999]
        snapshot["source_scope_ids"] = [22859]
        payload = b1_source_returned_selection_payload(snapshots=[snapshot])

        with self.assertRaisesRegex(
            writer.VirtualMetricWriterBlocked,
            "BLOCKED_N3P_B1_PAYLOAD_SELECTION_SCOPE_MISMATCH",
        ):
            writer.build_b1_source_returned_payload_selection(b1_source_returned_n3p_contract(), payload)

    def test_b1_source_returned_payload_selection_carries_pool_scope_context_and_snapshot_lineage(self) -> None:
        payload = b1_source_returned_selection_payload()

        selected = writer.build_b1_source_returned_payload_selection(b1_source_returned_n3p_contract(), payload)
        candidate = selected["candidates"][0]

        self.assertEqual(candidate["asset_kind"], "board")
        self.assertEqual(candidate["identity_key"], "board:TDX:881002")
        self.assertEqual(candidate["condition_key"], "BUY:Q,M,W,D")
        self.assertEqual(candidate["original_condition_key"], "BUY:Q,M,W,D")
        self.assertEqual(candidate["signal_type"], "B_BUY")
        self.assertEqual(candidate["direction"], "buy")
        self.assertEqual(candidate["source_condition_pool_id"], 23901)
        self.assertEqual(candidate["source_minute_target_scope_id"], 22859)
        self.assertEqual(candidate["source_snapshot_run_id"], B1_SOURCE_RETURNED_SNAPSHOT_RUN_ID)
        self.assertEqual(candidate["source_snapshot_row_id"], "board:TDX:881002@0955")
        self.assertEqual(candidate["proof_input_time"], "2026-06-12T09:55:00+08:00")
        self.assertEqual(candidate["proof_input_minute_label"], "0955")
        self.assertEqual(candidate["source_time_policy"], "source_returned_time")
        self.assertEqual(
            candidate["raw_json"]["b1_source_returned_payload_selection"]["source_context_run_id"],
            "trigger_context_snapshot_20260612_condition_layer_20260611_source_20260611_for_20260612_v1__atomic_rule_v1",
        )

    def test_live_current_1m_injects_n4_higher_period_context_for_688596_amount_chain(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}
        payload = live_688596_payload(include_n4_context=True)

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        stock_row = rows_by_asset["stock"][0]

        self.assertTrue(stock_row["metric_ready"])
        source = stock_row["trace_json"]["higher_period_context_source"]
        self.assertEqual(source["higher_period_context_match_strategy"], "asset_kind+identity_key+condition_key")
        self.assertEqual(source["period_trigger_baseline_source"], "n4_context_snapshot")
        self.assertEqual(
            source["source_context_run_id"],
            "trigger_context_snapshot_20260626_condition_layer_20260625_source_20260625_for_20260626_v1__atomic_rule_v1",
        )
        self.assertEqual(source["source_condition_pool_id"], 211486)
        self.assertEqual(source["source_minute_target_scope_id"], 199999)

        proof = stock_row["trace_json"]["formal_period_amount_proof"]["periods"]
        self.assertEqual(proof["W"]["current_trade_days_seed"], 4.0)
        self.assertEqual(proof["M"]["current_trade_days_seed"], 18.0)
        self.assertEqual(proof["Q"]["current_trade_days_seed"], 57.0)
        self.assertEqual(proof["W"]["avg_status"], "passed")
        self.assertEqual(proof["M"]["avg_status"], "passed")
        self.assertEqual(proof["Q"]["avg_status"], "passed")
        self.assertIsNone(proof["W"]["avg_blocked_reason"])
        self.assertNotIn("missing_current_trade_days_seed", str(proof))
        self.assertIsNotNone(stock_row["weekly_avg_with_today"])
        self.assertIsNotNone(stock_row["monthly_avg_with_today"])
        self.assertIsNotNone(stock_row["quarterly_avg_with_today"])
        self.assertTrue(stock_row["trace_json"]["trigger_amount_chain_pass"]["D"])
        self.assertTrue(stock_row["trace_json"]["trigger_amount_chain_pass"]["W"])
        self.assertTrue(stock_row["trace_json"]["trigger_amount_chain_pass"]["M"])
        self.assertEqual(
            stock_row["raw_json"]["higher_period_context_source"]["period_trigger_baseline_source"],
            "n4_context_snapshot",
        )

    def test_index_000688_new_week_uses_today_and_just_finished_week_average(self) -> None:
        today_amount = 127_195_597_248
        last_week_average = "113345131315.2"
        row = {
            "source_trade_date": "20260814",
            "for_trade_date": "20260817",
            "period_trigger_baseline_json": {
                "periods": {
                    "W": {
                        "period_key_current": "2026W33",
                        "baseline_source_trade_date": "20260814",
                        "current_amount_seed": last_week_average,
                        "current_amount_total_seed": "566725656576",
                        "current_trade_days_seed": 5,
                        "trigger_previous_amount_baseline": last_week_average,
                        "previous_avg_amount": "133071565619.2",
                    }
                }
            },
        }

        context, trace = writer.higher_period_context_from_period_baseline_row(
            row,
            source_kind="n4_context_snapshot",
        )
        metrics, proof = _build_formal_amount_chain_fields(
            today_virt_amount=today_amount,
            higher_period_context=context,
            asset_kind="index",
        )
        contracted = writer.apply_formal_amount_chain_contract(
            metric={
                "metric_ready": True,
                "quality_status": "passed",
                "blocked_reasons": [],
                **metrics,
                "trace_json": {"formal_period_amount_proof": proof},
                "raw_json": {},
            },
            candidate={"signal_type": "B_BUY", "condition_key": "BUY:D", "original_condition_key": "BUY:D"},
            higher_period_context_source=trace,
        )

        self.assertEqual(context["W"]["current_amount_total_seed"], 0)
        self.assertEqual(context["W"]["current_trade_days_seed"], 0)
        self.assertEqual(context["W"]["previous_avg_amount"], last_week_average)
        self.assertEqual(metrics["weekly_avg_with_today"], today_amount)
        self.assertEqual(metrics["prev_weekly_avg"], float(last_week_average))
        self.assertTrue(contracted["trace_json"]["trigger_amount_chain_pass"]["D"])
        self.assertEqual(
            trace["period_seed_guards"]["W"]["previous_avg_rollover_source"],
            "trigger_previous_amount_baseline",
        )

    def test_higher_period_rollover_is_symmetric_and_unit_safe(self) -> None:
        cases = [
            ("stock", "113345131.3152", "566725656.576", 127_195_597_248, 113_345_131_315.2),
            ("index", "113345131315.2", "566725656576", 127_195_597_248, 113_345_131_315.2),
            ("board", "113345131315.2", "566725656576", 127_195_597_248, 113_345_131_315.2),
        ]
        for asset_kind, seed, total, today_amount, expected_previous in cases:
            with self.subTest(asset_kind=asset_kind):
                row = {
                    "source_trade_date": "20260814",
                    "for_trade_date": "20260817",
                    "period_trigger_baseline_json": {
                        "periods": {
                            "W": {
                                "period_key_current": "2026W33",
                                "current_amount_seed": seed,
                                "current_amount_total_seed": total,
                                "current_trade_days_seed": 5,
                                "previous_avg_amount": "1",
                            }
                        }
                    },
                }
                context, _ = writer.higher_period_context_from_period_baseline_row(
                    row,
                    source_kind="n4_context_snapshot",
                )
                metrics, proof = _build_formal_amount_chain_fields(
                    today_virt_amount=today_amount,
                    higher_period_context=context,
                    asset_kind=asset_kind,
                )
                self.assertEqual(metrics["weekly_avg_with_today"], today_amount)
                self.assertEqual(metrics["prev_weekly_avg"], expected_previous)

                for signal_type, condition_key, today, expected in (
                    ("B_BUY", "BUY:D", today_amount, True),
                    ("S_SELL", "SELL:D", 100_000_000_000, True),
                ):
                    direction_metrics, direction_proof = _build_formal_amount_chain_fields(
                        today_virt_amount=today,
                        higher_period_context=context,
                        asset_kind=asset_kind,
                    )
                    contracted = writer.apply_formal_amount_chain_contract(
                        metric={
                            "metric_ready": True,
                            "quality_status": "passed",
                            "blocked_reasons": [],
                            **direction_metrics,
                            "trace_json": {"formal_period_amount_proof": direction_proof},
                            "raw_json": {},
                        },
                        candidate={
                            "signal_type": signal_type,
                            "condition_key": condition_key,
                            "original_condition_key": condition_key,
                        },
                        higher_period_context_source={},
                    )
                    self.assertIs(contracted["trace_json"]["trigger_amount_chain_pass"]["D"], expected)
                self.assertEqual(proof["periods"]["W"]["current_trade_days_seed"], 0.0)

    def test_w_m_q_y_rollover_and_same_period_context_are_guarded(self) -> None:
        cases = [
            ("W", "20260814", "20260817", "2026W33", "2026W34"),
            ("M", "20260831", "20260901", "202608", "202609"),
            ("Q", "20260930", "20261001", "2026Q3", "2026Q4"),
            ("Y", "20261231", "20270104", "2026", "2027"),
        ]
        for period, source_date, for_date, source_key, for_key in cases:
            with self.subTest(period=period):
                row = {
                    "source_trade_date": source_date,
                    "for_trade_date": for_date,
                    "period_trigger_baseline_json": {
                        "periods": {
                            period: {
                                "period_key_current": source_key,
                                "current_amount_seed": "100",
                                "current_amount_total_seed": "500",
                                "current_trade_days_seed": 5,
                                "trigger_previous_amount_baseline": "100",
                                "previous_avg_amount": "50",
                            }
                        }
                    },
                }
                context, trace = writer.higher_period_context_from_period_baseline_row(
                    row,
                    source_kind="n4_context_snapshot",
                )
                self.assertEqual(context[period]["source_period_key"], source_key)
                self.assertEqual(context[period]["for_period_key"], for_key)
                self.assertFalse(context[period]["period_seed_applied"])
                self.assertEqual(context[period]["previous_avg_amount"], "100")
                self.assertEqual(context[period]["current_trade_days_seed"], 0)
                self.assertTrue(trace["period_seed_guards"][period]["period_key_guard_pass"])

        same_period = {
            "source_trade_date": "20260813",
            "for_trade_date": "20260814",
            "period_trigger_baseline_json": {
                "periods": {
                    "W": {
                        "period_key_current": "2026W33",
                        "current_amount_seed": "100",
                        "current_amount_total_seed": "400",
                        "current_trade_days_seed": 4,
                        "previous_avg_amount": "50",
                    }
                }
            },
        }
        context, _ = writer.higher_period_context_from_period_baseline_row(
            same_period,
            source_kind="n4_context_snapshot",
        )
        self.assertTrue(context["W"]["period_seed_applied"])
        self.assertEqual(context["W"]["current_amount_total_seed"], "400")
        self.assertEqual(context["W"]["previous_avg_amount"], "50")

        combined_item = {
            "current_amount_seed": "100",
            "current_amount_total_seed": "500",
            "current_trade_days_seed": 5,
            "trigger_previous_amount_baseline": "100",
            "previous_avg_amount": "50",
        }
        combined, _ = writer.higher_period_context_from_period_baseline_row(
            {
                "source_trade_date": "20261231",
                "for_trade_date": "20270104",
                "period_trigger_baseline_json": {
                    "periods": {
                        period: {**combined_item, "period_key_current": writer._period_key_for_trade_date("20261231", period)}
                        for period in ("W", "M", "Q", "Y")
                    }
                },
            },
            source_kind="n4_context_snapshot",
        )
        self.assertEqual(
            {period: (combined[period]["current_trade_days_seed"], combined[period]["previous_avg_amount"]) for period in combined},
            {period: (0, "100") for period in ("W", "M", "Q", "Y")},
        )

    def test_higher_period_rollover_tampering_fails_closed(self) -> None:
        baseline_item = {
            "period_key_current": "2026W33",
            "current_amount_seed": "100",
            "current_amount_total_seed": "500",
            "current_trade_days_seed": 5,
            "trigger_previous_amount_baseline": "100",
        }
        for field, value, reason in (
            ("current_amount_total_seed", "499", "seed_proof_mismatch"),
            ("trigger_previous_amount_baseline", "99", "trigger_baseline_mismatch"),
            ("period_key_current", "2026W32", "baseline_period_key_mismatch"),
        ):
            with self.subTest(field=field):
                item = dict(baseline_item)
                item[field] = value
                with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, f"higher_period_rollover_{reason}:W"):
                    writer.higher_period_context_from_period_baseline_row(
                        {
                            "source_trade_date": "20260814",
                            "for_trade_date": "20260817",
                            "period_trigger_baseline_json": {"periods": {"W": item}},
                        },
                        source_kind="n4_context_snapshot",
                    )

        with self.assertRaisesRegex(
            writer.VirtualMetricWriterBlocked,
            "higher_period_rollover_period_key_unavailable:W",
        ):
            writer.higher_period_context_from_period_baseline_row(
                {
                    "source_trade_date": "20260814",
                    "period_trigger_baseline_json": {"periods": {"W": baseline_item}},
                },
                source_kind="n4_context_snapshot",
            )

    def test_amount_chain_trace_uses_n4_current_period_avg_transition_input(self) -> None:
        metric = {
            "metric_ready": True,
            "quality_status": "passed",
            "blocked_reasons": [],
            "today_virt_amount": 1000,
            "weekly_avg_with_today": 130,
            "current_m_virtual_amount": 1,
            "monthly_avg_with_today": 120,
            "quarterly_avg_with_today": 110,
            "yearly_avg_with_today": 105,
            "prev_quarterly_avg": 100,
            "trace_json": {
                "formal_period_amount_proof": {
                    "periods": {
                        "Q": {"avg_status": "passed"},
                    }
                }
            },
            "raw_json": {},
        }
        candidate = {
            "signal_type": "B_BUY",
            "condition_key": "BUY:M",
            "original_condition_key": "BUY:M",
        }

        row = writer.apply_formal_amount_chain_contract(
            metric=metric,
            candidate=candidate,
            higher_period_context_source={},
        )

        self.assertTrue(row["trace_json"]["trigger_amount_chain_pass"]["M"])
        transition_input = row["trace_json"]["transition_input_by_period"]["M"]
        self.assertEqual(transition_input["current_period_avg_with_today_field"], "monthly_avg_with_today")
        self.assertEqual(transition_input["current_period_avg_with_today_value"], 120)
        self.assertEqual(transition_input["used_for_period"], "M")
        self.assertEqual(transition_input["compare_to"], "previous_avg_amount[M]")
        self.assertNotIn("today_virt_amount_field", transition_input)
        d_transition_input = row["trace_json"]["transition_input_by_period"]["D"]
        self.assertEqual(d_transition_input["current_period_avg_with_today_field"], "today_virt_amount")
        self.assertEqual(d_transition_input["current_period_avg_with_today_value"], 1000)
        y_transition_input = row["trace_json"]["transition_input_by_period"]["Y"]
        self.assertEqual(y_transition_input["current_period_avg_with_today_field"], "yearly_avg_with_today")
        self.assertEqual(y_transition_input["current_period_avg_with_today_value"], 105)
        self.assertEqual(y_transition_input["used_for_period"], "Y")
        self.assertEqual(y_transition_input["compare_to"], "previous_avg_amount[Y]")
        amount_chain_input = row["trace_json"]["amount_chain_input_by_period"]["M"]
        self.assertEqual(amount_chain_input["left_field"], "monthly_avg_with_today")
        self.assertEqual(amount_chain_input["middle_field"], "quarterly_avg_with_today")
        self.assertEqual(amount_chain_input["baseline_field"], "prev_quarterly_avg")
        trace_text = json.dumps(row["trace_json"], ensure_ascii=False)
        self.assertNotIn("today_virt_amount(M)", trace_text)
        self.assertNotIn("today_virt_amount[Q]", trace_text)
        self.assertNotIn("today_virt_amount_field", trace_text)
        self.assertNotIn("today_virt_amount is a single intraday virtual amount input reused", trace_text)

    def test_live_current_1m_matches_n4_context_by_pool_and_scope_id_arrays(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}
        payload = live_688596_payload(include_n4_context=True)
        candidate = payload["candidates"][0]
        candidate["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        candidate["source_condition_pool_ids"] = [211486]
        candidate["source_scope_ids"] = [199999]

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        stock_row = rows_by_asset["stock"][0]

        self.assertTrue(stock_row["metric_ready"])
        self.assertEqual(
            stock_row["trace_json"]["higher_period_context_source"]["higher_period_context_match_strategy"],
            "source_condition_pool_id+source_minute_target_scope_id",
        )

    def test_live_current_1m_matches_n4_context_by_pool_and_scope_ids(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}
        payload = live_688596_payload(include_n4_context=True)
        candidate = payload["candidates"][0]
        candidate["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        candidate["source_condition_pool_id"] = 211486
        candidate["source_minute_target_scope_id"] = 199999

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        stock_row = rows_by_asset["stock"][0]

        self.assertTrue(stock_row["metric_ready"])
        source = stock_row["trace_json"]["higher_period_context_source"]
        self.assertEqual(source["higher_period_context_match_strategy"], "source_condition_pool_id+source_minute_target_scope_id")
        self.assertEqual(source["source_condition_pool_id"], 211486)
        self.assertEqual(source["source_minute_target_scope_id"], 199999)

    def test_live_current_1m_matches_n4_context_by_original_condition_key(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}
        payload = live_688596_payload(include_n4_context=True)
        candidate = payload["candidates"][0]
        candidate["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        candidate["original_condition_key"] = "BUY:M,W,D"

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        stock_row = rows_by_asset["stock"][0]

        self.assertTrue(stock_row["metric_ready"])
        source = stock_row["trace_json"]["higher_period_context_source"]
        self.assertEqual(source["higher_period_context_match_strategy"], "asset_kind+identity_key+original_condition_key")
        self.assertEqual(source["original_condition_key"], "BUY:M,W,D")
        self.assertEqual(stock_row["trace_json"]["formal_amount_chain_required_periods"], ["D", "W", "M"])

    def test_live_current_1m_matches_n4_context_by_condition_keys_array(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}
        payload = live_688596_payload(include_n4_context=True)
        candidate = payload["candidates"][0]
        candidate["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        candidate["condition_keys"] = ["BUY:M,W,D"]

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        stock_row = rows_by_asset["stock"][0]

        self.assertTrue(stock_row["metric_ready"])
        self.assertEqual(
            stock_row["trace_json"]["higher_period_context_source"]["higher_period_context_match_strategy"],
            "asset_kind+identity_key+condition_keys",
        )

    def test_live_current_1m_direction_fallback_matches_only_when_unique(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}
        payload = live_688596_payload(include_n4_context=True)
        candidate = payload["candidates"][0]
        candidate["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        candidate["direction"] = "buy"

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        stock_row = rows_by_asset["stock"][0]

        self.assertTrue(stock_row["metric_ready"])
        self.assertEqual(
            stock_row["trace_json"]["higher_period_context_source"]["higher_period_context_match_strategy"],
            "asset_kind+identity_key+direction_unique",
        )

    def test_live_current_1m_direction_fallback_ambiguous_fails_closed(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}
        payload = live_688596_payload(include_n4_context=True)
        second_context = dict(n4_context_row_688596())
        second_context["condition_key"] = "BUY:W,D"
        second_context["source_condition_pool_id"] = 211487
        second_context["source_minute_target_scope_id"] = 200000
        payload["n4_context_snapshot_rows"].append(second_context)
        candidate = payload["candidates"][0]
        candidate["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        candidate["direction"] = "buy"

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "higher_period_context_ambiguous_match"):
            writer.build_rows_by_asset_from_source_payload(contract, payload)

    def test_live_current_1m_original_condition_key_ambiguous_fails_closed(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}
        payload = live_688596_payload(include_n4_context=True)
        second_context = dict(n4_context_row_688596())
        second_context["source_condition_pool_id"] = 211487
        second_context["source_minute_target_scope_id"] = 200000
        payload["n4_context_snapshot_rows"].append(second_context)
        candidate = payload["candidates"][0]
        candidate["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        candidate["original_condition_key"] = "BUY:M,W,D"

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "higher_period_context_ambiguous_match"):
            writer.build_rows_by_asset_from_source_payload(contract, payload)

    def test_live_current_1m_pool_scope_ambiguous_fails_closed(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}
        payload = live_688596_payload(include_n4_context=True)
        second_context = dict(n4_context_row_688596())
        second_context["condition_key"] = "BUY:W,D"
        payload["n4_context_snapshot_rows"].append(second_context)
        candidate = payload["candidates"][0]
        candidate["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        candidate["source_condition_pool_id"] = 211486
        candidate["source_minute_target_scope_id"] = 199999

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "higher_period_context_ambiguous_match"):
            writer.build_rows_by_asset_from_source_payload(contract, payload)

    def test_live_current_1m_missing_required_higher_period_context_fails_closed(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "metric_not_ready_rows_present"):
            writer.run_virtual_metric_writer(
                contract=contract,
                preflight={"result": "PREFLIGHT_PASS"},
                source_payload=live_688596_payload(include_n4_context=False),
                execute=False,
                user_confirmed=False,
                target_absence_counts=clean_target_counts(),
            )

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(
            contract,
            live_688596_payload(include_n4_context=False),
        )
        stock_row = rows_by_asset["stock"][0]
        self.assertFalse(stock_row["metric_ready"])
        self.assertIn("formal_amount_chain_missing", str(stock_row["trace_json"]["blocked_reasons"]))
        self.assertIn("missing_current_trade_days_seed", str(stock_row["trace_json"]["formal_period_amount_proof"]))

    def test_live_current_1m_higher_period_context_conflict_fails_closed(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["expected_rows"]["by_signal_type"] = {"B_BUY": 1}
        payload = live_688596_payload(include_n4_context=True)
        payload["candidates"][0]["higher_period_context"] = {
            "W": {
                "current_trade_days_seed": 99,
            }
        }

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "higher_period_context_conflict"):
            writer.build_rows_by_asset_from_source_payload(contract, payload)

    def test_live_current_1m_source_records_normalize_mootdx_raw_1300_to_canonical_1130(self) -> None:
        contract = live_n3p_contract(expected_total=1)
        contract["source_scope"]["for_trade_date"] = "20260626"
        contract["source_scope"]["source_adapter"] = "mootdx"
        contract["until_minute_label"] = "2026-06-26 11:30"
        payload = {
            "source_records": {
                "300776": [
                    *previous_same_window_minutes("300776", open_=140, close=141, amount=10),
                    minute_bar("300776", "2026-06-26 11:29", 145, 146, 90),
                    minute_bar("300776", "2026-06-26 13:00", 146, 151, 100),
                ],
            },
            "candidates": [
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SZ:300776",
                    "exchange": "SZ",
                    "code": "300776",
                    "display_code": "300776",
                    "name": "帝尔激光",
                    "signal_type": "B_BUY",
                    "condition_key": "BUY:D",
                    "minute_label": "2026-06-26 13:00",
                    "observed_at": "2026-06-26 13:00:05",
                    "higher_period_context": {},
                    "source_adapter": "mootdx",
                }
            ],
        }

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, payload)
        stock_row = rows_by_asset["stock"][0]

        self.assertEqual(stock_row["metric_time_label"], "2026-06-26 11:30")
        self.assertEqual(stock_row["metric_minute_label"], "11:30")
        proof = stock_row["raw_json"]["closed_minute_proof"]
        self.assertEqual(proof["selected_metric_time"], "2026-06-26T11:30:00+08:00")
        trace = stock_row["raw_json"]["minute_label_normalization"]
        self.assertEqual(trace["raw_bar_time"], "2026-06-26T13:00:00+08:00")
        self.assertEqual(trace["canonical_bar_time"], "2026-06-26T11:30:00+08:00")
        self.assertEqual(trace["time_label_normalization"], "mootdx_intraday_1300_to_1130")
        self.assertEqual(trace["canonical_minute_policy"], "ashare_cn_1m_v1")
        self.assertEqual(stock_row["trace_json"]["minute_label_normalization"], trace)
        self.assertEqual(proof["minute_label_normalization"], trace)
        self.assertNotIn("13:00_label_equivalent_to_missing_11:30_bar", str(stock_row))

    def test_live_current_1m_raw_1300_without_normalization_fails_closed_in_builder(self) -> None:
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "raw 13:00"):
            writer.assert_no_live_current_raw_1300_label(
                [{"bar_time": datetime(2026, 6, 26, 13, 0)}],
                source_record_key="300776",
            )

    def test_live_current_1m_missing_rows_fails_closed(self) -> None:
        payload = source_payload()
        payload["candidates"] = []

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "missing live_current_minute_rows"):
            writer.build_rows_by_asset_from_source_payload(live_n3p_contract(), payload)

    def test_live_current_sparse_no_trade_exception_is_quality_visible_not_blocking(self) -> None:
        contract = live_sparse_n3p_contract()
        payload = live_sparse_no_trade_payload(exception_count=1)

        report = writer.run_virtual_metric_writer(
            contract=contract,
            preflight={"result": "PREFLIGHT_PASS"},
            source_payload=payload,
            execute=False,
            user_confirmed=False,
            target_absence_counts=clean_target_counts(),
        )

        exception_report = report["live_current_sparse_no_trade_exception_report"]
        self.assertEqual(report["planned_rows"]["total"], 1)
        self.assertEqual(report["rows_by_asset"]["stock"], 0)
        self.assertEqual(report["rows_by_asset"]["board"], 1)
        self.assertEqual(report["metric_ready_count"], 1)
        self.assertEqual(exception_report["status"], "passed")
        self.assertEqual(exception_report["exception_count"], 1)
        self.assertEqual(exception_report["exception_count_threshold"], 20)
        self.assertEqual(exception_report["exceptions"][0]["identity_key"], "stock:SH:688260")
        self.assertEqual(exception_report["exceptions"][0]["reason"], "adapter_sparse_no_trade")
        self.assertEqual(exception_report["exceptions"][0]["latest_row_minute"], "2026-06-26 09:31")
        self.assertEqual(exception_report["exceptions"][0]["expected_target_minute"], "2026-06-26 13:55")
        self.assertFalse(exception_report["exceptions"][0]["writes_fake_bar"])
        self.assertFalse(exception_report["exceptions"][0]["uses_previous_minute_as_target"])
        self.assertFalse(exception_report["exceptions"][0]["metric_ready"])
        self.assertNotIn("stock:SH:688260", str(report["signal_counts"]))

    def test_live_current_sparse_no_trade_exception_threshold_allows_twenty(self) -> None:
        report = writer.run_virtual_metric_writer(
            contract=live_sparse_n3p_contract(),
            preflight={"result": "PREFLIGHT_PASS"},
            source_payload=live_sparse_no_trade_payload(exception_count=20),
            execute=False,
            user_confirmed=False,
            target_absence_counts=clean_target_counts(),
        )

        self.assertEqual(report["live_current_sparse_no_trade_exception_count"], 20)
        self.assertEqual(report["live_current_sparse_no_trade_exception_report"]["status"], "passed")
        self.assertEqual(report["planned_rows"]["total"], 1)

    def test_live_current_sparse_no_trade_exception_threshold_exceeded_fails_closed(self) -> None:
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "threshold_exceeded"):
            writer.run_virtual_metric_writer(
                contract=live_sparse_n3p_contract(),
                preflight={"result": "PREFLIGHT_PASS"},
                source_payload=live_sparse_no_trade_payload(exception_count=21),
                execute=False,
                user_confirmed=False,
                target_absence_counts=clean_target_counts(),
            )

    def test_live_current_sparse_no_trade_exception_never_fabricates_target_minute(self) -> None:
        payload = live_sparse_no_trade_payload(exception_count=1)
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(live_sparse_n3p_contract(), payload)
        rows = [row for asset_rows in rows_by_asset.values() for row in asset_rows]

        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["identity_key"], "stock:SH:688260")
        self.assertNotEqual(rows[0]["metric_time_label"], "2026-06-26 13:55")

        blocked_payload = live_sparse_no_trade_payload(exception_count=1)
        blocked_payload["live_current_sparse_no_trade_exceptions"][0]["writes_fake_bar"] = True
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "fake_bar_forbidden"):
            writer.build_rows_by_asset_from_source_payload(live_sparse_n3p_contract(), blocked_payload)

    def test_dirty_target_blocks_before_injected_execute_writer(self) -> None:
        called = False
        dirty_counts = clean_target_counts()
        dirty_counts["common_market_data_run"] = 1

        def fake_write(*_args, **_kwargs):
            nonlocal called
            called = True

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "BLOCKED_TARGET_NOT_EMPTY"):
            writer.run_virtual_metric_writer(
                contract=n3p_contract(),
                preflight={"result": "PREFLIGHT_PASS"},
                source_payload=source_payload(),
                execute=True,
                user_confirmed=True,
                target_absence_counts=dirty_counts,
                write_fn=fake_write,
            )

        self.assertFalse(called)

    def test_default_plan_only_does_not_call_writer(self) -> None:
        called = False

        def fake_write(*_args, **_kwargs):
            nonlocal called
            called = True

        report = writer.run_virtual_metric_writer(
            contract=mini_contract(),
            preflight={"result": "PREFLIGHT_PASS"},
            source_payload=source_payload(),
            execute=False,
            user_confirmed=False,
            write_fn=fake_write,
        )

        self.assertEqual(report["result"], "PLAN_ONLY")
        self.assertFalse(called)
        self.assertFalse(report["side_effects"]["database_written"])
        self.assertFalse(report["side_effects"]["outbox_written"])
        self.assertFalse(report["side_effects"]["n4_n5_executed"])

    def test_missing_flags_block_before_payload_and_writer(self) -> None:
        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "missing --user-confirmed"):
            writer.run_virtual_metric_writer(
                contract=mini_contract(),
                preflight={"result": "PREFLIGHT_PASS"},
                source_payload=source_payload(),
                execute=True,
                user_confirmed=False,
                write_fn=lambda *_args, **_kwargs: self.fail("writer must not be called"),
            )

        with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "missing --execute"):
            writer.run_virtual_metric_writer(
                contract=mini_contract(),
                preflight={"result": "PREFLIGHT_PASS"},
                source_payload=source_payload(),
                execute=False,
                user_confirmed=True,
                write_fn=lambda *_args, **_kwargs: self.fail("writer must not be called"),
            )

    def test_source_record_key_overrides_code_for_full_scope_collision_safety(self) -> None:
        payload = source_payload()
        payload["source_records"] = {
            "stock:SH:000001": payload["source_records"]["300776"],
            "board:TDX:000001": payload["source_records"]["881002"],
        }
        payload["candidates"][0]["code"] = "000001"
        payload["candidates"][0]["source_record_key"] = "stock:SH:000001"
        payload["candidates"][1]["code"] = "000001"
        payload["candidates"][1]["source_record_key"] = "board:TDX:000001"

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(), payload)

        self.assertEqual(len(rows_by_asset["stock"]), 1)
        self.assertEqual(len(rows_by_asset["board"]), 1)
        self.assertEqual(rows_by_asset["stock"][0]["identity_key"], "stock:SZ:300776")
        self.assertEqual(rows_by_asset["board"][0]["identity_key"], "board:TDX:881002")

    def test_builds_canonical_realtime_virtual_metric_rows_from_source_payload(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(), source_payload())
        rows = [row for asset_rows in rows_by_asset.values() for row in asset_rows]

        self.assertEqual(len(rows), 2)
        stock_row = rows_by_asset["stock"][0]
        board_row = rows_by_asset["board"][0]
        self.assertEqual(stock_row["projection_run_id"], mini_contract()["target_run_id"])
        self.assertEqual(stock_row["source_condition_run_id"], "condition_layer_20260611_source_20260611_for_20260612_v1")
        self.assertEqual(stock_row["asset_kind"], "stock")
        self.assertEqual(stock_row["raw_json"]["signal_type"], "B_BUY")
        self.assertEqual(board_row["raw_json"]["signal_type"], "S_SELL")
        self.assertTrue(stock_row["metric_ready"])
        self.assertEqual(stock_row["session_kind"], "auction")
        self.assertTrue(stock_row["is_auction_virtual"])
        self.assertIn("current_d_body_high", stock_row)
        self.assertIn("previous_y_amount", stock_row)
        self.assertNotIn("current_D_body_high", stock_row)
        self.assertEqual(stock_row["trace_json"]["display_alias_to_db_column"]["current_D_body_high"], "current_d_body_high")
        self.assertIn("today_virt_amount", stock_row)
        self.assertIn("weekly_avg_with_today", stock_row)
        self.assertIn("prev_weekly_avg", stock_row)
        self.assertEqual(
            stock_row["trace_json"]["formal_period_amount_proof"]["source_kind"],
            "N3_standard_period_metric",
        )
        self.assertEqual(
            stock_row["trace_json"]["formal_period_amount_proof"]["amount_unit"],
            "yuan",
        )
        self.assertEqual(
            stock_row["trace_json"]["formal_amount_chain_metrics"]["today_virt_amount"],
            stock_row["today_virt_amount"],
        )
        self.assertEqual(
            stock_row["trace_json"]["virtual_amount_policy"]["periods"]["30m"]["metric_policy"],
            "previous_day_same_window_elapsed_ratio_v1",
        )

    def test_formal_amount_chain_keeps_stock_thousand_yuan_conversion(self) -> None:
        payload = source_payload()
        payload["source_records"] = {"300776": payload["source_records"]["300776"]}
        payload["candidates"] = [payload["candidates"][0]]

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(expected_total=1), payload)
        proof = rows_by_asset["stock"][0]["trace_json"]["formal_period_amount_proof"]

        self.assertEqual(proof["asset_kind"], "stock")
        self.assertEqual(proof["source_amount_unit"], "thousand_yuan")
        self.assertEqual(proof["unit_conversion_factor"], 1000.0)
        self.assertEqual(proof["unit_conversion_policy"], "formal_amount_chain_thousand_yuan_to_yuan_v1")

    def test_formal_amount_chain_uses_yuan_passthrough_for_index(self) -> None:
        payload = source_payload()
        index_candidate = dict(payload["candidates"][1])
        index_candidate.update(
            {
                "asset_kind": "index",
                "identity_key": "index:SH:000016",
                "exchange": "SH",
                "code": "000016",
                "display_code": "000016",
                "name": "上证50",
                "signal_type": "B_BUY",
                "condition_key": "BUY:Y,D",
            }
        )
        payload["source_records"] = {
            "000016": [
                {**row, "code": "000016"}
                for row in payload["source_records"]["881002"]
            ]
        }
        payload["candidates"] = [index_candidate]

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(expected_total=1), payload)
        row = rows_by_asset["index"][0]
        proof = row["trace_json"]["formal_period_amount_proof"]

        self.assertEqual(proof["asset_kind"], "index")
        self.assertEqual(proof["source_amount_unit"], "yuan")
        self.assertEqual(proof["unit_conversion_factor"], 1.0)
        self.assertEqual(proof["unit_conversion_policy"], "true_full_day_minute_series_yuan_passthrough_v1")
        self.assertTrue(row["raw_json"]["trigger_amount_chain_pass"]["D"])

    def test_formal_amount_chain_uses_yuan_passthrough_for_board(self) -> None:
        payload = source_payload()
        board_candidate = dict(payload["candidates"][1])
        board_candidate.update(
            {
                "signal_type": "B_BUY",
                "condition_key": "BUY:Y,D",
            }
        )
        payload["source_records"] = {"881002": payload["source_records"]["881002"]}
        payload["candidates"] = [board_candidate]

        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(expected_total=1), payload)
        row = rows_by_asset["board"][0]
        proof = row["trace_json"]["formal_period_amount_proof"]

        self.assertEqual(proof["asset_kind"], "board")
        self.assertEqual(proof["source_amount_unit"], "yuan")
        self.assertEqual(proof["unit_conversion_factor"], 1.0)
        self.assertEqual(proof["unit_conversion_policy"], "true_full_day_minute_series_yuan_passthrough_v1")
        self.assertTrue(row["raw_json"]["trigger_amount_chain_pass"]["D"])

    def test_n3p_plan_only_proof_summary_exposes_cache_contract(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(n3p_contract(expected_total=1), live_688596_payload())
        proof_rows = writer.build_n3p_plan_only_proof_summary_rows(rows_by_asset)

        self.assertEqual(len(proof_rows), 1)
        proof = proof_rows[0]
        row = rows_by_asset["stock"][0]
        self.assertEqual(proof["proof_version"], "n3p_plan_only_proof_summary_v1")
        self.assertEqual(proof["identity_key"], "stock:SH:688596")
        self.assertEqual(proof["stable_trigger_key"], "20260612|stock|stock:SH:688596|B_BUY|BUY:M,W,D|M|normal|14:47")
        self.assertEqual(proof["metric_ready"], row["metric_ready"])
        self.assertEqual(proof["trigger_amount_chain_pass"], row["raw_json"]["trigger_amount_chain_pass"])
        self.assertIn("source_input_fingerprint", proof)
        self.assertIn("context_fingerprint", proof)
        self.assertIn("amount_chain_boundary", proof)
        self.assertIn("next_recompute_condition", proof)
        self.assertFalse(proof["safe_negative_cacheable"])

    def test_n3p_plan_only_proof_summary_marks_buy_amount_chain_false_safe_negative(self) -> None:
        row = {
            "for_trade_date": "20260626",
            "asset_kind": "board",
            "identity_key": "board:TDX:881034",
            "signal_type": "B_BUY",
            "condition_key": "LIVE_CURRENT_1M:B_BUY",
            "trigger_mark_candidate": "normal",
            "metric_minute_label": "09:31",
            "metric_ready": True,
            "source_condition_run_id": "condition_layer_20260625_source_20260625_for_20260626_v1",
            "raw_json": {
                "original_condition_key": "BUY:M,W,D",
                "condition_keys": ["BUY:M,W,D"],
                "formal_amount_chain_required_periods": ["D", "W", "M"],
                "formal_amount_chain_input_ready": {"D": True, "W": True, "M": True, "Q": True},
                "formal_amount_chain_missing_inputs": {"D": [], "W": [], "M": [], "Q": []},
                "trigger_amount_chain_pass": {"D": True, "W": False, "M": True, "Q": True, "Y": "not_applicable"},
                "formal_amount_chain_metrics": {"today_virt_amount": "1000"},
                "formal_period_amount_proof": {"periods": {"M": {"previous_avg_amount": "1200"}}},
            },
            "trace_json": {
                "higher_period_context_source": {
                    "source_context_run_id": "trigger_context_snapshot_20260626_condition_layer_20260625_source_20260625_for_20260626_v1__atomic_rule_v1",
                    "source_condition_pool_id": 211486,
                    "source_minute_target_scope_id": 199999,
                    "original_condition_key": "BUY:M,W,D",
                    "higher_period_context_match_strategy": "source_condition_pool_id+source_minute_target_scope_id",
                }
            },
        }

        proof = writer.build_n3p_plan_only_proof_summary_rows({"board": [row]})[0]

        self.assertTrue(proof["safe_negative_cacheable"])
        self.assertEqual(proof["safe_negative_cacheable_reason"], "amount_chain_failed_for_required_period")
        self.assertEqual(proof["unsafe_negative_cacheable_reason"], "")
        self.assertEqual(proof["original_condition_key"], "BUY:M,W,D")
        self.assertEqual(proof["requested_periods"], ["D", "W", "M"])
        self.assertEqual(proof["proof_input_minute"], "09:31")
        self.assertEqual(
            proof["stable_trigger_key"],
            "20260626|board|board:TDX:881034|B_BUY|BUY:M,W,D|M|normal|09:31",
        )
        self.assertEqual(
            proof["required_period_boundaries"]["W"]["safe_negative_cacheable_reason"],
            "amount_chain_failed_for_required_period",
        )

    def test_n3p_plan_only_proof_summary_exposes_source_returned_time_policy(self) -> None:
        row = {
            "for_trade_date": "20260629",
            "asset_kind": "index",
            "identity_key": "index:SH:000016",
            "signal_type": "B_BUY",
            "condition_key": "BUY:D",
            "metric_minute_label": "09:31",
            "metric_ready": True,
            "raw_json": {
                "source_time_policy": "source_returned_time",
                "proof_input_time": "2026-06-29T09:31:00+08:00",
                "proof_input_time_source": "B1_source_snapshot_time",
                "formal_amount_chain_required_periods": ["D"],
                "formal_amount_chain_input_ready": {"D": True},
                "formal_amount_chain_missing_inputs": {"D": []},
                "trigger_amount_chain_pass": {"D": True},
            },
        }

        proof = writer.build_n3p_plan_only_proof_summary_rows({"index": [row]})[0]

        self.assertEqual(proof["source_time_policy"], "source_returned_time")
        self.assertEqual(proof["proof_input_time"], "2026-06-29T09:31:00+08:00")
        self.assertEqual(proof["proof_input_time_source"], "B1_source_snapshot_time")
        self.assertEqual(proof["proof_input_minute"], "09:31")
        self.assertEqual(proof["metric_role"], "trigger_proof")
        self.assertEqual(proof["proof_owner"], "N3")
        self.assertEqual(proof["proof_consumer"], "N4")
        self.assertTrue(proof["not_n5_final_proof"])

    def test_n3p_plan_only_proof_summary_keeps_missing_inputs_fail_open(self) -> None:
        row = {
            "for_trade_date": "20260626",
            "asset_kind": "stock",
            "identity_key": "stock:SH:688596",
            "signal_type": "B_BUY",
            "condition_key": "BUY:M,W,D",
            "metric_minute_label": "14:47",
            "metric_ready": False,
            "raw_json": {
                "formal_amount_chain_required_periods": ["D", "W", "M"],
                "formal_amount_chain_input_ready": {"D": True, "W": False, "M": True},
                "formal_amount_chain_missing_inputs": {"D": [], "W": ["missing_current_trade_days_seed"], "M": []},
                "trigger_amount_chain_pass": {"D": True, "W": None, "M": True, "Q": True, "Y": "not_applicable"},
            },
        }

        proof = writer.build_n3p_plan_only_proof_summary_rows({"stock": [row]})[0]

        self.assertFalse(proof["safe_negative_cacheable"])
        self.assertEqual(proof["unsafe_negative_cacheable_reason"], "missing_inputs_present")

    def test_row_builder_uses_reviewed_source_run_id_fk_lineage_when_payload_has_no_snapshot_run_id(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(), source_payload())
        rows = [row for asset_rows in rows_by_asset.values() for row in asset_rows]

        for row in rows:
            self.assertEqual(row["source_snapshot_run_id"], SOURCE_SNAPSHOT_RUN_ID)
            self.assertEqual(row["source_today_minute_run_id"], SOURCE_TODAY_MINUTE_RUN_ID)
            self.assertEqual(row["source_previous_day_minute_run_id"], SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID)
            self.assertEqual(
                row["source_fact_ids"]["lineage_policy"],
                "contract_reviewed_source_run_id_fk_lineage",
            )
            if row["previous_1m_period_source"] == "previous_trade_date_last_period":
                self.assertGreater(len(row["previous_day_minute_refs"]), 0)
                self.assertIn("2026-06-11 10:00", row["previous_day_minute_refs"])

    def test_row_builder_marks_source_snapshot_id_nullable_for_minute_source_metric(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(), source_payload())
        rows = [row for asset_rows in rows_by_asset.values() for row in asset_rows]

        for row in rows:
            self.assertIsNone(row["source_snapshot_id"])
            self.assertEqual(
                row["source_fact_ids"]["source_snapshot_id_policy"],
                "nullable_for_minute_source_realtime_virtual_metric",
            )
            self.assertEqual(row["trace_json"]["source_snapshot_id_policy"], "nullable_for_minute_source_realtime_virtual_metric")

    def test_row_builder_canonicalizes_current_price_source_for_db_check_constraint(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(), source_payload())
        rows = [row for asset_rows in rows_by_asset.values() for row in asset_rows]

        for row in rows:
            self.assertEqual(row["current_price_source"], "minute_bar_1m")
            self.assertEqual(
                row["trace_json"]["raw_current_price_source"],
                "n3_realtime_virtual_metric.current_1m.close",
            )
            self.assertEqual(
                row["trace_json"]["current_price_source_canonicalization"],
                "n3_realtime_virtual_metric.current_1m.close->minute_bar_1m",
            )

    def test_payload_validation_enforces_expected_rows_and_signal_distribution(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(), source_payload())
        validation = writer.validate_rows_against_contract(rows_by_asset, mini_contract())

        self.assertTrue(validation["valid"], validation)
        self.assertEqual(validation["row_counts"]["total"], 2)
        self.assertEqual(validation["signal_counts"], {"B_BUY": 1, "S_SELL": 1})

        wrong_contract = mini_contract(expected_total=3)
        wrong_contract["expected_rows"]["by_signal_type"] = {"B_BUY": 2, "S_SELL": 1}
        blocked = writer.validate_rows_against_contract(rows_by_asset, wrong_contract)
        self.assertFalse(blocked["valid"])
        self.assertIn("expected_row_count_mismatch", blocked["blocked_reasons"])

    def test_payload_validation_allows_explicit_expected_not_ready_quality_warning(self) -> None:
        contract = mini_contract()
        contract["expected_rows"]["metric_ready"] = 1
        contract["expected_rows"]["metric_not_ready"] = 1
        contract["expected_rows"]["expected_not_ready_reason"] = "expected_not_ready_insufficient_upper_period_history"
        contract["expected_rows"]["expected_not_ready_blocked_reason_prefixes"] = ["formal_amount_chain_missing:"]
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, source_payload())
        row = rows_by_asset["stock"][0]
        row["metric_ready"] = False
        row["metric_quality_status"] = "failed"
        row["raw_json"]["blocked_reasons"] = ["formal_amount_chain_missing:M:prev_quarterly_avg"]
        row["trace_json"]["blocked_reasons"] = ["formal_amount_chain_missing:M:prev_quarterly_avg"]

        validation = writer.validate_rows_against_contract(rows_by_asset, contract)

        self.assertTrue(validation["valid"], validation)
        self.assertEqual(validation["metric_ready_count"], 1)
        self.assertEqual(validation["metric_not_ready_count"], 1)
        self.assertEqual(
            validation["expected_not_ready_quality_warning"]["reason"],
            "expected_not_ready_insufficient_upper_period_history",
        )

    def test_payload_validation_allows_explicit_stock_zero_quote_not_ready_reason(self) -> None:
        contract = mini_contract()
        contract["expected_rows"]["metric_ready"] = 1
        contract["expected_rows"]["metric_not_ready"] = 1
        contract["expected_rows"]["expected_not_ready_blocked_reasons"] = [
            "stock_quote_zero_price_ohlc_volume",
        ]
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, source_payload())
        row = rows_by_asset["stock"][0]
        row["metric_ready"] = False
        row["metric_quality_status"] = "failed"
        row["raw_json"]["blocked_reasons"] = ["stock_quote_zero_price_ohlc_volume"]
        row["trace_json"]["blocked_reasons"] = ["stock_quote_zero_price_ohlc_volume"]

        validation = writer.validate_rows_against_contract(rows_by_asset, contract)

        self.assertTrue(validation["valid"], validation)

        row["trace_json"]["blocked_reasons"] = ["unexpected_zero_quote_reason"]
        row["raw_json"]["blocked_reasons"] = ["unexpected_zero_quote_reason"]
        blocked = writer.validate_rows_against_contract(rows_by_asset, contract)

        self.assertFalse(blocked["valid"])
        self.assertIn("unexpected_metric_not_ready_reason", blocked["blocked_reasons"])

    def test_payload_validation_blocks_not_ready_rows_without_explicit_policy(self) -> None:
        contract = mini_contract()
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, source_payload())
        row = rows_by_asset["stock"][0]
        row["metric_ready"] = False
        row["metric_quality_status"] = "failed"
        row["trace_json"]["blocked_reasons"] = ["formal_amount_chain_missing:M:prev_quarterly_avg"]

        validation = writer.validate_rows_against_contract(rows_by_asset, contract)

        self.assertFalse(validation["valid"])
        self.assertIn("metric_not_ready_rows_present", validation["blocked_reasons"])

    def test_payload_validation_blocks_previous_trade_date_source_without_previous_day_refs(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(), source_payload())
        rows_by_asset["stock"][0]["previous_day_minute_refs"] = []

        blocked = writer.validate_rows_against_contract(rows_by_asset, mini_contract())

        self.assertFalse(blocked["valid"])
        self.assertIn("previous_day_minute_refs_missing", blocked["blocked_reasons"])

    def test_payload_validation_blocks_missing_previous_day_same_window_amount_when_required(self) -> None:
        contract = mini_contract()
        contract["previous_day_same_window_amount_policy"] = {
            "required_for_metric_ready_rows": True,
            "writer_validation_blocker": "previous_day_same_window_amount_missing",
        }
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(contract, source_payload())
        rows_by_asset["stock"][0]["previous_day_same_window_amount"] = None

        blocked = writer.validate_rows_against_contract(rows_by_asset, contract)

        self.assertFalse(blocked["valid"])
        self.assertIn("previous_day_same_window_amount_missing", blocked["blocked_reasons"])

    def test_payload_validation_blocks_30m_virtual_amount_that_differs_from_policy_proof(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(), source_payload())
        rows_by_asset["stock"][0]["current_30m_virtual_amount"] = 8_433_135_360
        rows_by_asset["stock"][0]["trace_json"]["virtual_amount_policy"]["periods"]["30m"] = {
            "status": "passed",
            "metric_policy": "previous_day_same_window_elapsed_ratio_v1",
            "current_elapsed_amount": "281104512",
            "previous_day_same_elapsed_amount": "312718976",
            "previous_day_same_full_amount": "2613103496",
            "amount_unit": "yuan",
            "current_period_amount_source_kind": "N3_standard_period_metric",
            }

        blocked = writer.validate_rows_against_contract(rows_by_asset, mini_contract())

        self.assertFalse(blocked["valid"])
        self.assertIn("current_30m_virtual_amount_policy_mismatch", blocked["blocked_reasons"])
        self.assertEqual(blocked["virtual_amount_policy_integrity"]["mismatch_rows"], 1)

    def test_payload_validation_blocks_missing_required_virtual_amount_proof_fields(self) -> None:
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(mini_contract(), source_payload())
        rows_by_asset["stock"][0]["trace_json"]["virtual_amount_policy"]["periods"]["5m"].pop("amount_unit")

        blocked = writer.validate_rows_against_contract(rows_by_asset, mini_contract())

        self.assertFalse(blocked["valid"])
        self.assertIn("current_virtual_amount_policy_required_trace_missing", blocked["blocked_reasons"])
        self.assertEqual(blocked["virtual_amount_policy_integrity"]["required_trace_missing_rows"], 1)

    def test_payload_validation_blocks_unresolved_required_source_run_id_fk_lineage(self) -> None:
        fallback_contract = mini_contract()
        for key in (
            "source_snapshot_run_id",
            "source_today_minute_run_id",
            "source_previous_day_minute_run_id",
        ):
            fallback_contract["source_scope"].pop(key)
        rows_by_asset = writer.build_rows_by_asset_from_source_payload(fallback_contract, source_payload())

        blocked = writer.validate_rows_against_contract(rows_by_asset, fallback_contract)

        self.assertFalse(blocked["valid"])
        self.assertIn("source_run_id_fk_lineage_unresolved", blocked["blocked_reasons"])

    def test_execute_path_uses_injected_writer_and_still_writes_no_outbox(self) -> None:
        captured = {}

        def fake_write(*, contract, rows_by_asset):
            captured["contract"] = contract
            captured["rows_by_asset"] = rows_by_asset
            return {"run_rows": 1, "quality_rows": 1, "metric_rows": 2}

        report = writer.run_virtual_metric_writer(
            contract=mini_contract(),
            preflight={"result": "PREFLIGHT_PASS"},
            source_payload=source_payload(),
            execute=True,
            user_confirmed=True,
            write_fn=fake_write,
        )

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(report["write_result"]["metric_rows"], 2)
        self.assertEqual(captured["contract"]["target_run_id"], mini_contract()["target_run_id"])
        self.assertFalse(report["side_effects"]["outbox_written"])
        self.assertFalse(report["side_effects"]["outbox_inbox_checkpoint_consumed_or_updated"])
        self.assertFalse(report["side_effects"]["n4_n5_executed"])

    def test_cli_plan_only_writes_report_without_business_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            contract_path = root / "contract.json"
            preflight_path = root / "preflight.json"
            payload_path = root / "payload.json"
            report_path = root / "report.json"
            md_path = root / "report.md"
            contract_path.write_text(json.dumps(mini_contract()), encoding="utf-8")
            preflight_path.write_text(json.dumps({"result": "PREFLIGHT_PASS"}), encoding="utf-8")
            payload_path.write_text(json.dumps(source_payload()), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = writer.main(
                    [
                        "--contract-path",
                        str(contract_path),
                        "--preflight-path",
                        str(preflight_path),
                        "--source-payload-path",
                        str(payload_path),
                        "--json-report-path",
                        str(report_path),
                        "--markdown-report-path",
                        str(md_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = json.loads(report_path.read_text())
            self.assertEqual(report["result"], "PLAN_ONLY")
            self.assertFalse(report["side_effects"]["database_written"])
            self.assertIn("PLAN_ONLY", md_path.read_text())


if __name__ == "__main__":
    unittest.main()
