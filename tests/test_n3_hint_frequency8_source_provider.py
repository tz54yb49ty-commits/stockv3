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
        "target_run_id": "n3_hint_index_board_1m_source_payload_20260630_until_1300_v1",
        "n4_context_run_id": "trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1",
        "subscription_run_id": "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1",
        "hint_proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
    }
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

    def load_n3_hint_target_snapshot(self, **_kwargs):
        self.calls += 1
        return self.snapshot


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

    def test_hint_proof_preflight_excludes_first_30m_window_from_metric_facts(self) -> None:
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
                    previous_day_rows_loader=PreviousDayRowsLoader([]),
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
            self.assertEqual(result["proof_rows_total"], 0)
            self.assertEqual(result["rows_by_asset"], {})
            self.assertEqual(result["metric_ready"], {"ready": 0, "not_ready": 0})
            self.assertEqual(result["projection_type_distribution"], {})

            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            proof_row = contract["proof_rows"][0]
            self.assertFalse(proof_row["valid"])
            self.assertIsNone(proof_row["previous_completed_window_start"])
            self.assertIn("first_30m_window_no_previous_completed_window", proof_row["blocked_reasons"])
            self.assertEqual(contract["write_plan"]["metric_rows"], {})
            self.assertTrue(
                any(
                    item["gate_code"] == "N3_HINT_INDEX_BOARD_1M_PROOF_NOT_READY_EXCLUDED_FROM_FACT"
                    and item["actual_value"] == "1"
                    for item in contract["write_plan"]["quality_items"]
                )
            )

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
                "user_projection_run": 0,
                "user_signal_projection": 0,
                "user_signal_card": 0,
            },
            columns_by_table={
                "common_trigger_run": ("run_id",),
                "common_trigger_state": ("source_run_id",),
                "common_trigger_match": ("source_projection_run_id",),
                "common_action_run": ("source_run_id",),
                "common_action_event": ("trigger_run_id",),
                "user_projection_run": ("source_run_id",),
                "user_signal_projection": ("action_run_id",),
                "user_signal_card": ("projection_run_id",),
            },
        )

        snapshot = _load_n3_hint_target_snapshot_with_connection(
            conn=conn,
            target_run_id="n3_hint_index_board_1m_source_payload_20260703_0931_midday_bridge_v1",
        )

        self.assertEqual(snapshot["outbox_refs"], 2)
        self.assertEqual(snapshot["inbox_refs"], 3)
        self.assertEqual(snapshot["checkpoint_refs"], 5)
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
        self.assertIn("from common_event_inbox inbox", " ".join(executed_sql.split()))
        self.assertIn("from common_event_outbox outbox", " ".join(executed_sql.split()))
        self.assertIn("inbox.source_layer = outbox.source_layer", " ".join(executed_sql.split()))
        self.assertIn("inbox.event_id = outbox.event_id", " ".join(executed_sql.split()))
        self.assertNotIn("from common_event_inbox where source_run_id=%s", " ".join(executed_sql.split()))

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

    def test_target_snapshot_inbox_refs_use_outbox_to_inbox_index_join(self) -> None:
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
            if "from common_event_inbox inbox" in " ".join(sql.lower().split())
        ]
        self.assertEqual(len(inbox_statements), 1)
        inbox_sql, inbox_params = inbox_statements[0]
        self.assertIn("from common_event_outbox outbox", inbox_sql)
        self.assertIn("outbox.source_layer=%s", inbox_sql)
        self.assertIn("outbox.event_type = any(%s)", inbox_sql)
        self.assertIn("outbox.source_run_id=%s", inbox_sql)
        self.assertIn("inbox.source_layer = outbox.source_layer", inbox_sql)
        self.assertIn("inbox.event_id = outbox.event_id", inbox_sql)
        self.assertNotIn("from common_event_inbox where source_run_id=%s", inbox_sql)
        self.assertEqual(inbox_params[0], "N3_market_data")
        self.assertIn("MarketSnapshotUpdated", inbox_params[1])
        self.assertIn("MarketDisplaySnapshotUpdated", inbox_params[1])
        self.assertEqual(inbox_params[2], target_run_id)

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


if __name__ == "__main__":
    unittest.main()
