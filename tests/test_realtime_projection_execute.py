import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from ashare_v3.market.b2_projection_proof import build_b2_30m_projection_proof_fields
from ashare_v3.market.realtime_projection_execute import (
    ALLOWED_WRITE_TABLES,
    ALLOWED_QUALITY_DATA_DOMAINS,
    B2_QUALITY_LAYER_SCOPE,
    FORBIDDEN_WRITE_TABLES,
    PROJECTION_METRIC_SCOPE,
    RealtimeProjectionExecuteError,
    b2_30m_projection_adapter_contract,
    build_projection_rows,
    build_projection_row,
    build_projection_quality_items,
    build_projection_rollback_sql,
    build_projection_time_alignment_evidence,
    ensure_clean_projection_target,
    ensure_projection_execute_contract,
    ensure_source_runs_passed,
    resolve_source_run_ids,
    run_realtime_projection_metric_execute,
    summarize_projection_rows,
    validate_projection_rows_against_contract,
)


PROJECTION_RUN_ID = (
    "realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
SHANGHAI = ZoneInfo("Asia/Shanghai")


class RealtimeProjectionExecuteTest(unittest.TestCase):
    def test_execute_requires_double_confirmation(self) -> None:
        with self.assertRaisesRegex(RealtimeProjectionExecuteError, "--execute"):
            ensure_projection_execute_contract(
                sample_contract(),
                sample_preflight(result="PREFLIGHT_PASS"),
                execute=False,
                user_confirmed=True,
                projection_run_id=PROJECTION_RUN_ID,
                for_trade_date="20260525",
            )

        with self.assertRaisesRegex(RealtimeProjectionExecuteError, "--user-confirmed"):
            ensure_projection_execute_contract(
                sample_contract(),
                sample_preflight(result="PREFLIGHT_PASS"),
                execute=True,
                user_confirmed=False,
                projection_run_id=PROJECTION_RUN_ID,
                for_trade_date="20260525",
            )

    def test_projection_run_id_mismatch_blocks(self) -> None:
        with self.assertRaisesRegex(RealtimeProjectionExecuteError, "projection_run_id"):
            ensure_projection_execute_contract(
                sample_contract(),
                sample_preflight(result="PREFLIGHT_PASS"),
                execute=True,
                user_confirmed=True,
                projection_run_id="wrong_run_id",
                for_trade_date="20260525",
            )

    def test_preflight_must_pass_before_execute(self) -> None:
        with self.assertRaisesRegex(RealtimeProjectionExecuteError, "preflight"):
            ensure_projection_execute_contract(
                sample_contract(),
                sample_preflight(result="PREFLIGHT_BLOCKED"),
                execute=True,
                user_confirmed=True,
                projection_run_id=PROJECTION_RUN_ID,
                for_trade_date="20260525",
            )

    def test_source_run_not_passed_blocks(self) -> None:
        preflight = sample_preflight(result="PREFLIGHT_PASS")
        preflight["lineage_checks"][1]["passed"] = False

        with self.assertRaisesRegex(RealtimeProjectionExecuteError, "lineage"):
            ensure_projection_execute_contract(
                sample_contract(),
                preflight,
                execute=True,
                user_confirmed=True,
                projection_run_id=PROJECTION_RUN_ID,
                for_trade_date="20260525",
            )

    def test_direct_30m_k_source_runs_do_not_require_snapshot_run(self) -> None:
        contract = sample_contract()
        contract["source_mode"] = "direct_30m_k"
        contract["source_runs"] = {
            "source_condition_run_id": "condition_layer",
            "subscription_run_id": "subscription",
            "source_30m_k_run_id": "direct_30m_k_source",
            "preload_run_id": "preload",
        }
        snapshot = {
            "source_run_rows": {
                "subscription": {"status": "passed", "market_data_fact_written": False},
                "preload": {"status": "passed", "market_data_fact_written": True},
                "direct_30m_k_source": {"status": "passed", "market_data_fact_written": True},
            }
        }

        ensure_source_runs_passed(snapshot, contract)

    def test_projection_run_existing_state_blocks(self) -> None:
        snapshot = sample_clean_snapshot()
        snapshot["projection_run_exists"] = True

        with self.assertRaisesRegex(RealtimeProjectionExecuteError, "already exists"):
            ensure_clean_projection_target(snapshot, PROJECTION_RUN_ID)

    def test_outbox_scoped_by_projection_run_blocks(self) -> None:
        snapshot = sample_clean_snapshot()
        snapshot["outbox_rows_for_projection_run"] = 1

        with self.assertRaisesRegex(RealtimeProjectionExecuteError, "outbox"):
            ensure_clean_projection_target(snapshot, PROJECTION_RUN_ID)

    def test_checkpoint_scoped_by_projection_run_blocks(self) -> None:
        snapshot = sample_clean_snapshot()
        snapshot["checkpoint_refs_for_projection_run"] = 1

        with self.assertRaisesRegex(RealtimeProjectionExecuteError, "checkpoint"):
            ensure_clean_projection_target(snapshot, PROJECTION_RUN_ID)

    def test_writes_outbox_false_is_enforced(self) -> None:
        contract = sample_contract()
        contract["writes_outbox"] = True

        with self.assertRaisesRegex(RealtimeProjectionExecuteError, "writes_outbox=false"):
            ensure_projection_execute_contract(
                contract,
                sample_preflight(result="PREFLIGHT_PASS"),
                execute=True,
                user_confirmed=True,
                projection_run_id=PROJECTION_RUN_ID,
                for_trade_date="20260525",
            )

    def test_forbidden_tables_do_not_overlap_allowed_write_scope(self) -> None:
        self.assertFalse(set(ALLOWED_WRITE_TABLES) & set(FORBIDDEN_WRITE_TABLES))
        self.assertIn("common_event_outbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("common_event_inbox", FORBIDDEN_WRITE_TABLES)
        self.assertIn("stock_realtime_projection_metric", ALLOWED_WRITE_TABLES)

    def test_b2_30m_projection_adapter_contract_routes_asset_kind(self) -> None:
        self.assertEqual(
            b2_30m_projection_adapter_contract("stock"),
            {"frequency": "30m", "adapter_frequency": 2, "adapter_method": "bars"},
        )
        self.assertEqual(
            b2_30m_projection_adapter_contract("index"),
            {"frequency": "30m", "adapter_frequency": 2, "adapter_method": "index"},
        )
        self.assertEqual(
            b2_30m_projection_adapter_contract("board"),
            {"frequency": "30m", "adapter_frequency": 2, "adapter_method": "index"},
        )

    def test_direct_30m_k_source_returned_time_maps_open_row_to_projected_window(self) -> None:
        fields = build_b2_30m_projection_proof_fields(
            asset_kind="index",
            projection_run_id="realtime_projection_metric_20260629_until_0920",
            projection_signal_status="up_volume_expanding",
            source_mode="direct_30m_k",
            for_trade_date="20260629",
            source_30m_k_run_id="source_30m_k_20260629",
            source_30m_k_bar_id=123,
            source_30m_k_time="2026-06-29T09:31:00+08:00",
            source_30m_k_adapter_method="index",
        )

        self.assertEqual(fields["source_time_policy"], "source_returned_time")
        self.assertEqual(fields["projection_mode"], "realtime_virtual_30m")
        self.assertEqual(fields["source_30m_k_window_start"], "2026-06-29T09:30:00+08:00")
        self.assertEqual(fields["source_30m_k_window_end"], "2026-06-29T10:00:00+08:00")
        self.assertEqual(fields["source_30m_k_closed_status"], "projected")

    def test_direct_30m_k_source_returned_time_rejects_fake_source_marker(self) -> None:
        with self.assertRaisesRegex(ValueError, "fake_source_time_forbidden"):
            build_b2_30m_projection_proof_fields(
                asset_kind="board",
                projection_run_id="realtime_projection_metric_20260629_until_0920",
                projection_signal_status="up_volume_expanding",
                source_mode="direct_30m_k",
                for_trade_date="20260629",
                source_30m_k_run_id="source_30m_k_20260629",
                source_30m_k_bar_id=123,
                source_30m_k_time="2026-06-29T09:31:00+08:00",
                source_30m_k_adapter_method="index",
                source_30m_k_source_marker="fake",
            )

    def test_direct_30m_k_source_returned_time_rejects_outside_trading_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_time_outside_30m_window"):
            build_b2_30m_projection_proof_fields(
                asset_kind="index",
                projection_run_id="realtime_projection_metric_20260629_until_0920",
                projection_signal_status="up_volume_expanding",
                source_mode="direct_30m_k",
                for_trade_date="20260629",
                source_30m_k_run_id="source_30m_k_20260629",
                source_30m_k_bar_id=123,
                source_30m_k_time="2026-06-29T12:00:00+08:00",
                source_30m_k_adapter_method="index",
            )

    def test_direct_30m_k_source_returned_time_rejects_trade_date_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_time_date_mismatch"):
            build_b2_30m_projection_proof_fields(
                asset_kind="index",
                projection_run_id="realtime_projection_metric_20260629_until_0920",
                projection_signal_status="up_volume_expanding",
                source_mode="direct_30m_k",
                for_trade_date="20260629",
                source_30m_k_run_id="source_30m_k_20260629",
                source_30m_k_bar_id=123,
                source_30m_k_time="2026-06-26T09:31:00+08:00",
                source_30m_k_adapter_method="index",
            )

    def test_direct_30m_k_materializes_from_injected_rows_without_b1(self) -> None:
        contract = sample_contract()
        contract["projection_run_id"] = "realtime_projection_metric_20260629_until_0920__b2_30m_projection_proof_v1"
        contract["source_mode"] = "direct_30m_k"
        contract["dates"] = {"for_trade_date": "20260629", "prev_trade_date": "20260626"}
        contract["source_runs"] = {
            "source_condition_run_id": "condition_layer",
            "subscription_run_id": "subscription",
            "preload_run_id": "preload",
            "source_30m_k_run_id": "direct_30m_k_source_20260629_until_0920",
        }
        contract["source_30m_k_rows"] = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "exchange": "SH",
                "code": "600000",
                "display_code": "600000",
                "name": "sample",
                "source_30m_k_bar_id": 9001,
                "source_30m_k_time": "2026-06-29T09:31:00+08:00",
                "source_30m_k_adapter_method": "bars",
                "projection_status": "ready",
                "projection_signal_status": "up_volume_expanding",
            }
        ]

        rows = build_projection_rows(dsn="postgresql://must-not-connect", contract=contract)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["projection_run_id"], contract["projection_run_id"])
        self.assertIsNone(row["source_snapshot_run_id"])
        self.assertEqual(row["source_fact_ids"]["source_mode"], "direct_30m_k")
        self.assertEqual(row["source_fact_ids"]["source_time_policy"], "source_returned_time")
        self.assertEqual(row["source_fact_ids"]["source_30m_k_adapter_method"], "bars")
        self.assertEqual(row["source_fact_ids"]["source_30m_k_window_start"], "2026-06-29T09:30:00+08:00")
        self.assertEqual(row["source_fact_ids"]["source_30m_k_closed_status"], "projected")
        self.assertTrue(row["source_fact_ids"]["not_n5_final_proof"])

    def test_direct_30m_k_missing_materialized_rows_blocks(self) -> None:
        contract = sample_contract()
        contract["source_mode"] = "direct_30m_k"
        contract["dates"] = {"for_trade_date": "20260629", "prev_trade_date": "20260626"}
        contract["source_runs"] = {
            "source_condition_run_id": "condition_layer",
            "subscription_run_id": "subscription",
            "preload_run_id": "preload",
            "source_30m_k_run_id": "direct_30m_k_source_20260629_until_0920",
        }

        with self.assertRaisesRegex(RealtimeProjectionExecuteError, "BLOCKED_DIRECT_30M_K_ROWS_MISSING"):
            build_projection_rows(dsn="postgresql://must-not-connect", contract=contract)

    def test_board_and_bj_not_ready_are_preserved_in_summary(self) -> None:
        rows = [
            projection_row("stock", "stock:SH:600000", "ready", "up_volume_expanding"),
            projection_row("index", "index:SH:000905", "ready", "flat"),
            projection_row("board", "board:TDX:881002", "not_ready", "unknown"),
            projection_row("stock", "stock:BJ:920045", "not_ready", "unknown"),
        ]

        summary = summarize_projection_rows(rows)

        self.assertEqual(summary["projection_status"], {"ready": 2, "not_ready": 2})
        self.assertEqual(summary["ready_by_asset"], {"stock": 1, "index": 1})
        self.assertEqual(summary["not_ready_by_asset"], {"board": 1, "stock": 1})
        self.assertEqual(summary["board_not_ready"], 1)
        self.assertEqual(summary["bj_920xxx_not_ready"], 1)

    def test_projection_validation_uses_contract_not_ready_visibility_counts(self) -> None:
        rows = [
            projection_row("stock", "stock:SH:600000", "not_ready", "unknown"),
            projection_row("index", "index:SH:000905", "not_ready", "unknown"),
            projection_row("board", "board:TDX:881002", "not_ready", "unknown"),
            projection_row("board", "board:TDX:881003", "not_ready", "unknown"),
        ]
        contract = sample_contract()
        contract["expected_projection_rows"] = {"stock": 1, "index": 1, "board": 2, "total": 4}
        contract["expected_distribution"] = {
            "ready_rows": 0,
            "ready_by_asset": {},
            "not_ready_rows": 4,
            "not_ready_by_asset": {"stock": 1, "index": 1, "board": 2},
            "projection_signal_status": {"unknown": 4},
            "board_not_ready": 2,
            "bj_920xxx_not_ready": 0,
        }

        validate_projection_rows_against_contract(rows, contract)

    def test_projection_validation_accepts_nested_rows_by_asset_contract(self) -> None:
        rows = [
            projection_row("stock", "stock:SH:600000", "ready", "up_volume_expanding"),
            projection_row("index", "index:SH:000905", "not_ready", "unknown"),
            projection_row("board", "board:TDX:881002", "not_ready", "unknown"),
        ]
        contract = sample_contract()
        contract["expected_projection_rows"] = {
            "total": 3,
            "by_asset": {"stock": 1, "index": 1, "board": 1},
        }
        contract["expected_distribution"] = {
            "ready_rows": 1,
            "ready_by_asset": {"stock": 1},
            "not_ready_rows": 2,
            "not_ready_by_asset": {"index": 1, "board": 1},
            "projection_signal_status": {"up_volume_expanding": 1, "unknown": 2},
            "board_not_ready": 1,
            "bj_920xxx_not_ready": 0,
        }

        validate_projection_rows_against_contract(rows, contract)

    def test_dynamic_child_contract_derives_expected_distribution_from_projection_rows(self) -> None:
        rows = [
            projection_row("stock", "stock:SH:600000", "ready", "up_volume_expanding"),
            projection_row("index", "index:SH:000905", "not_ready", "unknown"),
            projection_row("board", "board:TDX:881002", "not_ready", "unknown"),
            projection_row("stock", "stock:BJ:920045", "not_ready", "unknown"),
        ]
        contract = sample_contract()
        contract["artifact_generation_mode"] = "dynamic_intraday_child_artifact"
        contract["expected_projection_rows"] = {"stock": 2, "index": 1, "board": 1, "total": 4}
        contract["expected_distribution"] = {
            "ready_rows": None,
            "ready_by_asset": {},
            "not_ready_rows": None,
            "not_ready_by_asset": {},
            "projection_signal_status": {},
            "projection_quality_status": {},
            "trace_status": {},
            "board_not_ready": None,
            "bj_920xxx_not_ready": None,
        }
        contract["expected_distribution_policy"] = {
            "mode": "derive_from_projection_rows",
            "applies_to_artifact_generation_mode": "dynamic_intraday_child_artifact",
        }

        validate_projection_rows_against_contract(rows, contract)

        self.assertEqual(contract["expected_distribution"]["ready_rows"], 1)
        self.assertEqual(contract["expected_distribution"]["not_ready_rows"], 3)
        self.assertEqual(contract["expected_distribution"]["ready_by_asset"], {"stock": 1})
        self.assertEqual(contract["expected_distribution"]["not_ready_by_asset"], {"board": 1, "index": 1, "stock": 1})
        self.assertEqual(
            contract["expected_distribution"]["projection_signal_status"],
            {"unknown": 3, "up_volume_expanding": 1},
        )
        self.assertEqual(contract["expected_distribution"]["board_not_ready"], 1)
        self.assertEqual(contract["expected_distribution"]["bj_920xxx_not_ready"], 1)

    def test_fact_only_snapshot_trace_policy_allows_missing_snapshot_event_id(self) -> None:
        contract = sample_contract()
        contract["source_runs"] = {
            "snapshot_run_id": "realtime_snapshot_fact_only",
            "today_minute_run_id": "today_minute",
            "preload_run_id": "preload",
        }
        contract["calculation_config"] = sample_calculation_config()
        contract["fact_only_snapshot_trace_policy"] = {
            "allow_missing_snapshot_event_id": True,
            "required_trace_fields": ["snapshot_id", "subscription_id", "pull_plan_id", "source_adapter"],
        }
        row = build_projection_row(
            asset_kind="stock",
            snapshot=sample_snapshot(),
            event=None,
            pull_plan_id=42,
            today_bars=sample_current_bars(),
            previous_bars=sample_previous_bars(),
            latest_closed_minute=datetime(2026, 6, 5, 11, 5, tzinfo=SHANGHAI),
            contract=contract,
            source_condition_run_id="condition_layer",
            projection_run_id=PROJECTION_RUN_ID,
            for_trade_date="20260605",
            prev_trade_date="20260604",
            calculation_config=sample_calculation_config(),
        )

        missing_reasons = row["source_fact_ids"]["missing_reason"]
        self.assertNotIn("mandatory_trace_field_missing", missing_reasons)
        self.assertEqual(row["snapshot_event_id"], "")
        self.assertTrue(row["raw_json"]["fact_only_snapshot_trace_compatible"])

    def test_live_current_1m_projection_row_does_not_require_c1_source_run(self) -> None:
        contract = sample_contract()
        contract["source_mode"] = "live_current_1m"
        contract["source_runs"] = {
            "snapshot_run_id": "realtime_snapshot_live",
            "source_live_minute_run_id": "live_current_1m_source_20260605_until_1105__subscription",
            "preload_run_id": "preload",
        }
        contract["calculation_config"] = sample_calculation_config()
        contract["fact_only_snapshot_trace_policy"] = {
            "allow_missing_snapshot_event_id": True,
            "required_trace_fields": ["snapshot_id", "subscription_id", "pull_plan_id", "source_adapter"],
        }

        row = build_projection_row(
            asset_kind="stock",
            snapshot=sample_snapshot(),
            event=None,
            pull_plan_id=42,
            today_bars=sample_current_bars(),
            previous_bars=sample_previous_bars(),
            latest_closed_minute=datetime(2026, 6, 5, 11, 5, tzinfo=SHANGHAI),
            contract=contract,
            source_condition_run_id="condition_layer",
            projection_run_id=PROJECTION_RUN_ID,
            for_trade_date="20260605",
            prev_trade_date="20260604",
            calculation_config=sample_calculation_config(),
        )

        self.assertEqual(row["projection_status"], "ready")
        self.assertEqual(row["source_fact_kind"], "mixed")
        self.assertEqual(row["source_fact_ids"]["canonical_source_fact_kind"], "live_current_1m")
        self.assertEqual(row["source_fact_ids"]["source_mode"], "live_current_1m")
        self.assertEqual(
            row["source_fact_ids"]["source_live_minute_run_id"],
            "live_current_1m_source_20260605_until_1105__subscription",
        )
        self.assertFalse(row["source_fact_ids"]["c1_dependency"])
        self.assertFalse(row["source_fact_ids"]["is_closed_1m"])
        self.assertTrue(row["source_fact_ids"]["no_c1_table_rows_read"])
        self.assertTrue(row["source_fact_ids"]["no_c1_table_rows_written"])
        self.assertFalse(row["raw_json"]["c1_dependency"])
        self.assertFalse(row["raw_json"]["is_closed_1m"])
        self.assertTrue(row["raw_json"]["no_c1_table_rows_read"])
        self.assertTrue(row["raw_json"]["no_c1_table_rows_written"])
        self.assertEqual(row["raw_json"]["canonical_source_fact_kind"], "live_current_1m")
        self.assertFalse(row["raw_json"]["closed_minute_confirmed_for_actionexecuted"])
        self.assertFalse(row["raw_json"]["n5_actionexecuted_confirmation_required"])
        self.assertEqual(row["raw_json"]["metric_role"], "projection_trigger_proof")
        self.assertEqual(row["raw_json"]["proof_owner"], "N3")
        self.assertEqual(row["raw_json"]["proof_consumer"], "N4")
        self.assertEqual(row["raw_json"]["proof_kind"], "n3_b2_30m_projection")
        self.assertTrue(row["raw_json"]["not_n5_final_proof"])
        self.assertEqual(row["raw_json"]["frequency"], "30m")
        self.assertEqual(row["raw_json"]["adapter_method"], "bars")
        self.assertEqual(row["source_fact_ids"]["metric_role"], "projection_trigger_proof")
        self.assertEqual(row["source_fact_ids"]["proof_kind"], "n3_b2_30m_projection")
        self.assertTrue(row["source_fact_ids"]["not_n5_final_proof"])

    def test_live_current_1m_missing_object_is_not_ready_without_fake_target_minute(self) -> None:
        contract = sample_contract()
        contract["source_mode"] = "live_current_1m"
        contract["source_runs"] = {
            "snapshot_run_id": "realtime_snapshot_live",
            "source_live_minute_run_id": "live_current_1m_source_20260605_until_1105__subscription",
            "preload_run_id": "preload",
        }
        contract["calculation_config"] = sample_calculation_config()
        contract["fact_only_snapshot_trace_policy"] = {
            "allow_missing_snapshot_event_id": True,
            "required_trace_fields": ["snapshot_id", "subscription_id", "pull_plan_id", "source_adapter"],
        }

        row = build_projection_row(
            asset_kind="stock",
            snapshot=sample_snapshot(),
            event=None,
            pull_plan_id=42,
            today_bars=[],
            previous_bars=sample_previous_bars(),
            latest_closed_minute=datetime(2026, 6, 5, 11, 5, tzinfo=SHANGHAI),
            contract=contract,
            source_condition_run_id="condition_layer",
            projection_run_id=PROJECTION_RUN_ID,
            for_trade_date="20260605",
            prev_trade_date="20260604",
            calculation_config=sample_calculation_config(),
        )

        self.assertEqual(row["projection_status"], "not_ready")
        self.assertEqual(row["projection_quality_status"], "blocked")
        self.assertEqual(row["trace_status"], "blocked")
        self.assertEqual(row["source_fact_kind"], "mixed")
        self.assertEqual(row["source_fact_ids"]["canonical_source_fact_kind"], "live_current_1m")
        self.assertEqual(row["minute_bar_ids_used"], [])
        self.assertEqual(row["source_fact_ids"]["minute_bar_ids_used"], [])
        self.assertIn("missing_today_minute_elapsed", row["source_fact_ids"]["missing_reason"])
        self.assertIn("amount_projection_ratio_not_computable", row["source_fact_ids"]["missing_reason"])
        self.assertFalse(row["source_fact_ids"]["is_closed_1m"])
        self.assertTrue(row["source_fact_ids"]["no_c1_table_rows_read"])
        self.assertTrue(row["source_fact_ids"]["no_c1_table_rows_written"])
        self.assertFalse(row["raw_json"]["c1_dependency"])
        self.assertEqual(row["raw_json"]["canonical_source_fact_kind"], "live_current_1m")
        self.assertEqual(row["raw_json"]["today_minute_run_id"], "live_current_1m_source_20260605_until_1105__subscription")

    def test_live_current_minute_rows_normalize_mootdx_raw_1300_to_canonical_1130(self) -> None:
        from ashare_v3.market.realtime_projection_execute import live_current_minute_rows_by_identity

        contract = sample_contract()
        contract["source_mode"] = "live_current_1m"
        contract["dates"]["for_trade_date"] = "20260626"
        contract["intraday_trade_date"] = "20260626"
        contract["source_adapter"] = "mootdx"
        contract["live_current_minute_rows"] = {
            "stock": [
                {
                    "bar_id": 1300,
                    "identity_key": "stock:SH:600000",
                    "bar_time": datetime(2026, 6, 26, 13, 0, tzinfo=SHANGHAI),
                    "open": Decimal("10.00"),
                    "high": Decimal("10.10"),
                    "low": Decimal("9.99"),
                    "close": Decimal("10.05"),
                    "volume": Decimal("100"),
                    "amount": Decimal("1000"),
                    "quality_status": "passed",
                    "raw_payload": {},
                }
            ]
        }

        rows_by_identity = live_current_minute_rows_by_identity(contract)
        rows = rows_by_identity[("stock", "stock:SH:600000")]

        self.assertEqual(rows[0]["bar_time"].strftime("%H:%M"), "11:30")
        trace = rows[0]["raw_payload"]
        self.assertEqual(trace["raw_bar_time"], "2026-06-26T13:00:00+08:00")
        self.assertEqual(trace["canonical_bar_time"], "2026-06-26T11:30:00+08:00")
        self.assertEqual(trace["time_label_normalization"], "mootdx_intraday_1300_to_1130")
        self.assertEqual(trace["canonical_minute_policy"], "ashare_cn_1m_v1")
        self.assertNotIn("13:00_label_equivalent_to_missing_11:30_bar", str(rows[0]))

    def test_fact_only_snapshot_trace_policy_still_requires_core_trace_fields(self) -> None:
        contract = sample_contract()
        contract["source_runs"] = {
            "snapshot_run_id": "realtime_snapshot_fact_only",
            "today_minute_run_id": "today_minute",
            "preload_run_id": "preload",
        }
        contract["calculation_config"] = sample_calculation_config()
        contract["fact_only_snapshot_trace_policy"] = {
            "allow_missing_snapshot_event_id": True,
            "required_trace_fields": ["snapshot_id", "subscription_id", "pull_plan_id", "source_adapter"],
        }
        snapshot = sample_snapshot()
        snapshot["snapshot_id"] = None

        row = build_projection_row(
            asset_kind="stock",
            snapshot=snapshot,
            event=None,
            pull_plan_id=42,
            today_bars=sample_current_bars(),
            previous_bars=sample_previous_bars(),
            latest_closed_minute=datetime(2026, 6, 5, 11, 5, tzinfo=SHANGHAI),
            contract=contract,
            source_condition_run_id="condition_layer",
            projection_run_id=PROJECTION_RUN_ID,
            for_trade_date="20260605",
            prev_trade_date="20260604",
            calculation_config=sample_calculation_config(),
        )

        self.assertIn("mandatory_trace_field_missing", row["source_fact_ids"]["missing_reason"])
        self.assertEqual(row["trace_status"], "blocked")

    def test_projection_time_alignment_records_snapshot_after_c1_without_blocking(self) -> None:
        contract = sample_contract()
        contract["projection_time_policy"] = {
            "mode": "fact_only_defer_off_bucket_source_snapshot_time",
            "bucket_time_source": "source_snapshot_time",
            "off_bucket_source_snapshot_time_handling": "NOOP_PASS_NO_WRITE",
            "no_closed_data_forged": True,
            "maps_midday_to_trading_bucket": False,
        }
        evidence = build_projection_time_alignment_evidence(
            contract=contract,
            latest_closed_minute=datetime(2026, 6, 24, 10, 0, tzinfo=SHANGHAI),
            snapshot_rows_by_asset={
                "stock": [
                    {"identity_key": "stock:SH:600000", "snapshot_time": datetime(2026, 6, 24, 10, 3, tzinfo=SHANGHAI)}
                ]
            },
        )

        self.assertFalse(evidence["blocked"])
        self.assertEqual(evidence["reason"], None)
        self.assertEqual(evidence["max_required_closed_label"], "2026-06-24T10:02:00+08:00")
        self.assertEqual(evidence["after_latest_closed_count"], 1)
        self.assertEqual(evidence["after_latest_closed_sample"][0]["identity_key"], "stock:SH:600000")
        self.assertEqual(evidence["n5_actionexecuted_confirmation_required"], True)

    def test_projection_time_alignment_passes_when_c1_covers_snapshot_bucket(self) -> None:
        contract = sample_contract()
        contract["projection_time_policy"] = {
            "mode": "fact_only_defer_off_bucket_source_snapshot_time",
            "bucket_time_source": "source_snapshot_time",
            "off_bucket_source_snapshot_time_handling": "NOOP_PASS_NO_WRITE",
            "no_closed_data_forged": True,
            "maps_midday_to_trading_bucket": False,
        }
        evidence = build_projection_time_alignment_evidence(
            contract=contract,
            latest_closed_minute=datetime(2026, 6, 24, 10, 0, tzinfo=SHANGHAI),
            snapshot_rows_by_asset={
                "stock": [
                    {"identity_key": "stock:SH:600000", "snapshot_time": datetime(2026, 6, 24, 10, 1, tzinfo=SHANGHAI)}
                ]
            },
        )

        self.assertFalse(evidence["blocked"])
        self.assertEqual(evidence["max_required_closed_label"], "2026-06-24T10:00:00+08:00")

    def test_projection_time_alignment_evidence_does_not_block_build_or_write(self) -> None:
        contract = sample_contract()
        contract["dates"] = {
            "for_trade_date": "20260525",
            "source_trade_date": "20260524",
            "prev_trade_date": "20260524",
        }
        contract["source_runs"] = {
            "source_condition_run_id": "condition_layer",
            "subscription_run_id": "subscription",
            "snapshot_run_id": "snapshot",
            "preload_run_id": "preload",
            "today_minute_run_id": "today",
        }
        contract["calculation_config"] = sample_calculation_config()
        pre_backup = sample_clean_snapshot()
        pre_backup["source_run_rows"] = {
            "subscription": {"status": "passed", "market_data_fact_written": False},
            "snapshot": {"status": "passed", "market_data_fact_written": True},
            "preload": {"status": "passed", "market_data_fact_written": True},
            "today": {"status": "passed", "market_data_fact_written": True},
        }
        alignment_evidence = {
            "blocked": False,
            "reason": None,
            "latest_closed_minute": "2026-06-24T10:00:00+08:00",
            "max_required_closed_label": "2026-06-24T10:02:00+08:00",
            "after_latest_closed_count": 1,
            "n5_actionexecuted_confirmation_required": True,
        }
        projection_rows = [
            projection_row("stock", "stock:SH:600000", "ready", "up_volume_expanding"),
            projection_row("index", "index:SH:000905", "ready", "flat"),
            projection_row("board", "board:TDX:881002", "not_ready", "unknown"),
            projection_row("stock", "stock:BJ:920045", "not_ready", "unknown"),
        ]
        write_result = {
            "projection_rows_written": 4,
            "quality_item_rows_written": 1,
            "common_market_data_run_written": 1,
        }

        with tempfile.TemporaryDirectory() as tmp:
            contract_path = Path(tmp) / "contract.json"
            preflight_path = Path(tmp) / "preflight.json"
            dry_run_path = Path(tmp) / "dry_run.json"
            report_path = Path(tmp) / "report.json"
            md_path = Path(tmp) / "report.md"
            rollback_path = Path(tmp) / "rollback.sql"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            preflight_path.write_text(json.dumps(sample_preflight("PREFLIGHT_PASS")), encoding="utf-8")
            dry_run_path.write_text(
                json.dumps({"result": "DRY_RUN_PASS", "projection_run_id_candidate": PROJECTION_RUN_ID}),
                encoding="utf-8",
            )

            with patch(
                "ashare_v3.market.realtime_projection_execute.capture_projection_execute_snapshot",
                return_value=pre_backup,
            ), patch(
                "ashare_v3.market.realtime_projection_execute.detect_projection_time_policy_noop",
                return_value={"should_noop": False},
            ), patch(
                "ashare_v3.market.realtime_projection_execute.detect_projection_time_alignment_blocker",
                return_value=alignment_evidence,
            ), patch(
                "ashare_v3.market.realtime_projection_execute.build_projection_rows",
                return_value=projection_rows,
            ), patch(
                "ashare_v3.market.realtime_projection_execute.write_projection_execute_transaction",
                return_value=write_result,
            ):
                report = run_realtime_projection_metric_execute(
                    dsn="postgresql://example",
                    contract_path=str(contract_path),
                    preflight_path=str(preflight_path),
                    dry_run_path=str(dry_run_path),
                    json_report_path=str(report_path),
                    markdown_report_path=str(md_path),
                    rollback_sql_path=str(rollback_path),
                    projection_run_id=PROJECTION_RUN_ID,
                    for_trade_date="20260525",
                    execute=True,
                    user_confirmed=True,
                )

            self.assertEqual(report["write_result"]["event_outbox_rows_written"], 0)
            self.assertEqual(report["write_result"]["projection_rows_written"], 4)

    def test_standard_outbox_observed_at_policy_uses_latest_closed_minute_bucket(self) -> None:
        contract = sample_contract()
        contract["source_runs"] = {
            "snapshot_run_id": "realtime_snapshot_standard_outbox",
            "today_minute_run_id": "today_minute",
            "preload_run_id": "preload",
        }
        contract["calculation_config"] = sample_calculation_config()
        contract["projection_time_policy"] = {
            "mode": "standard_outbox_observed_at_to_latest_closed_minute",
            "bucket_time_source": "latest_closed_minute",
            "store_snapshot_time": "projection_bucket_time",
            "preserve_source_observed_at_trace": True,
        }
        snapshot = sample_snapshot()
        snapshot["snapshot_time"] = datetime(2026, 6, 11, 15, 34, 16, tzinfo=SHANGHAI)
        event = {
            "event_id": "evt_standard_outbox_1",
            "payload_json": {
                "snapshot_id": 1,
                "pull_plan_id": 42,
                "observed_at": "2026-06-11T15:34:16+08:00",
                "source_time_label_normalized": True,
            },
        }

        row = build_projection_row(
            asset_kind="stock",
            snapshot=snapshot,
            event=event,
            pull_plan_id=42,
            today_bars=projection_policy_current_bars(),
            previous_bars=projection_policy_previous_bars(),
            latest_closed_minute=datetime(2026, 6, 11, 13, 41, tzinfo=SHANGHAI),
            contract=contract,
            source_condition_run_id="condition_layer",
            projection_run_id=PROJECTION_RUN_ID,
            for_trade_date="20260611",
            prev_trade_date="20260610",
            calculation_config=sample_calculation_config(),
        )

        self.assertEqual(row["projection_window_id"], "20260611_1330_1400")
        self.assertEqual(row["source_fact_ids"]["closed_label_used"], "2026-06-11T13:41:00+08:00")
        self.assertEqual(row["snapshot_time"], datetime(2026, 6, 11, 13, 42, tzinfo=SHANGHAI))
        self.assertEqual(row["raw_json"]["projection_time_policy"]["mode"], "standard_outbox_observed_at_to_latest_closed_minute")
        self.assertEqual(row["raw_json"]["source_snapshot_time"], "2026-06-11T15:34:16+08:00")
        self.assertEqual(row["raw_json"]["projection_bucket_closed_label"], "2026-06-11T13:41:00+08:00")
        self.assertEqual(row["snapshot_event_id"], "evt_standard_outbox_1")

    def test_standard_outbox_observed_at_policy_clamps_boundary_closed_minute_to_window_end(self) -> None:
        contract = sample_contract()
        contract["source_runs"] = {
            "snapshot_run_id": "realtime_snapshot_standard_outbox",
            "today_minute_run_id": "today_minute",
            "preload_run_id": "preload",
        }
        contract["calculation_config"] = sample_calculation_config()
        contract["projection_time_policy"] = {
            "mode": "standard_outbox_observed_at_to_latest_closed_minute",
            "bucket_time_source": "latest_closed_minute",
            "store_snapshot_time": "projection_bucket_time",
            "preserve_source_observed_at_trace": True,
        }
        snapshot = sample_snapshot()
        snapshot["snapshot_time"] = datetime(2026, 6, 12, 14, 35, 56, tzinfo=SHANGHAI)
        event = {
            "event_id": "evt_standard_outbox_boundary",
            "payload_json": {"snapshot_id": 1, "pull_plan_id": 42},
        }

        row = build_projection_row(
            asset_kind="stock",
            snapshot=snapshot,
            event=event,
            pull_plan_id=42,
            today_bars=[],
            previous_bars=[],
            latest_closed_minute=datetime(2026, 6, 12, 14, 30, tzinfo=SHANGHAI),
            contract=contract,
            source_condition_run_id="condition_layer",
            projection_run_id=PROJECTION_RUN_ID,
            for_trade_date="20260612",
            prev_trade_date="20260611",
            calculation_config=sample_calculation_config(),
        )

        self.assertEqual(row["projection_window_id"], "20260612_1400_1430")
        self.assertEqual(row["snapshot_time"], datetime(2026, 6, 12, 14, 30, tzinfo=SHANGHAI))
        self.assertLessEqual(row["snapshot_time"], row["window_end"])
        self.assertEqual(row["raw_json"]["projection_bucket_closed_label"], "2026-06-12T14:30:00+08:00")
        self.assertEqual(row["raw_json"]["projection_snapshot_time"], "2026-06-12T14:30:00+08:00")

    def test_fact_only_midday_projection_time_policy_noops_before_build_or_write(self) -> None:
        contract = sample_contract()
        contract["dates"] = {
            "for_trade_date": "20260612",
            "source_trade_date": "20260611",
            "prev_trade_date": "20260611",
        }
        contract["calculation_config"] = sample_calculation_config()
        contract["projection_time_policy"] = {
            "mode": "fact_only_defer_off_bucket_source_snapshot_time",
            "bucket_time_source": "source_snapshot_time",
            "off_bucket_source_snapshot_time_handling": "NOOP_PASS_NO_WRITE",
            "no_closed_data_forged": True,
            "maps_midday_to_trading_bucket": False,
        }
        pre_backup = sample_clean_snapshot()
        pre_backup["source_run_rows"] = {
            "subscription": {"status": "passed", "market_data_fact_written": False},
            "snapshot": {"status": "passed", "market_data_fact_written": True},
            "preload": {"status": "passed", "market_data_fact_written": True},
            "today": {"status": "passed", "market_data_fact_written": True},
        }
        off_bucket_evidence = {
            "should_noop": True,
            "reason": "off_bucket_source_snapshot_time",
            "off_bucket_count": 1,
            "off_bucket_by_asset": {"stock": 1},
            "sample": [
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "snapshot_time": "2026-06-12T12:05:00+08:00",
                }
            ],
            "no_closed_data_forged": True,
        }

        with tempfile.TemporaryDirectory() as tmp:
            contract_path = Path(tmp) / "contract.json"
            preflight_path = Path(tmp) / "preflight.json"
            dry_run_path = Path(tmp) / "dry_run.json"
            report_path = Path(tmp) / "report.json"
            md_path = Path(tmp) / "report.md"
            rollback_path = Path(tmp) / "rollback.sql"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            preflight_path.write_text(json.dumps(sample_preflight("PREFLIGHT_PASS")), encoding="utf-8")
            dry_run_path.write_text(
                json.dumps({"result": "DRY_RUN_PASS", "projection_run_id_candidate": PROJECTION_RUN_ID}),
                encoding="utf-8",
            )

            with patch(
                "ashare_v3.market.realtime_projection_execute.capture_projection_execute_snapshot",
                return_value=pre_backup,
            ), patch(
                "ashare_v3.market.realtime_projection_execute.detect_projection_time_policy_noop",
                return_value=off_bucket_evidence,
            ), patch(
                "ashare_v3.market.realtime_projection_execute.build_projection_rows",
                side_effect=AssertionError("B2 NOOP must happen before projection row build"),
            ), patch(
                "ashare_v3.market.realtime_projection_execute.write_projection_execute_transaction",
                side_effect=AssertionError("B2 NOOP must happen before DB write"),
            ):
                report = run_realtime_projection_metric_execute(
                    dsn="postgresql://example",
                    contract_path=str(contract_path),
                    preflight_path=str(preflight_path),
                    dry_run_path=str(dry_run_path),
                    json_report_path=str(report_path),
                    markdown_report_path=str(md_path),
                    rollback_sql_path=str(rollback_path),
                    projection_run_id=PROJECTION_RUN_ID,
                    for_trade_date="20260612",
                    execute=True,
                    user_confirmed=True,
                )

            self.assertEqual(report["result"], "NOOP_PASS")
            self.assertEqual(report["noop_reason"], "off_bucket_source_snapshot_time")
            self.assertEqual(report["write_result"]["projection_rows_written"], 0)
            self.assertEqual(report["write_result"]["quality_item_rows_written"], 0)
            self.assertFalse(report["side_effects"]["writes_performed"])
            self.assertFalse(report["side_effects"]["projection_fact_written"])
            self.assertFalse(report["side_effects"]["event_outbox_written"])
            self.assertTrue(report["projection_time_policy_noop"]["no_closed_data_forged"])
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["result"], "NOOP_PASS")

    def test_auction_snapshot_only_noops_without_today_minute_before_db_probe_or_write(self) -> None:
        contract = sample_contract()
        contract["projection_input_mode"] = "auction_or_snapshot_only"
        contract["source_runs"] = {
            "source_condition_run_id": "condition_layer",
            "subscription_run_id": "subscription",
            "snapshot_run_id": "snapshot",
            "preload_run_id": "preload",
            "today_minute_run_id": None,
        }
        contract["source_requirements"] = {
            "requires_snapshot_run": True,
            "requires_previous_day_minute_run": True,
            "requires_today_minute_run": False,
            "closed_minute_forged": False,
            "auction_or_snapshot_only_allowed": True,
        }
        contract["snapshot_only_execution_policy"] = {
            "noop_pass_no_write_allowed": True,
            "is_auction_virtual": True,
            "period_source": "snapshot_only_no_closed_1m",
            "quality_status": "pending_market_data",
            "minute_bar_closed_written": False,
        }
        preflight = sample_preflight("PREFLIGHT_PASS")
        preflight["lineage_checks"][-1] = {
            "name": "today_minute_run_id_not_required",
            "passed": True,
            "value": False,
        }
        dry_run = {"result": "DRY_RUN_PASS", "projection_run_id_candidate": PROJECTION_RUN_ID}

        with tempfile.TemporaryDirectory() as tmp:
            contract_path = Path(tmp) / "contract.json"
            preflight_path = Path(tmp) / "preflight.json"
            dry_run_path = Path(tmp) / "dry_run.json"
            report_path = Path(tmp) / "report.json"
            md_path = Path(tmp) / "report.md"
            rollback_path = Path(tmp) / "rollback.sql"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            preflight_path.write_text(json.dumps(preflight), encoding="utf-8")
            dry_run_path.write_text(json.dumps(dry_run), encoding="utf-8")

            with patch(
                "ashare_v3.market.realtime_projection_execute.capture_projection_execute_snapshot",
                side_effect=AssertionError("snapshot-only NOOP must happen before DB probe"),
            ), patch(
                "ashare_v3.market.realtime_projection_execute.build_projection_rows",
                side_effect=AssertionError("snapshot-only NOOP must not build closed-minute rows"),
            ), patch(
                "ashare_v3.market.realtime_projection_execute.write_projection_execute_transaction",
                side_effect=AssertionError("snapshot-only NOOP must not write DB"),
            ):
                report = run_realtime_projection_metric_execute(
                    dsn="postgresql://example",
                    contract_path=str(contract_path),
                    preflight_path=str(preflight_path),
                    dry_run_path=str(dry_run_path),
                    json_report_path=str(report_path),
                    markdown_report_path=str(md_path),
                    rollback_sql_path=str(rollback_path),
                    projection_run_id=PROJECTION_RUN_ID,
                    for_trade_date="20260525",
                    execute=True,
                    user_confirmed=True,
                )

            self.assertEqual(report["result"], "NOOP_PASS")
            self.assertEqual(report["noop_reason"], "auction_or_snapshot_only_waiting_for_metric_runner")
            self.assertIsNone(report["today_minute_run_id"])
            self.assertTrue(report["snapshot_only_metric_policy"]["is_auction_virtual"])
            self.assertEqual(report["snapshot_only_metric_policy"]["period_source"], "snapshot_only_no_closed_1m")
            self.assertEqual(report["snapshot_only_metric_policy"]["quality_status"], "pending_market_data")
            self.assertFalse(report["snapshot_only_metric_policy"]["trace_json"]["closed_minute_forged"])
            self.assertFalse(report["snapshot_only_metric_policy"]["trace_json"]["minute_bar_closed_written"])
            self.assertEqual(report["write_result"]["projection_rows_written"], 0)
            self.assertFalse(report["side_effects"]["writes_performed"])
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["result"], "NOOP_PASS")

    def test_fact_only_projection_time_policy_stores_bucket_time_at_boundary(self) -> None:
        contract = sample_contract()
        contract["source_runs"] = {
            "snapshot_run_id": "realtime_snapshot_fact_only",
            "today_minute_run_id": "today_minute",
            "preload_run_id": "preload",
        }
        contract["calculation_config"] = sample_calculation_config()
        contract["projection_time_policy"] = {
            "mode": "fact_only_defer_off_bucket_source_snapshot_time",
            "bucket_time_source": "source_snapshot_time",
            "off_bucket_source_snapshot_time_handling": "NOOP_PASS_NO_WRITE",
            "no_closed_data_forged": True,
            "maps_midday_to_trading_bucket": False,
        }
        snapshot = sample_snapshot()
        snapshot["snapshot_time"] = datetime(2026, 6, 11, 14, 0, 0, 10889, tzinfo=SHANGHAI)

        row = build_projection_row(
            asset_kind="stock",
            snapshot=snapshot,
            event=None,
            pull_plan_id=42,
            today_bars=projection_policy_current_bars(),
            previous_bars=projection_policy_previous_bars(),
            latest_closed_minute=datetime(2026, 6, 11, 13, 59, tzinfo=SHANGHAI),
            contract=contract,
            source_condition_run_id="condition_layer",
            projection_run_id=PROJECTION_RUN_ID,
            for_trade_date="20260611",
            prev_trade_date="20260610",
            calculation_config=sample_calculation_config(),
        )

        self.assertEqual(row["projection_window_id"], "20260611_1330_1400")
        self.assertEqual(row["snapshot_time"], datetime(2026, 6, 11, 14, 0, tzinfo=SHANGHAI))
        self.assertLessEqual(row["snapshot_time"], row["window_end"])
        self.assertEqual(row["raw_json"]["source_snapshot_time"], "2026-06-11T14:00:00.010889+08:00")
        self.assertEqual(row["raw_json"]["projection_snapshot_time"], "2026-06-11T14:00:00+08:00")

    def test_fact_only_projection_after_latest_closed_minute_is_ready_for_trigger_only(self) -> None:
        contract = sample_contract()
        contract["source_runs"] = {
            "snapshot_run_id": "realtime_snapshot_fact_only",
            "today_minute_run_id": "today_minute",
            "preload_run_id": "preload",
        }
        contract["calculation_config"] = sample_calculation_config()
        contract["projection_time_policy"] = {
            "mode": "fact_only_defer_off_bucket_source_snapshot_time",
            "bucket_time_source": "source_snapshot_time",
            "off_bucket_source_snapshot_time_handling": "NOOP_PASS_NO_WRITE",
            "no_closed_data_forged": True,
            "maps_midday_to_trading_bucket": False,
        }
        contract["fact_only_snapshot_trace_policy"] = {
            "allow_missing_snapshot_event_id": True,
            "required_trace_fields": ["snapshot_id", "subscription_id", "pull_plan_id", "source_adapter"],
        }
        snapshot = sample_snapshot()
        snapshot["snapshot_time"] = datetime(2026, 6, 11, 13, 43, tzinfo=SHANGHAI)

        row = build_projection_row(
            asset_kind="stock",
            snapshot=snapshot,
            event=None,
            pull_plan_id=42,
            today_bars=projection_policy_current_bars(),
            previous_bars=projection_policy_previous_bars(),
            latest_closed_minute=datetime(2026, 6, 11, 13, 41, tzinfo=SHANGHAI),
            contract=contract,
            source_condition_run_id="condition_layer",
            projection_run_id=PROJECTION_RUN_ID,
            for_trade_date="20260611",
            prev_trade_date="20260610",
            calculation_config=sample_calculation_config(),
        )

        self.assertEqual(row["projection_status"], "ready")
        self.assertEqual(row["projection_quality_status"], "passed")
        self.assertEqual(row["trace_status"], "passed")
        self.assertNotIn("snapshot_time_after_c1_latest_closed_minute", row["source_fact_ids"]["missing_reason"])
        self.assertTrue(row["source_fact_ids"]["source_snapshot_after_latest_closed_minute"])
        self.assertFalse(row["source_fact_ids"]["closed_minute_confirmation_available"])
        self.assertEqual(row["raw_json"]["evidence_role"], "provisional_trigger_evidence")
        self.assertFalse(row["raw_json"]["closed_minute_confirmed_for_actionexecuted"])

    def test_rollback_scope_uses_projection_run_id_and_no_outbox_delete(self) -> None:
        sql = build_projection_rollback_sql(PROJECTION_RUN_ID)

        first_delete = sql.index("DELETE FROM")
        self.assertLess(sql.index("RAISE EXCEPTION"), first_delete)
        self.assertIn(f"SELECT set_config('app.n3_b2_projection_run_id', '{PROJECTION_RUN_ID}', false);", sql)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("common_trigger_state", sql)
        self.assertIn("common_trigger_match", sql)
        self.assertIn("common_action_event", sql)
        self.assertIn("user_projection_run", sql)
        self.assertIn("downstream_layers_touched", sql)
        self.assertIn("worker_started", sql)
        self.assertIn("WHERE run_id = current_setting('app.n3_b2_projection_run_id')", sql)
        self.assertIn("WHERE projection_run_id = current_setting('app.n3_b2_projection_run_id')", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)

    def test_source_run_id_resolution_supports_additive_multi_run_fields(self) -> None:
        source_runs = {
            "today_minute_run_id": "today_base",
            "today_minute_run_ids": ["today_base", "today_expansion"],
            "preload_run_id": "preload_base",
            "preload_run_ids": ["preload_expansion"],
        }

        self.assertEqual(
            resolve_source_run_ids(source_runs, "today_minute_run_id", "today_minute_run_ids"),
            ["today_base", "today_expansion"],
        )
        self.assertEqual(
            resolve_source_run_ids(source_runs, "preload_run_id", "preload_run_ids"),
            ["preload_base", "preload_expansion"],
        )

    def test_projection_quality_items_use_existing_data_domains_and_metric_scope(self) -> None:
        rows = [
            projection_row("stock", "stock:SH:600000", "ready", "up_volume_expanding"),
            projection_row("index", "index:SH:000905", "ready", "flat"),
            projection_row("board", "board:TDX:881002", "not_ready", "unknown"),
            projection_row("stock", "stock:BJ:920045", "not_ready", "unknown"),
        ]

        items = build_projection_quality_items(
            contract=sample_contract(),
            rows=rows,
            pre_backup={"outbox_rows_for_projection_run": 0},
        )

        self.assertTrue(items)
        domains = {str(item.get("data_domain") or "") for item in items}
        self.assertLessEqual(domains, set(ALLOWED_QUALITY_DATA_DOMAINS))
        self.assertNotIn("market_data_projection", domains)
        for item in items:
            details = item.get("details") or {}
            self.assertEqual(item.get("layer_scope"), B2_QUALITY_LAYER_SCOPE)
            self.assertNotEqual(item.get("layer_scope"), PROJECTION_METRIC_SCOPE)
            self.assertEqual(details.get("metric_scope"), PROJECTION_METRIC_SCOPE)
            self.assertEqual(details.get("projection_run_id"), PROJECTION_RUN_ID)
            self.assertIn(details.get("asset_kind"), ALLOWED_QUALITY_DATA_DOMAINS)
            self.assertEqual(details.get("projection_schema_version"), "n3.realtime_projection.v1")
        by_gate = {str(item["gate_code"]): item for item in items}
        self.assertEqual(by_gate["n3_b2_execute_board_not_ready_visible"]["data_domain"], "board")
        self.assertEqual(by_gate["n3_b2_execute_board_not_ready_visible"]["table_name"], "board_realtime_projection_metric")
        self.assertEqual(by_gate["n3_b2_execute_bj_920xxx_not_ready_visible"]["data_domain"], "stock")
        self.assertEqual(by_gate["n3_b2_execute_bj_920xxx_not_ready_visible"]["table_name"], "stock_realtime_projection_metric")
        self.assertEqual(by_gate["n3_b2_execute_projection_rows_match_contract"]["data_domain"], "common")

    def test_b2_contract_and_preflight_document_quality_data_domain_policy(self) -> None:
        for path in (
            Path("docs/N3_B2_realtime_projection_execute_contract.json"),
            Path("docs/N3_B2_realtime_projection_execute_preflight.json"),
        ):
            data = json.loads(path.read_text())
            policy = data.get("quality_data_domain_policy") or (data.get("contract_summary") or {}).get(
                "quality_data_domain_policy"
            )
            scope_policy = data.get("quality_layer_scope_policy") or (data.get("contract_summary") or {}).get(
                "quality_layer_scope_policy"
            )
            self.assertIsNotNone(policy, f"{path} must document B2 quality data_domain policy")
            self.assertIsNotNone(scope_policy, f"{path} must document B2 quality layer_scope policy")
            self.assertEqual(set(policy["allowed_data_domains"]), set(ALLOWED_QUALITY_DATA_DOMAINS))
            self.assertNotIn("market_data_projection", policy["allowed_data_domains"])
            self.assertIn("market_data_projection", policy.get("forbidden_data_domains", []))
            self.assertEqual(scope_policy["layer_scope"], B2_QUALITY_LAYER_SCOPE)
            self.assertNotIn(PROJECTION_METRIC_SCOPE, scope_policy.get("allowed_layer_scopes", []))
            self.assertIn(PROJECTION_METRIC_SCOPE, scope_policy.get("forbidden_layer_scopes", []))
        preflight = json.loads(Path("docs/N3_B2_realtime_projection_execute_preflight.json").read_text())
        for item in (preflight.get("quality") or {}).get("items", []):
            if str(item.get("gate_code") or "").startswith("n3_b2_"):
                if "data_domain" in item:
                    self.assertIn(item["data_domain"], ALLOWED_QUALITY_DATA_DOMAINS)
                if "layer_scope" in item:
                    self.assertEqual(item["layer_scope"], B2_QUALITY_LAYER_SCOPE)
                details = item.get("details") or {}
                self.assertNotEqual(item.get("data_domain"), "market_data_projection")
                self.assertNotEqual(item.get("layer_scope"), PROJECTION_METRIC_SCOPE)
                self.assertEqual(details.get("metric_scope"), PROJECTION_METRIC_SCOPE)


