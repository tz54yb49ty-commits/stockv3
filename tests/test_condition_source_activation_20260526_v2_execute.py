import contextlib
from datetime import date, datetime, time
from decimal import Decimal
import importlib.util
import io
import json
import math
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from ashare_v3.ingestion.condition_source_activation_20260526_v2_execute import (
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    CONDITION_SOURCE_GAP_IDENTITIES,
    EXPECTED_REFERENCE_ROWS,
    SOURCE_VERSIONS,
    TRADE_DATE,
    ConditionSourceActivation20260526V2Blocked,
    build_commit_plan,
    build_execute_preflight_report,
    execute_commit_transaction,
    assert_json_compatible,
    jsonb_row,
    sample_pass_snapshot,
    sanitize_json_value,
    validate_commit_preconditions,
    validate_execute_request,
    validate_source_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_condition_source_activation_20260526_v2_once.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("n1_condition_source_activation_v2_execute_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def stock_daily_basic_row(index: int) -> dict:
    code = f"{500000 + index:06d}"
    return {
        "stock_identity_key": f"stock:SH:{code}",
        "trade_date": TRADE_DATE,
        "ts_code": f"{code}.SH",
        "code": code,
        "exchange": "SH",
        "close": 10.0,
        "turnover_rate": 1.0,
        "turnover_rate_f": 1.0,
        "volume_ratio": 1.0,
        "pe": 12.0,
        "pe_ttm": 11.0,
        "pb": 1.2,
        "ps": 2.1,
        "ps_ttm": 2.0,
        "dv_ratio": None,
        "dv_ttm": None,
        "total_share": 100000.0,
        "float_share": 80000.0,
        "free_share": 60000.0,
        "total_mv": 1200000.0,
        "circ_mv": 900000.0,
        "source": "mock.tushare.daily_basic",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSIONS["stock_daily_basic"],
        "raw_payload": {"mock": True, "i": index},
    }


def stock_financial_row(index: int) -> dict:
    code = f"{500000 + index:06d}"
    return {
        "stock_identity_key": f"stock:SH:{code}",
        "asof_date": TRADE_DATE,
        "source_trade_date": TRADE_DATE,
        "announcement_date": "20260430",
        "report_period": "20260331",
        "ts_code": f"{code}.SH",
        "code": code,
        "exchange": "SH",
        "roe": 5.0,
        "revenue_yoy": 3.0,
        "profit_yoy": 2.0,
        "total_revenue": 1000.0,
        "net_profit": 100.0,
        "net_assets": 2000.0,
        "eps": 0.1,
        "bps": 2.0,
        "pe_core": 11.0,
        "total_mv": 1200000.0,
        "circ_mv": 900000.0,
        "score": 1,
        "warning": None,
        "quality_status": "passed",
        "source": "mock.financial_asof",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSIONS["stock_financial"],
        "raw_payload": {"mock": True, "i": index},
    }


def index_membership_row(index: int) -> dict:
    code = f"{index % 90 + 1:06d}"
    stock_code = f"{500000 + index:06d}"
    return {
        "trade_date": TRADE_DATE,
        "index_identity_key": f"index:SH:{code}",
        "stock_identity_key": f"stock:SH:{stock_code}",
        "index_code": code,
        "index_name": f"index-{code}",
        "stock_code": stock_code,
        "stock_name": f"stock-{stock_code}",
        "source": "mock.tdx.index",
        "source_file": "指数板块.txt",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSIONS["index_membership"],
        "raw_payload": {"mock": True, "i": index},
    }


def board_membership_row(index: int) -> dict:
    code = f"881{index % 428 + 1:03d}"
    stock_code = f"{500000 + index:06d}"
    return {
        "trade_date": TRADE_DATE,
        "board_identity_key": f"board:TDX:{code}",
        "stock_identity_key": f"stock:SH:{stock_code}",
        "board_code": code,
        "board_name": f"board-{code}",
        "board_type": "tdx_industry",
        "stock_code": stock_code,
        "stock_name": f"stock-{stock_code}",
        "source": "mock.tdx.board",
        "source_file": "行业板块.txt",
        "source_batch_id": BATCH_ID,
        "source_version": SOURCE_VERSIONS["board_membership"],
        "raw_payload": {"mock": True, "i": index},
    }


def valid_source_bundle() -> dict:
    return {
        "stock_daily_basic": [stock_daily_basic_row(i) for i in range(EXPECTED_REFERENCE_ROWS["stock_daily_basic"])],
        "stock_financial": [stock_financial_row(i) for i in range(EXPECTED_REFERENCE_ROWS["stock_financial"])],
        "index_membership": [index_membership_row(i) for i in range(EXPECTED_REFERENCE_ROWS["index_membership"])],
        "board_membership": [board_membership_row(i) for i in range(EXPECTED_REFERENCE_ROWS["board_membership"])],
        "manifests": {
            "condition_source_gap_manifest": [
                {"identity_key": identity_key, "severity": "P1", "action": "exclude_from_condition_universe"}
                for identity_key in CONDITION_SOURCE_GAP_IDENTITIES
            ],
            "board_unmapped_raw_count": 10,
            "board_unmapped_unique_identity_count": 7,
        },
    }


class FakeSourceBuilder:
    def __init__(self, bundle: dict | None = None) -> None:
        self.bundle = bundle or valid_source_bundle()
        self.called = False

    def build_source_bundle(self, *, dsn: str, trade_date: str, snapshot: dict) -> dict:
        self.called = True
        return self.bundle


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.executemany_calls: list[tuple[str, int]] = []

    def execute(self, sql: str, params=None) -> None:
        self.statements.append(" ".join(sql.split()))

    def executemany(self, sql: str, params_seq) -> None:
        rows = list(params_seq)
        self.statements.append(" ".join(sql.split()))
        self.executemany_calls.append((" ".join(sql.split()), len(rows)))


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_obj = RecordingCursor()
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> RecordingCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class RunnerHarness:
    def __init__(self, *, snapshot: dict | None = None, bundle: dict | None = None) -> None:
        self.snapshot = snapshot or sample_pass_snapshot()
        self.builder = FakeSourceBuilder(bundle)
        self.conn = RecordingConnection()
        self.calls: list[str] = []

    def deps(self) -> dict:
        return {
            "build_snapshot_from_db": self.build_snapshot_from_db,
            "source_builder_factory": self.source_builder_factory,
            "connect": self.connect,
            "write_preflight_files": self.write_preflight_files,
            "write_contract_files": self.write_contract_files,
        }

    def build_snapshot_from_db(self, **kwargs) -> dict:
        self.calls.append("build_snapshot_from_db")
        return self.snapshot

    def source_builder_factory(self, **kwargs) -> FakeSourceBuilder:
        self.calls.append("source_builder_factory")
        return self.builder

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append("connect")
        return self.conn

    def write_preflight_files(self, *args, **kwargs) -> None:
        self.calls.append("write_preflight_files")

    def write_contract_files(self, *args, **kwargs) -> None:
        self.calls.append("write_contract_files")


class ConditionSourceActivation20260526V2ExecuteTests(unittest.TestCase):
    def test_missing_required_flags_block(self) -> None:
        cases = [
            (False, True, True, "--execute"),
            (True, False, True, "--user-confirmed"),
            (True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ConditionSourceActivation20260526V2Blocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        postgres_commit_enabled=commit,
                    )

    def test_existing_target_rows_block(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["current_target_fact_rows"]["stock_daily_basic"] = 1

        report = build_execute_preflight_report(
            snapshot,
            execute_requested=False,
            user_confirmed=False,
            postgres_commit_enabled=False,
        )

        self.assertEqual(report["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("target_fact_already_exists", report["blockers"])

    def test_existing_active_source_version_blocks(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["active_target_source_versions"] = [{"data_type": "stock_daily_basic", "scope_key": TRADE_DATE}]

        report = build_execute_preflight_report(
            snapshot,
            execute_requested=False,
            user_confirmed=False,
            postgres_commit_enabled=False,
        )

        self.assertEqual(report["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("active_source_version_conflict", report["blockers"])

    def test_count_mismatch_blocks_validation(self) -> None:
        bundle = valid_source_bundle()
        bundle["stock_daily_basic"] = bundle["stock_daily_basic"][:-1]

        validation = validate_source_bundle(bundle=bundle, snapshot=sample_pass_snapshot())

        self.assertEqual(validation["result"], "VALIDATION_BLOCKED")
        self.assertIn("stock_daily_basic_row_count_mismatch", validation["blockers"])

    def test_condition_gap_rows_inserted_blocks_validation(self) -> None:
        bundle = valid_source_bundle()
        gap_identity = CONDITION_SOURCE_GAP_IDENTITIES[0]
        leaked_basic = dict(bundle["stock_daily_basic"][0], stock_identity_key=gap_identity)
        leaked_financial = dict(bundle["stock_financial"][0], stock_identity_key=gap_identity)
        bundle["stock_daily_basic"][0] = leaked_basic
        bundle["stock_financial"][0] = leaked_financial

        validation = validate_source_bundle(bundle=bundle, snapshot=sample_pass_snapshot())

        self.assertEqual(validation["result"], "VALIDATION_BLOCKED")
        self.assertIn("condition_source_gap_leaked_into_stock_condition_source", validation["blockers"])

    def test_success_commit_plan_has_expected_counts_and_manifest_quality(self) -> None:
        bundle = valid_source_bundle()
        validation = validate_source_bundle(bundle=bundle, snapshot=sample_pass_snapshot())
        plan = build_commit_plan(bundle=bundle, validation_report=validation, baseline=sample_pass_snapshot())

        self.assertEqual(validation["result"], "VALIDATION_PASS")
        self.assertEqual(validation["quality"], {"p0_count": 0, "p1_count": 1, "p2_count": 1})
        self.assertEqual(
            plan["row_counts"],
            {
                "stock_daily_basic": 5504,
                "stock_financial": 5504,
                "index_membership": 12841,
                "board_membership": 56872,
                "total": 80721,
            },
        )
        manifest_items = [
            item
            for item in validation["quality_items"]
            if item["gate_name"] == "condition_source_gap_manifest"
        ]
        self.assertEqual(len(manifest_items), 1)
        self.assertEqual(len(manifest_items[0]["details"]["manifest"]), 16)

    def test_commit_writes_allowed_tables_only(self) -> None:
        bundle = valid_source_bundle()
        validation = validate_source_bundle(bundle=bundle, snapshot=sample_pass_snapshot())
        plan = build_commit_plan(bundle=bundle, validation_report=validation, baseline=sample_pass_snapshot())
        conn = RecordingConnection()

        result = execute_commit_transaction(
            conn,
            commit_plan=plan,
            execute_requested=True,
            user_confirmed=True,
            postgres_commit_enabled=True,
        )

        self.assertTrue(result["committed"])
        self.assertTrue(conn.committed)
        self.assertEqual(tuple(result["written_tables"]), ALLOWED_FUTURE_WRITE_TABLES)
        joined = "\n".join(conn.cursor_obj.statements).lower()
        for forbidden in (
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "parquet",
        ):
            self.assertNotIn(forbidden, joined)

    def test_commit_preconditions_block_p0_validation(self) -> None:
        validation = {"p0_count": 1, "blockers": ["stock_daily_basic_row_count_mismatch"]}
        with self.assertRaisesRegex(ConditionSourceActivation20260526V2Blocked, "stock_daily_basic_row_count_mismatch"):
            validate_commit_preconditions(
                snapshot=sample_pass_snapshot(),
                validation_report=validation,
                postgres_commit_enabled=True,
            )

    def test_rollback_sql_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "sql" / "N1_condition_source_20260526_v2_activation_rollback.sql").exists())

    def test_json_sanitize_replaces_nan_and_nested_nonfinite_with_null(self) -> None:
        payload = {
            "nan": math.nan,
            "pos_inf": math.inf,
            "neg_inf": -math.inf,
            "nested": [{"numpy_nan": np.nan, "ok": 3.5}],
        }

        sanitized = sanitize_json_value(payload)

        self.assertIsNone(sanitized["nan"])
        self.assertIsNone(sanitized["pos_inf"])
        self.assertIsNone(sanitized["neg_inf"])
        self.assertIsNone(sanitized["nested"][0]["numpy_nan"])
        self.assertEqual(sanitized["nested"][0]["ok"], 3.5)
        json.dumps(sanitized, allow_nan=False)

    def test_json_sanitize_replaces_pandas_missing_values_with_null(self) -> None:
        payload = {
            "pd_na": pd.NA,
            "pd_nat": pd.NaT,
            "timestamp": pd.Timestamp("2026-05-26 15:00:00"),
        }

        sanitized = sanitize_json_value(payload)

        self.assertIsNone(sanitized["pd_na"])
        self.assertIsNone(sanitized["pd_nat"])
        self.assertEqual(sanitized["timestamp"], "2026-05-26T15:00:00")
        json.dumps(sanitized, allow_nan=False)

    def test_json_sanitize_converts_decimal_and_nested_decimal_to_float(self) -> None:
        payload = {"decimal": Decimal("12.34"), "nested": [{"decimal": Decimal("0.56")}]}

        sanitized = sanitize_json_value(payload)

        self.assertEqual(sanitized, {"decimal": 12.34, "nested": [{"decimal": 0.56}]})
        json.dumps(sanitized, allow_nan=False)

    def test_json_sanitize_converts_date_datetime_time_to_iso_strings(self) -> None:
        payload = {
            "date": date(2026, 5, 26),
            "datetime": datetime(2026, 5, 26, 15, 0, 1),
            "time": time(9, 30, 5),
        }

        sanitized = sanitize_json_value(payload)

        self.assertEqual(sanitized["date"], "2026-05-26")
        self.assertEqual(sanitized["datetime"], "2026-05-26T15:00:01")
        self.assertEqual(sanitized["time"], "09:30:05")
        json.dumps(sanitized, allow_nan=False)

    def test_json_sanitize_converts_bytes_to_text_or_base64(self) -> None:
        payload = {"utf8": b"hello", "binary": b"\xff\xfe"}

        sanitized = sanitize_json_value(payload)

        self.assertEqual(sanitized["utf8"], "hello")
        self.assertEqual(sanitized["binary"], "//4=")
        json.dumps(sanitized, allow_nan=False)

    def test_json_sanitize_converts_numpy_scalars_to_python_scalars(self) -> None:
        payload = {
            "int": np.int64(7),
            "float": np.float64(1.25),
            "bool": np.bool_(True),
        }

        sanitized = sanitize_json_value(payload)

        self.assertEqual(sanitized, {"int": 7, "float": 1.25, "bool": True})
        self.assertIs(type(sanitized["int"]), int)
        self.assertIs(type(sanitized["float"]), float)
        self.assertIs(type(sanitized["bool"]), bool)
        json.dumps(sanitized, allow_nan=False)

    def test_json_sanitize_converts_set_and_tuple_to_lists(self) -> None:
        payload = {"tuple": (1, 2), "set": {"a", "b"}}

        sanitized = sanitize_json_value(payload)

        self.assertEqual(sanitized["tuple"], [1, 2])
        self.assertEqual(sorted(sanitized["set"]), ["a", "b"])
        json.dumps(sanitized, allow_nan=False)

    def test_json_sanitize_converts_unknown_object_to_string_with_warning(self) -> None:
        class UnknownPayload:
            def __str__(self) -> str:
                return "unknown-payload"

        warnings: list[str] = []
        sanitized = sanitize_json_value({"obj": UnknownPayload()}, warnings=warnings)

        self.assertEqual(sanitized["obj"], "unknown-payload")
        self.assertTrue(warnings)
        self.assertIn("unknown object converted to string", warnings[0])
        json.dumps(sanitized, allow_nan=False)

    def test_json_sanitize_preserves_normal_json_scalars(self) -> None:
        payload = {"number": 1.25, "text": "ok", "flag": True, "none": None}

        self.assertEqual(sanitize_json_value(payload), payload)
        assert_json_compatible(sanitize_json_value(payload), context="test.payload")

    def test_jsonb_row_sanitizes_payloads_without_touching_business_numeric_columns(self) -> None:
        row = stock_daily_basic_row(0)
        row["pe"] = math.nan
        row["raw_payload"] = {
            "pe": math.nan,
            "items": [1, math.inf, {"pd_na": pd.NA, "plain": "value"}],
        }

        converted = jsonb_row(row)
        payload = converted["raw_payload"].obj

        self.assertTrue(math.isnan(converted["pe"]))
        self.assertIsNone(payload["pe"])
        self.assertIsNone(payload["items"][1])
        self.assertIsNone(payload["items"][2]["pd_na"])
        self.assertEqual(payload["items"][2]["plain"], "value")
        json.dumps(payload, allow_nan=False)

    def test_validate_source_bundle_checks_sanitized_json_payloads_before_commit(self) -> None:
        bundle = valid_source_bundle()
        bundle["stock_daily_basic"][0]["raw_payload"] = {
            "bad": math.nan,
            "nested": [math.inf, -math.inf, Decimal("1.5")],
            "binary": b"\xff\xfe",
        }
        bundle["manifests"]["condition_source_gap_manifest"][0]["evidence"] = {"pd_na": pd.NA}

        validation = validate_source_bundle(bundle=bundle, snapshot=sample_pass_snapshot())

        self.assertEqual(validation["result"], "VALIDATION_PASS")
        json_quality = [item for item in validation["quality_items"] if item["gate_name"] == "json_payload_sanitized"]
        self.assertEqual(len(json_quality), 1)
        self.assertEqual(json_quality[0]["status"], "passed")
        plan = build_commit_plan(bundle=bundle, validation_report=validation, baseline=sample_pass_snapshot())
        basic_row = jsonb_row(plan["rows"]["stock_daily_basic"][0])
        quality_row = jsonb_row(
            next(item for item in plan["quality_rows"] if item["gate_name"] == "condition_source_gap_manifest")
        )
        json.dumps(basic_row["raw_payload"].obj, allow_nan=False)
        json.dumps(quality_row["details"].obj, allow_nan=False)

    def test_cli_all_flags_reaches_execute_path_with_mocked_builder_and_commit(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = runner.main(
                ["--execute", "--user-confirmed", "--postgres-commit-enabled", "--no-write-report"],
                dependencies=harness.deps(),
            )

        self.assertEqual(result, 0, stderr.getvalue())
        self.assertTrue(harness.builder.called)
        self.assertTrue(harness.conn.committed)
        self.assertIn("connect", harness.calls)

    def test_cli_missing_flag_blocks_before_source_build(self) -> None:
        runner = load_runner_module()
        harness = RunnerHarness()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = runner.main(
                ["--execute", "--user-confirmed", "--no-write-report"],
                dependencies=harness.deps(),
            )

        self.assertNotEqual(result, 0)
        self.assertFalse(harness.builder.called)
        self.assertFalse(harness.conn.committed)


if __name__ == "__main__":
    unittest.main()