def sample_contract() -> dict[str, object]:
    return {
        "stage": "N3-B2-realtime-projection-execute-contract",
        "layer_role": "N3_market_data",
        "execution_mode": "realtime_projection_metric_run_once_execute",
        "projection_run_id": PROJECTION_RUN_ID,
        "dates": {"for_trade_date": "20260525"},
        "source_runs": {
            "source_condition_run_id": "condition_layer",
            "subscription_run_id": "subscription",
            "snapshot_run_id": "snapshot",
            "preload_run_id": "preload",
            "today_minute_run_id": "today",
        },
        "writes_outbox": False,
        "updates_market_snapshot_payload": False,
        "consumes_outbox": False,
        "starts_worker": False,
        "expected_projection_rows": {"stock": 2, "index": 1, "board": 1, "total": 4},
        "expected_distribution": {
            "ready_rows": 2,
            "ready_by_asset": {"stock": 1, "index": 1},
            "not_ready_rows": 2,
            "not_ready_by_asset": {"stock": 1, "board": 1},
            "projection_signal_status": {"up_volume_expanding": 1, "flat": 1, "unknown": 2},
        },
    }


def sample_preflight(result: str) -> dict[str, object]:
    return {
        "stage": "N3-B2-realtime-projection-execute-preflight",
        "layer_role": "N3_market_data",
        "result": result,
        "projection_run_id": PROJECTION_RUN_ID,
        "lineage_checks": [
            {"kind": "subscription", "passed": True},
            {"kind": "snapshot", "passed": True},
            {"kind": "preload", "passed": True},
            {"kind": "today_minute", "passed": True},
        ],
        "contract_summary": {
            "writes_outbox": False,
            "updates_market_snapshot_payload": False,
            "consumes_outbox": False,
        },
    }


def sample_clean_snapshot() -> dict[str, object]:
    return {
        "projection_run_exists": False,
        "projection_run_table_counts": {
            "stock_realtime_projection_metric": 0,
            "index_realtime_projection_metric": 0,
            "board_realtime_projection_metric": 0,
        },
        "quality_rows_for_projection_run": 0,
        "outbox_rows_for_projection_run": 0,
        "inbox_rows_for_projection_run": 0,
        "checkpoint_refs_for_projection_run": 0,
    }


def projection_row(asset_kind: str, identity_key: str, status: str, signal: str) -> dict[str, object]:
    return {
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "projection_status": status,
        "projection_quality_status": "passed" if status == "ready" else "blocked",
        "trace_status": "passed" if status == "ready" else "blocked",
        "projection_signal_status": signal,
    }


def sample_calculation_config() -> dict[str, object]:
    return {
        "completion_ratio_min_ready": "0.1",
        "amount_projection_expand_threshold": "1.2",
        "amount_projection_shrink_threshold": "0.8",
        "price_flat_abs_pct_threshold": "0.001",
        "window_total_seconds": 1800,
        "calculation_method": "active_30m_bucket_projection_v1_strict_current_lineage",
        "calculation_config_hash": "test-hash",
    }


def sample_snapshot() -> dict[str, object]:
    return {
        "snapshot_id": 1,
        "subscription_id": 2,
        "identity_key": "stock:SH:600000",
        "exchange": "SH",
        "code": "600000",
        "display_code": "600000",
        "name": "sample",
        "snapshot_time": datetime(2026, 6, 5, 11, 5, tzinfo=SHANGHAI),
        "current_price": Decimal("10.10"),
        "close": Decimal("10.10"),
        "source_adapter": "StockMarketDataAdapter",
    }


def sample_current_bars() -> list[dict[str, object]]:
    return [
        {
            "bar_id": 10,
            "bar_time": datetime(2026, 6, 5, 11, 1, tzinfo=SHANGHAI),
            "open": Decimal("10.00"),
            "high": Decimal("10.10"),
            "low": Decimal("9.99"),
            "close": Decimal("10.05"),
            "volume": Decimal("100"),
            "amount": Decimal("1000"),
            "quality_status": "passed",
        },
        {
            "bar_id": 11,
            "bar_time": datetime(2026, 6, 5, 11, 5, tzinfo=SHANGHAI),
            "open": Decimal("10.05"),
            "high": Decimal("10.20"),
            "low": Decimal("10.04"),
            "close": Decimal("10.10"),
            "volume": Decimal("120"),
            "amount": Decimal("1200"),
            "quality_status": "passed",
        },
    ]


def sample_previous_bars() -> list[dict[str, object]]:
    return [
        {
            "bar_id": 20,
            "bar_time": datetime(2026, 6, 4, 11, 1, tzinfo=SHANGHAI),
            "open": Decimal("9.90"),
            "high": Decimal("10.00"),
            "low": Decimal("9.80"),
            "close": Decimal("9.95"),
            "volume": Decimal("100"),
            "amount": Decimal("900"),
            "quality_status": "passed",
        },
        {
            "bar_id": 21,
            "bar_time": datetime(2026, 6, 4, 11, 5, tzinfo=SHANGHAI),
            "open": Decimal("9.95"),
            "high": Decimal("10.05"),
            "low": Decimal("9.90"),
            "close": Decimal("10.00"),
            "volume": Decimal("100"),
            "amount": Decimal("900"),
            "quality_status": "passed",
        },
        {
            "bar_id": 22,
            "bar_time": datetime(2026, 6, 4, 11, 30, tzinfo=SHANGHAI),
            "open": Decimal("10.00"),
            "high": Decimal("10.10"),
            "low": Decimal("9.95"),
            "close": Decimal("10.05"),
            "volume": Decimal("100"),
            "amount": Decimal("900"),
            "quality_status": "passed",
        },
    ]


def projection_policy_current_bars() -> list[dict[str, object]]:
    return [
        {
            "bar_id": 30,
            "bar_time": datetime(2026, 6, 11, 13, 31, tzinfo=SHANGHAI),
            "open": Decimal("10.00"),
            "high": Decimal("10.10"),
            "low": Decimal("9.99"),
            "close": Decimal("10.05"),
            "volume": Decimal("100"),
            "amount": Decimal("1000"),
            "quality_status": "passed",
        },
        {
            "bar_id": 31,
            "bar_time": datetime(2026, 6, 11, 13, 41, tzinfo=SHANGHAI),
            "open": Decimal("10.05"),
            "high": Decimal("10.20"),
            "low": Decimal("10.04"),
            "close": Decimal("10.10"),
            "volume": Decimal("120"),
            "amount": Decimal("1200"),
            "quality_status": "passed",
        },
    ]


def projection_policy_previous_bars() -> list[dict[str, object]]:
    return [
        {
            "bar_id": 40,
            "bar_time": datetime(2026, 6, 10, 13, 31, tzinfo=SHANGHAI),
            "open": Decimal("9.90"),
            "high": Decimal("10.00"),
            "low": Decimal("9.80"),
            "close": Decimal("9.95"),
            "volume": Decimal("100"),
            "amount": Decimal("900"),
            "quality_status": "passed",
        },
        {
            "bar_id": 41,
            "bar_time": datetime(2026, 6, 10, 13, 41, tzinfo=SHANGHAI),
            "open": Decimal("9.95"),
            "high": Decimal("10.05"),
            "low": Decimal("9.90"),
            "close": Decimal("10.00"),
            "volume": Decimal("100"),
            "amount": Decimal("900"),
            "quality_status": "passed",
        },
        {
            "bar_id": 42,
            "bar_time": datetime(2026, 6, 10, 14, 0, tzinfo=SHANGHAI),
            "open": Decimal("10.00"),
            "high": Decimal("10.10"),
            "low": Decimal("9.95"),
            "close": Decimal("10.05"),
            "volume": Decimal("100"),
            "amount": Decimal("900"),
            "quality_status": "passed",
        },
    ]


if __name__ == "__main__":
    unittest.main()
