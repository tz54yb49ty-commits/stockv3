import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

from ashare_v3.market.realtime_snapshot_execute import (
    ALLOWED_B1_FACT_ONLY_WRITE_TABLES,
    ALLOWED_B1_WRITE_TABLES,
    AssetRoutingRealtimeSnapshotAdapter,
    BoardMarketDataAdapter,
    FORBIDDEN_B1_WRITE_TABLE_MARKERS,
    IndexMarketDataAdapter,
    RealtimeSnapshotExecuteError,
    TushareBjIndexSnapshotAdapter,
    build_snapshot_record,
    build_snapshot_source_time_evidence,
    build_post_execute_checks,
    build_post_execute_quality_items,
    ensure_clean_snapshot_target,
    ensure_executable_contract,
    ensure_execute_authorized,
    execute_one_subscription_snapshot,
    prepare_one_subscription_snapshot,
    run_realtime_daily_snapshot_execute,
)
from ashare_v3.market.realtime_snapshot_execute_contract import build_source_time_policy


class RealtimeSnapshotExecuteTest(unittest.TestCase):
    def test_requires_execute_and_user_confirmed(self) -> None:
        with self.assertRaisesRegex(RealtimeSnapshotExecuteError, "--execute"):
            ensure_execute_authorized(execute=False, user_confirmed=True)

        with self.assertRaisesRegex(RealtimeSnapshotExecuteError, "--user-confirmed"):
            ensure_execute_authorized(execute=True, user_confirmed=False)

    def test_readiness_false_blocks_before_adapter_use(self) -> None:
        with self.assertRaisesRegex(RealtimeSnapshotExecuteError, "readiness"):
            ensure_executable_contract(
                {**sample_contract(), "writes_outbox": False},
                {**sample_readiness(), "ready": False, "blocked_reason": "test_blocker"},
                execute=True,
                user_confirmed=True,
                no_outbox=True,
                for_trade_date="20260525",
                snapshot_run_id="realtime_daily_snapshot_20260525__market_data_subscription_test",
            )

    def test_fact_only_contract_requires_explicit_no_outbox_confirmation(self) -> None:
        contract = {**sample_contract(), "writes_outbox": False}

        with self.assertRaisesRegex(RealtimeSnapshotExecuteError, "--no-outbox"):
            ensure_executable_contract(
                contract,
                sample_readiness(),
                execute=True,
                user_confirmed=True,
                no_outbox=False,
                for_trade_date="20260525",
                snapshot_run_id="realtime_daily_snapshot_20260525__market_data_subscription_test",
            )

        ensure_executable_contract(
            contract,
            sample_readiness(),
            execute=True,
            user_confirmed=True,
            no_outbox=True,
            for_trade_date="20260525",
            snapshot_run_id="realtime_daily_snapshot_20260525__market_data_subscription_test",
        )

    def test_pre_open_contract_requires_explicit_source_policy_confirmation(self) -> None:
        contract = {
            **sample_contract(),
            "writes_outbox": False,
            "source_time_policy": {"mode": "pre_open_fact_only"},
        }

        with self.assertRaisesRegex(RealtimeSnapshotExecuteError, "--pre-open-source-policy"):
            ensure_executable_contract(
                contract,
                sample_readiness(),
                execute=True,
                user_confirmed=True,
                no_outbox=True,
                pre_open_source_policy=False,
                for_trade_date="20260525",
                snapshot_run_id="realtime_daily_snapshot_20260525__market_data_subscription_test",
            )

        ensure_executable_contract(
            contract,
            sample_readiness(),
            execute=True,
            user_confirmed=True,
            no_outbox=True,
            pre_open_source_policy=True,
            for_trade_date="20260525",
            snapshot_run_id="realtime_daily_snapshot_20260525__market_data_subscription_test",
        )

    def test_writes_outbox_contract_requires_explicit_writes_outbox_confirmation(self) -> None:
        with self.assertRaisesRegex(RealtimeSnapshotExecuteError, "--writes-outbox=true"):
            ensure_executable_contract(
                sample_contract(),
                sample_readiness(),
                execute=True,
                user_confirmed=True,
                no_outbox=False,
                for_trade_date="20260525",
                snapshot_run_id="realtime_daily_snapshot_20260525__market_data_subscription_test",
            )

        with self.assertRaisesRegex(RealtimeSnapshotExecuteError, "conflicts"):
            ensure_executable_contract(
                sample_contract(),
                sample_readiness(),
                execute=True,
                user_confirmed=True,
                no_outbox=True,
                allow_outbox=True,
                for_trade_date="20260525",
                snapshot_run_id="realtime_daily_snapshot_20260525__market_data_subscription_test",
            )

        ensure_executable_contract(
            sample_contract(),
            sample_readiness(),
            execute=True,
            user_confirmed=True,
            no_outbox=False,
            allow_outbox=True,
            for_trade_date="20260525",
            snapshot_run_id="realtime_daily_snapshot_20260525__market_data_subscription_test",
        )

    def test_snapshot_run_id_existing_blocks_by_default(self) -> None:
        backup = {
            "snapshot_run_exists": True,
            "target_snapshot_run_row_counts": {"stock_realtime_daily_snapshot": 0},
            "snapshot_outbox_row_count": 0,
            "downstream_inbox_row_count": 0,
        }

        with self.assertRaisesRegex(RealtimeSnapshotExecuteError, "already exists"):
            ensure_clean_snapshot_target(backup, "realtime_daily_snapshot_20260525__market_data_subscription_test")

    def test_for_trade_date_marker_is_not_target_row(self) -> None:
        backup = {
            "snapshot_run_exists": False,
            "target_snapshot_run_row_counts": {
                "stock_realtime_daily_snapshot": 0,
                "index_realtime_daily_snapshot": 0,
                "board_realtime_daily_snapshot": 0,
                "common_market_data_quality_item": 0,
                "common_market_data_run": 0,
                "common_event_outbox": 0,
                "for_trade_date_marker": 1,
            },
            "snapshot_outbox_row_count": 0,
            "downstream_inbox_row_count": 0,
        }

        ensure_clean_snapshot_target(backup, "realtime_daily_snapshot_20260525__market_data_subscription_test")

    def test_build_snapshot_record_keeps_trace_fields(self) -> None:
        record = build_snapshot_record(
            contract=sample_contract(),
            subscription=sample_subscription(),
            adapter_name="StockMarketDataAdapter",
            adapter=FakeSnapshotAdapter({"stock:SH:600000": sample_raw_snapshot()}),
            raw_snapshot=sample_raw_snapshot(),
            snapshot_time=sample_snapshot_time(),
        )

        self.assertEqual(record["run_id"], sample_contract()["snapshot_run_id"])
        self.assertEqual(record["subscription_id"], 11)
        self.assertEqual(record["pull_plan_id"], 22)
        self.assertEqual(record["source_adapter"], "StockMarketDataAdapter")
        self.assertEqual(record["identity_key"], "stock:SH:600000")
        self.assertEqual(record["quality_status"], "passed")

    def test_pre_open_snapshot_record_marks_source_time_warning(self) -> None:
        contract = {
            **sample_contract(),
            "writes_outbox": False,
            "source_time_policy": {"mode": "pre_open_fact_only"},
        }
        raw_snapshot = {
            "open": 0,
            "high": 0,
            "low": 0,
            "close": 0,
            "current_price": 0,
            "pre_close": 10,
            "volume": 0,
            "amount": 0,
            "raw_payload": {"price": 0, "open": 0, "volume": 0},
        }
        evidence = build_snapshot_source_time_evidence(
            contract=contract,
            raw_snapshot=raw_snapshot,
            default_time=sample_snapshot_time(),
        )
        record = build_snapshot_record(
            contract=contract,
            subscription=sample_subscription(),
            adapter_name="StockMarketDataAdapter",
            adapter=FakeSnapshotAdapter({"stock:SH:600000": raw_snapshot}),
            raw_snapshot=raw_snapshot,
            snapshot_time=evidence["resolved_snapshot_time"],
            source_time_evidence=evidence,
        )

        self.assertEqual(record["quality_status"], "partial")
        self.assertEqual(record["data_quality_status"], "partial")
        raw_json = record["raw_json"].obj
        self.assertEqual(raw_json["source_time_status"], "source_time_missing_or_preopen")
        self.assertTrue(raw_json["source_time_missing_or_preopen"])
        self.assertEqual(raw_json["snapshot_time_policy"], "execution_time_when_source_time_missing")

    def test_future_source_time_is_p0_failed_and_writes_no_outbox(self) -> None:
        execution_time = datetime(2026, 6, 11, 13, 11, tzinfo=timezone(timedelta(hours=8)))
        future_raw_snapshot = {
            **sample_raw_snapshot(),
            "snapshot_time": "2026-06-11T15:00:00+08:00",
        }
        conn = FakeConnection()
        adapter = FakeSnapshotAdapter({"board:TDX:881002": future_raw_snapshot})

        result = execute_one_subscription_snapshot(
            dsn="postgresql://test",
            contract={
                **sample_board_contract(),
                "source_time_policy": {"mode": "strict_live", "future_tolerance_seconds": 120},
            },
            subscription=sample_board_subscription(),
            adapter=adapter,
            connection_factory=lambda _dsn: conn,
            snapshot_time=execution_time,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["quality_status"], "failed")
        self.assertEqual(result["source_time_status"], "source_time_future")
        self.assertIsNone(result["event_type"])
        self.assertEqual(result["snapshot_rows_written"], 0)
        self.assertEqual(result["quality_item_rows_written"], 1)
        self.assertEqual(result["outbox_rows_written"], 0)
        self.assertEqual(conn.sql_kinds(), ["quality_fact"])

    def test_source_returned_time_accepts_open_row_before_wall_clock_open(self) -> None:
        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": {"mode": "source_returned_time"},
            },
            raw_snapshot={
                **sample_raw_snapshot(),
                "snapshot_time": "2026-06-29T09:31:00+08:00",
            },
            default_time=datetime(2026, 6, 29, 9, 20, tzinfo=timezone(timedelta(hours=8))),
        )

        self.assertEqual(evidence["source_time_policy_mode"], "source_returned_time")
        self.assertEqual(evidence["source_time_status"], "source_time_confirmed")
        self.assertEqual(evidence["source_snapshot_time"], "2026-06-29T09:31:00+08:00")
        self.assertEqual(evidence["source_snapshot_trade_date"], "20260629")

    def test_b1_contract_planner_generates_source_returned_time_policy(self) -> None:
        policy = build_source_time_policy(source_returned_time_policy=True)

        self.assertEqual(policy["mode"], "source_returned_time")
        self.assertFalse(policy["allow_source_time_missing_or_preopen"])
        self.assertTrue(policy["source_time_required"])
        self.assertTrue(policy["local_observed_at_trace_only"])
        self.assertEqual(policy["future_source_time_handling"], "allowed_when_source_trade_date_matches")
        self.assertEqual(policy["quality_gate_code"], "BLOCKED_N3_SOURCE_RETURNED_TIME_INVALID")
        self.assertEqual(policy["untrusted_source_time_label_handling"], "NORMALIZE_TO_OBSERVED_AT")
        self.assertEqual(policy["index_board_period_label_policy"], "normalize_to_observed_at_trace_raw_label")
        self.assertTrue(policy["index_board_only_normalization"])
        self.assertEqual(
            policy["stock_missing_source_time_policy"],
            "observed_at_fallback_when_effective_quote_present",
        )
        self.assertTrue(policy["stock_observed_at_fallback"])
        self.assertFalse(policy["stock_trusted_source_timestamp_required"])
        self.assertEqual(policy["stock_fallback_quality_severity"], "P1")

    def test_source_returned_stock_missing_source_time_falls_back_to_observed_at_when_quote_valid(self) -> None:
        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": build_source_time_policy(source_returned_time_policy=True),
            },
            raw_snapshot={
                **sample_raw_snapshot(),
                "observed_at": "2026-06-29T09:32:30+08:00",
                "fetched_at": "2026-06-29T09:32:31+08:00",
            },
            default_time=datetime(2026, 6, 29, 9, 32, 32, tzinfo=timezone(timedelta(hours=8))),
            asset_kind="stock",
        )

        self.assertEqual(evidence["source_time_status"], "source_time_observed_at_fallback")
        self.assertTrue(evidence["source_time_warning"])
        self.assertTrue(evidence["source_time_observed_at_fallback"])
        self.assertFalse(evidence["trusted_source_timestamp_present"])
        self.assertEqual(evidence["stock_missing_source_time_policy"], "observed_at_fallback_when_effective_quote_present")
        self.assertEqual(evidence["stock_source_time_fallback_reason"], "missing_trusted_source_timestamp")
        self.assertEqual(evidence["source_snapshot_time"], "2026-06-29T09:32:30+08:00")
        self.assertEqual(evidence["source_snapshot_trade_date"], "20260629")

    def test_source_returned_stock_fallback_blocks_fake_marker(self) -> None:
        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": build_source_time_policy(source_returned_time_policy=True),
            },
            raw_snapshot={
                **sample_raw_snapshot(),
                "observed_at": "2026-06-29T09:32:30+08:00",
                "source_marker": "fabricated",
            },
            default_time=datetime(2026, 6, 29, 9, 32, 32, tzinfo=timezone(timedelta(hours=8))),
            asset_kind="stock",
        )

        self.assertEqual(evidence["source_time_status"], "fake_source_time_forbidden")
        self.assertFalse(evidence["source_time_observed_at_fallback"])
        self.assertIsNone(evidence["source_snapshot_time"])
        self.assertIsNone(evidence["stock_source_time_fallback_reason"])

    def test_source_returned_stock_fallback_blocks_when_no_effective_quote(self) -> None:
        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": build_source_time_policy(source_returned_time_policy=True),
            },
            raw_snapshot={
                "open": 0,
                "high": 0,
                "low": 0,
                "close": 0,
                "current_price": 0,
                "volume": 0,
                "amount": 0,
                "observed_at": "2026-06-29T09:32:30+08:00",
            },
            default_time=datetime(2026, 6, 29, 9, 32, 32, tzinfo=timezone(timedelta(hours=8))),
            asset_kind="stock",
        )

        self.assertEqual(evidence["source_time_status"], "missing_source_time")
        self.assertFalse(evidence["source_time_observed_at_fallback"])

    def test_source_returned_stock_explicit_timestamp_date_mismatch_blocks(self) -> None:
        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": build_source_time_policy(source_returned_time_policy=True),
            },
            raw_snapshot={
                **sample_raw_snapshot(),
                "snapshot_time": "2026-06-26T09:32:30+08:00",
                "observed_at": "2026-06-29T09:32:30+08:00",
            },
            default_time=datetime(2026, 6, 29, 9, 32, 32, tzinfo=timezone(timedelta(hours=8))),
            asset_kind="stock",
        )

        self.assertEqual(evidence["source_time_status"], "source_time_date_mismatch")
        self.assertFalse(evidence["source_time_observed_at_fallback"])

    def test_source_returned_index_period_label_normalizes_to_observed_at(self) -> None:
        raw_snapshot = {
            **sample_raw_snapshot(),
            "raw_snapshot_time_label": "2026-06-29T15:00:00+08:00",
            "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
            "source_time_trust_level": "untrusted_period_label",
            "observed_at": "2026-06-29T09:32:10+08:00",
            "fetched_at": "2026-06-29T09:32:10+08:00",
        }

        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_index_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": build_source_time_policy(source_returned_time_policy=True),
            },
            raw_snapshot=raw_snapshot,
            default_time=datetime(2026, 6, 29, 9, 32, 11, tzinfo=timezone(timedelta(hours=8))),
            asset_kind="index",
        )

        self.assertEqual(evidence["source_time_status"], "source_time_label_normalized")
        self.assertTrue(evidence["source_time_label_normalized"])
        self.assertTrue(evidence["source_time_warning"])
        self.assertEqual(evidence["source_snapshot_time"], "2026-06-29T09:32:10+08:00")
        self.assertEqual(evidence["source_snapshot_trade_date"], "20260629")
        self.assertEqual(evidence["raw_snapshot_time_label"], "2026-06-29T15:00:00+08:00")
        self.assertEqual(evidence["raw_snapshot_time_semantics"], "tdx_index_frequency_9_period_label")
        self.assertEqual(evidence["source_time_trust_level"], "untrusted_period_label")
        self.assertEqual(evidence["untrusted_source_time_label_handling"], "NORMALIZE_TO_OBSERVED_AT")

    def test_source_returned_board_period_label_normalizes_to_observed_at(self) -> None:
        raw_snapshot = {
            **sample_raw_snapshot(),
            "raw_snapshot_time_label": "2026-06-29T15:00:00+08:00",
            "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
            "source_time_trust_level": "untrusted_period_label",
            "observed_at": "2026-06-29T09:32:20+08:00",
            "fetched_at": "2026-06-29T09:32:20+08:00",
        }

        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_board_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": build_source_time_policy(source_returned_time_policy=True),
            },
            raw_snapshot=raw_snapshot,
            default_time=datetime(2026, 6, 29, 9, 32, 21, tzinfo=timezone(timedelta(hours=8))),
            asset_kind="board",
        )

        self.assertEqual(evidence["source_time_status"], "source_time_label_normalized")
        self.assertEqual(evidence["source_snapshot_time"], "2026-06-29T09:32:20+08:00")
        self.assertEqual(evidence["raw_snapshot_time_label"], "2026-06-29T15:00:00+08:00")

    def test_source_returned_stock_period_label_still_blocks_under_index_board_policy(self) -> None:
        raw_snapshot = {
            **sample_raw_snapshot(),
            "raw_snapshot_time_label": "2026-06-29T15:00:00+08:00",
            "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
            "source_time_trust_level": "untrusted_period_label",
            "observed_at": "2026-06-29T09:32:10+08:00",
            "fetched_at": "2026-06-29T09:32:10+08:00",
        }

        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": build_source_time_policy(source_returned_time_policy=True),
            },
            raw_snapshot=raw_snapshot,
            default_time=datetime(2026, 6, 29, 9, 32, 11, tzinfo=timezone(timedelta(hours=8))),
            asset_kind="stock",
        )

        self.assertEqual(evidence["source_time_status"], "source_time_untrusted_label")
        self.assertFalse(evidence["source_time_label_normalized"])

    def test_source_returned_index_period_label_fake_marker_still_blocks(self) -> None:
        raw_snapshot = {
            **sample_raw_snapshot(),
            "raw_snapshot_time_label": "2026-06-29T15:00:00+08:00",
            "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
            "source_time_trust_level": "untrusted_period_label",
            "observed_at": "2026-06-29T09:32:10+08:00",
            "fetched_at": "2026-06-29T09:32:10+08:00",
            "source_marker": "synthetic",
        }

        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_index_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": build_source_time_policy(source_returned_time_policy=True),
            },
            raw_snapshot=raw_snapshot,
            default_time=datetime(2026, 6, 29, 9, 32, 11, tzinfo=timezone(timedelta(hours=8))),
            asset_kind="index",
        )

        self.assertEqual(evidence["source_time_status"], "fake_source_time_forbidden")
        self.assertFalse(evidence["source_time_label_normalized"])

    def test_source_returned_board_period_label_observed_at_date_mismatch_blocks(self) -> None:
        raw_snapshot = {
            **sample_raw_snapshot(),
            "raw_snapshot_time_label": "2026-06-29T15:00:00+08:00",
            "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
            "source_time_trust_level": "untrusted_period_label",
            "observed_at": "2026-06-26T09:32:10+08:00",
            "fetched_at": "2026-06-26T09:32:10+08:00",
        }

        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_board_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": build_source_time_policy(source_returned_time_policy=True),
            },
            raw_snapshot=raw_snapshot,
            default_time=datetime(2026, 6, 29, 9, 32, 11, tzinfo=timezone(timedelta(hours=8))),
            asset_kind="board",
        )

        self.assertEqual(evidence["source_time_status"], "source_time_date_mismatch")
        self.assertFalse(evidence["source_time_label_normalized"])

    def test_b1_contract_planner_existing_source_time_policies_unchanged(self) -> None:
        self.assertEqual(build_source_time_policy()["mode"], "strict_live")
        self.assertEqual(build_source_time_policy(pre_open_source_policy=True)["mode"], "pre_open_fact_only")

    def test_source_returned_time_rejects_missing_source_snapshot_time(self) -> None:
        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": {"mode": "source_returned_time"},
            },
            raw_snapshot=sample_raw_snapshot(),
            default_time=datetime(2026, 6, 29, 9, 20, tzinfo=timezone(timedelta(hours=8))),
        )

        self.assertEqual(evidence["source_time_status"], "missing_source_time")
        self.assertIsNone(evidence["source_snapshot_time"])

    def test_source_returned_time_rejects_trade_date_mismatch(self) -> None:
        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260629",
                "source_time_policy": {"mode": "source_returned_time"},
            },
            raw_snapshot={
                **sample_raw_snapshot(),
                "snapshot_time": "2026-06-26T09:31:00+08:00",
            },
            default_time=datetime(2026, 6, 29, 9, 20, tzinfo=timezone(timedelta(hours=8))),
        )

        self.assertEqual(evidence["source_time_status"], "source_time_date_mismatch")
        self.assertEqual(evidence["source_snapshot_trade_date"], "20260626")

    def test_index_route_mismatch_is_p0_failed_before_snapshot_or_outbox(self) -> None:
        execution_time = datetime(2026, 6, 12, 9, 33, tzinfo=timezone(timedelta(hours=8)))
        contaminated_stock_quote = {
            **sample_raw_snapshot(),
            "current_price": 6.85,
            "price": 6.85,
            "last_close": 7.01,
            "snapshot_time": "2026-06-12T09:33:00+08:00",
            "raw_payload": {
                "market": 0,
                "code": "000009",
                "price": 6.85,
                "last_close": 7.01,
            },
        }
        prepared = prepare_one_subscription_snapshot(
            contract={
                **sample_index_contract(),
                "source_time_policy": {"mode": "strict_live", "future_tolerance_seconds": 120},
            },
            subscription={
                **sample_index_subscription(),
                "identity_key": "index:SH:000009",
                "code": "000009",
                "display_code": "000009.SH",
                "name": "上证380",
            },
            adapter=FakeSnapshotAdapter({"index:SH:000009": contaminated_stock_quote}),
            snapshot_time=execution_time,
        )

        result = prepared["object_result"]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["quality_status"], "failed")
        self.assertEqual(result["identity_route_status"], "identity_route_mismatch")
        self.assertEqual(result["snapshot_rows_written"], 0)
        self.assertEqual(result["outbox_rows_written"], 0)
        self.assertIsNone(prepared["snapshot_record"])
        self.assertEqual(prepared["quality_record"]["severity"], "P0")
        self.assertEqual(prepared["quality_record"]["gate_code"], "n3_b1_identity_route_mismatch")

    def test_board_frequency9_datetime_is_raw_label_not_trusted_source_time(self) -> None:
        adapter = BoardMarketDataAdapter(
            client=FakeBoardClient(
                pd.DataFrame(
                    [
                        {
                            "open": 2392.66,
                            "close": 2369.03,
                            "high": 2398.37,
                            "low": 2351.30,
                            "volume": 76771,
                            "amount": 8476289536,
                            "datetime": "2026-06-10 15:00",
                        },
                        {
                            "open": 2432.28,
                            "close": 2413.50,
                            "high": 2491.55,
                            "low": 2399.27,
                            "volume": 108899,
                            "amount": 12269034496,
                            "datetime": "2026-06-11 15:00",
                        },
                    ]
                )
            )
        )

        snapshot = adapter.fetch_snapshot(sample_board_subscription(), "20260611")

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertNotIn("snapshot_time", snapshot)
        self.assertEqual(snapshot["raw_snapshot_time_label"], "2026-06-11T15:00:00+08:00")
        self.assertEqual(snapshot["source_time_trust_level"], "untrusted_period_label")
        self.assertEqual(snapshot["raw_snapshot_time_semantics"], "tdx_index_frequency_9_period_label")
        self.assertIn("observed_at", snapshot)
        self.assertIn("fetched_at", snapshot)

    def test_board_raw_1500_label_blocks_without_future_event_time(self) -> None:
        execution_time = datetime(2026, 6, 11, 13, 11, tzinfo=timezone(timedelta(hours=8)))
        raw_snapshot = {
            **sample_raw_snapshot(),
            "raw_snapshot_time_label": "2026-06-11T15:00:00+08:00",
            "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
            "source_time_trust_level": "untrusted_period_label",
            "observed_at": "2026-06-11T13:11:00+08:00",
            "fetched_at": "2026-06-11T13:11:00+08:00",
            "raw_payload": {"datetime": "2026-06-11 15:00"},
        }
        conn = FakeConnection()
        adapter = FakeSnapshotAdapter({"board:TDX:881002": raw_snapshot})

        result = execute_one_subscription_snapshot(
            dsn="postgresql://test",
            contract={
                **sample_board_contract(),
                "source_time_policy": {
                    "mode": "strict_live",
                    "future_tolerance_seconds": 120,
                    "board_source_time_label_handling": "P0_BLOCK_NO_OUTBOX",
                },
            },
            subscription=sample_board_subscription(),
            adapter=adapter,
            connection_factory=lambda _dsn: conn,
            snapshot_time=execution_time,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["quality_status"], "failed")
        self.assertEqual(result["source_time_status"], "source_time_untrusted_label")
        self.assertEqual(result["snapshot_rows_written"], 0)
        self.assertEqual(result["outbox_rows_written"], 0)
        self.assertEqual(result["quality_item_rows_written"], 1)
        self.assertEqual(conn.sql_kinds(), ["quality_fact"])

    def test_standard_outbox_future_source_time_blocks_before_any_db_write(self) -> None:
        contract = sample_mult_asset_contract()
        readiness = sample_mult_asset_readiness(contract)
        subscriptions = [
            sample_subscription(),
            sample_index_subscription(),
            sample_board_subscription(),
        ]
        adapter = FakeSnapshotAdapter(
            {
                "stock:SH:600000": {**sample_raw_snapshot(), "snapshot_time": "2026-06-11T13:11:00+08:00"},
                "index:SH:000001": {**sample_raw_snapshot(), "snapshot_time": "2026-06-11T13:11:00+08:00"},
                "board:TDX:881002": {**sample_raw_snapshot(), "snapshot_time": "2026-06-11T15:00:00+08:00"},
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_contract_and_readiness(temp_dir, contract, readiness)
            with patch(
                "ashare_v3.market.realtime_snapshot_execute.capture_snapshot_execute_backup",
                return_value=sample_snapshot_backup(contract),
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.build_realtime_subscription_report",
                return_value={"test": True},
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.realtime_snapshot_subscriptions",
                return_value=subscriptions,
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.fetch_market_data_run_row_by_id",
                return_value=sample_source_run_row(),
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.utc_now_iso",
                return_value="2026-06-11T05:11:00+00:00",
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.insert_snapshot_run"
            ) as insert_run, patch(
                "ashare_v3.market.realtime_snapshot_execute.write_market_snapshot_with_event"
            ) as write_with_event, patch(
                "ashare_v3.market.realtime_snapshot_execute.write_market_quality_fact_only"
            ) as write_quality, patch(
                "ashare_v3.market.realtime_snapshot_execute.write_snapshot_quality_and_finalize_run"
            ) as finalize_run:
                report = run_realtime_daily_snapshot_execute(
                    dsn="postgresql://test",
                    contract_path=paths["contract"],
                    readiness_path=paths["readiness"],
                    pre_backup_path=paths["pre_backup"],
                    post_backup_path=paths["post_backup"],
                    json_report_path=paths["json_report"],
                    markdown_report_path=paths["markdown_report"],
                    for_trade_date=str(contract["for_trade_date"]),
                    snapshot_run_id=str(contract["snapshot_run_id"]),
                    execute=True,
                    user_confirmed=True,
                    allow_outbox=True,
                    adapter=adapter,
                )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["quality"]["p0_count"], 1)
        self.assertEqual(report["write_result"]["snapshot_rows_written"], 0)
        self.assertEqual(report["write_result"]["event_outbox_rows_written"], 0)
        self.assertFalse(report["side_effects"]["writes_performed"])
        self.assertFalse(report["side_effects"]["realtime_snapshot_written"])
        self.assertFalse(report["side_effects"]["event_outbox_written"])
        self.assertEqual(report["atomic_source_time_precheck"]["future_source_time_count"], 1)
        insert_run.assert_not_called()
        write_with_event.assert_not_called()
        write_quality.assert_not_called()
        finalize_run.assert_not_called()

    def test_standard_outbox_board_raw_label_blocks_before_stock_index_writes(self) -> None:
        contract = sample_mult_asset_contract()
        readiness = sample_mult_asset_readiness(contract)
        subscriptions = [
            sample_subscription(),
            sample_index_subscription(),
            sample_board_subscription(),
        ]
        adapter = FakeSnapshotAdapter(
            {
                "stock:SH:600000": {**sample_raw_snapshot(), "snapshot_time": "2026-06-11T13:11:00+08:00"},
                "index:SH:000001": {**sample_raw_snapshot(), "snapshot_time": "2026-06-11T13:11:00+08:00"},
                "board:TDX:881002": {
                    **sample_raw_snapshot(),
                    "raw_snapshot_time_label": "2026-06-11T15:00:00+08:00",
                    "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
                    "source_time_trust_level": "untrusted_period_label",
                    "observed_at": "2026-06-11T13:11:00+08:00",
                    "fetched_at": "2026-06-11T13:11:00+08:00",
                    "raw_payload": {"datetime": "2026-06-11 15:00"},
                },
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_contract_and_readiness(temp_dir, contract, readiness)
            with patch(
                "ashare_v3.market.realtime_snapshot_execute.capture_snapshot_execute_backup",
                return_value=sample_snapshot_backup(contract),
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.build_realtime_subscription_report",
                return_value={"test": True},
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.realtime_snapshot_subscriptions",
                return_value=subscriptions,
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.fetch_market_data_run_row_by_id",
                return_value=sample_source_run_row(),
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.insert_snapshot_run"
            ) as insert_run, patch(
                "ashare_v3.market.realtime_snapshot_execute.write_market_snapshot_with_event"
            ) as write_with_event, patch(
                "ashare_v3.market.realtime_snapshot_execute.write_market_quality_fact_only"
            ) as write_quality, patch(
                "ashare_v3.market.realtime_snapshot_execute.write_snapshot_quality_and_finalize_run"
            ) as finalize_run:
                report = run_realtime_daily_snapshot_execute(
                    dsn="postgresql://test",
                    contract_path=paths["contract"],
                    readiness_path=paths["readiness"],
                    pre_backup_path=paths["pre_backup"],
                    post_backup_path=paths["post_backup"],
                    json_report_path=paths["json_report"],
                    markdown_report_path=paths["markdown_report"],
                    for_trade_date=str(contract["for_trade_date"]),
                    snapshot_run_id=str(contract["snapshot_run_id"]),
                    execute=True,
                    user_confirmed=True,
                    allow_outbox=True,
                    adapter=adapter,
                )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["quality"]["p0_count"], 1)
        self.assertEqual(report["write_result"]["snapshot_rows_written"], 0)
        self.assertEqual(report["write_result"]["event_outbox_rows_written"], 0)
        self.assertEqual(report["atomic_source_time_precheck"]["untrusted_source_time_label_count"], 1)
        insert_run.assert_not_called()
        write_with_event.assert_not_called()
        write_quality.assert_not_called()
        finalize_run.assert_not_called()

    def test_standard_outbox_all_valid_source_times_still_writes_snapshot_and_outbox(self) -> None:
        contract = sample_mult_asset_contract()
        readiness = sample_mult_asset_readiness(contract)
        subscriptions = [
            sample_subscription(),
            sample_index_subscription(),
            sample_board_subscription(),
        ]
        adapter = FakeSnapshotAdapter(
            {
                "stock:SH:600000": {**sample_raw_snapshot(), "snapshot_time": "2026-06-11T13:11:00+08:00"},
                "index:SH:000001": {**sample_raw_snapshot(), "snapshot_time": "2026-06-11T13:11:00+08:00"},
                "board:TDX:881002": {**sample_raw_snapshot(), "snapshot_time": "2026-06-11T13:11:00+08:00"},
            }
        )
        after_backup = sample_snapshot_backup(
            contract,
            row_counts={"stock": 1, "index": 1, "board": 1},
            outbox_count=3,
            outbox_counts_by_type={"MarketSnapshotUpdated": 3},
            snapshot_run_row={"run_id": contract["snapshot_run_id"], "status": "passed"},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_contract_and_readiness(temp_dir, contract, readiness)
            with patch(
                "ashare_v3.market.realtime_snapshot_execute.capture_snapshot_execute_backup",
                side_effect=[sample_snapshot_backup(contract), after_backup, after_backup],
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.build_realtime_subscription_report",
                return_value={"test": True},
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.realtime_snapshot_subscriptions",
                return_value=subscriptions,
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.fetch_market_data_run_row_by_id",
                return_value=sample_source_run_row(),
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.insert_snapshot_run"
            ) as insert_run, patch(
                "ashare_v3.market.realtime_snapshot_execute.write_market_snapshot_with_event"
            ) as write_with_event, patch(
                "ashare_v3.market.realtime_snapshot_execute.open_connection",
                side_effect=lambda _dsn: FakeConnection(),
            ), patch(
                "ashare_v3.market.realtime_snapshot_execute.write_snapshot_quality_and_finalize_run"
            ) as finalize_run:
                report = run_realtime_daily_snapshot_execute(
                    dsn="postgresql://test",
                    contract_path=paths["contract"],
                    readiness_path=paths["readiness"],
                    pre_backup_path=paths["pre_backup"],
                    post_backup_path=paths["post_backup"],
                    json_report_path=paths["json_report"],
                    markdown_report_path=paths["markdown_report"],
                    for_trade_date=str(contract["for_trade_date"]),
                    snapshot_run_id=str(contract["snapshot_run_id"]),
                    execute=True,
                    user_confirmed=True,
                    allow_outbox=True,
                    adapter=adapter,
                )

        self.assertEqual(report.get("result", "EXECUTE_PASS"), "EXECUTE_PASS")
        self.assertEqual(report["write_result"]["snapshot_rows_written"], 3)
        self.assertEqual(report["write_result"]["event_outbox_rows_written"], 3)
        self.assertEqual(report["quality"]["p0_count"], 0)
        insert_run.assert_called_once()
        self.assertEqual(write_with_event.call_count, 3)
        finalize_run.assert_called_once()

    def test_future_source_time_within_tolerance_is_confirmed(self) -> None:
        execution_time = datetime(2026, 6, 11, 13, 11, tzinfo=timezone(timedelta(hours=8)))
        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260611",
                "source_time_policy": {"mode": "strict_live", "future_tolerance_seconds": 120},
            },
            raw_snapshot={**sample_raw_snapshot(), "snapshot_time": "2026-06-11T13:12:59+08:00"},
            default_time=execution_time,
        )

        self.assertEqual(evidence["source_time_status"], "source_time_confirmed")
        self.assertFalse(evidence["source_time_warning"])
        self.assertEqual(evidence["source_time_future_tolerance_seconds"], 120)

    def test_date_mismatch_still_takes_precedence_over_future_guard(self) -> None:
        execution_time = datetime(2026, 6, 11, 13, 11, tzinfo=timezone(timedelta(hours=8)))
        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260611",
                "source_time_policy": {"mode": "strict_live", "future_tolerance_seconds": 120},
            },
            raw_snapshot={**sample_raw_snapshot(), "snapshot_time": "2026-06-12T09:31:00+08:00"},
            default_time=execution_time,
        )

        self.assertEqual(evidence["source_time_status"], "source_time_date_mismatch")

    def test_missing_source_time_pre_open_policy_is_not_future_blocked(self) -> None:
        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "writes_outbox": False,
                "source_time_policy": {"mode": "pre_open_fact_only", "future_tolerance_seconds": 120},
            },
            raw_snapshot={
                "open": 0,
                "high": 0,
                "low": 0,
                "close": 0,
                "current_price": 0,
                "pre_close": 10,
                "volume": 0,
                "amount": 0,
            },
            default_time=sample_snapshot_time(),
        )

        self.assertEqual(evidence["source_time_status"], "source_time_missing_or_preopen")
        self.assertNotEqual(evidence["source_time_status"], "source_time_future")

    def test_successful_snapshot_writes_fact_and_outbox_once(self) -> None:
        conn = FakeConnection()
        adapter = FakeSnapshotAdapter({"stock:SH:600000": sample_raw_snapshot()})

        result = execute_one_subscription_snapshot(
            dsn="postgresql://test",
            contract=sample_contract(),
            subscription=sample_subscription(),
            adapter=adapter,
            connection_factory=lambda _dsn: conn,
            snapshot_time=sample_snapshot_time(),
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["event_type"], "MarketSnapshotUpdated")
        self.assertEqual(result["snapshot_rows_written"], 1)
        self.assertEqual(result["quality_item_rows_written"], 0)
        self.assertEqual(conn.sql_kinds(), ["snapshot_fact", "outbox"])
        self.assertEqual(conn.transaction_commits, 1)
        self.assertEqual(conn.transaction_rollbacks, 0)

    def test_successful_snapshot_fact_only_writes_no_outbox(self) -> None:
        conn = FakeConnection()
        adapter = FakeSnapshotAdapter({"stock:SH:600000": sample_raw_snapshot()})

        result = execute_one_subscription_snapshot(
            dsn="postgresql://test",
            contract={**sample_contract(), "writes_outbox": False},
            subscription=sample_subscription(),
            adapter=adapter,
            connection_factory=lambda _dsn: conn,
            snapshot_time=sample_snapshot_time(),
        )

        self.assertEqual(result["status"], "passed")
        self.assertIsNone(result["event_type"])
        self.assertEqual(result["snapshot_rows_written"], 1)
        self.assertEqual(result["quality_item_rows_written"], 0)
        self.assertEqual(result["outbox_rows_written"], 0)
        self.assertEqual(conn.sql_kinds(), ["snapshot_fact"])
        self.assertEqual(conn.transaction_commits, 1)

    def test_pre_open_fact_only_writes_snapshot_and_records_warning_metadata(self) -> None:
        conn = FakeConnection()
        adapter = FakeSnapshotAdapter(
            {
                "stock:SH:600000": {
                    "open": 0,
                    "high": 0,
                    "low": 0,
                    "close": 0,
                    "current_price": 0,
                    "pre_close": 10,
                    "volume": 0,
                    "amount": 0,
                }
            }
        )

        result = execute_one_subscription_snapshot(
            dsn="postgresql://test",
            contract={
                **sample_contract(),
                "writes_outbox": False,
                "source_time_policy": {"mode": "pre_open_fact_only"},
            },
            subscription=sample_subscription(),
            adapter=adapter,
            connection_factory=lambda _dsn: conn,
            snapshot_time=sample_snapshot_time(),
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["source_time_status"], "source_time_missing_or_preopen")
        self.assertTrue(result["source_time_warning"])
        self.assertEqual(result["snapshot_rows_written"], 1)
        self.assertEqual(result["outbox_rows_written"], 0)
        self.assertEqual(conn.sql_kinds(), ["snapshot_fact"])

    def test_missing_snapshot_outbox_contract_writes_quality_without_non_snapshot_outbox(self) -> None:
        conn = FakeConnection()
        adapter = FakeSnapshotAdapter({})

        result = execute_one_subscription_snapshot(
            dsn="postgresql://test",
            contract=sample_contract(),
            subscription=sample_subscription(),
            adapter=adapter,
            connection_factory=lambda _dsn: conn,
            snapshot_time=sample_snapshot_time(),
        )

        self.assertEqual(result["status"], "missing")
        self.assertIsNone(result["event_type"])
        self.assertEqual(result["snapshot_rows_written"], 0)
        self.assertEqual(result["quality_item_rows_written"], 1)
        self.assertEqual(result["outbox_rows_written"], 0)
        self.assertEqual(conn.sql_kinds(), ["quality_fact"])

    def test_missing_snapshot_fact_only_writes_quality_without_outbox(self) -> None:
        conn = FakeConnection()
        adapter = FakeSnapshotAdapter({})

        result = execute_one_subscription_snapshot(
            dsn="postgresql://test",
            contract={**sample_contract(), "writes_outbox": False},
            subscription=sample_subscription(),
            adapter=adapter,
            connection_factory=lambda _dsn: conn,
            snapshot_time=sample_snapshot_time(),
        )

        self.assertEqual(result["status"], "missing")
        self.assertIsNone(result["event_type"])
        self.assertEqual(result["snapshot_rows_written"], 0)
        self.assertEqual(result["quality_item_rows_written"], 1)
        self.assertEqual(result["outbox_rows_written"], 0)
        self.assertEqual(conn.sql_kinds(), ["quality_fact"])

    def test_adapter_error_outbox_contract_writes_quality_without_non_snapshot_outbox(self) -> None:
        conn = FakeConnection()
        adapter = FakeSnapshotAdapter({}, error=RuntimeError("quote timeout"))

        result = execute_one_subscription_snapshot(
            dsn="postgresql://test",
            contract=sample_contract(),
            subscription=sample_subscription(),
            adapter=adapter,
            connection_factory=lambda _dsn: conn,
            snapshot_time=sample_snapshot_time(),
        )

        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["event_type"])
        self.assertEqual(result["quality_item_rows_written"], 1)
        self.assertEqual(result["outbox_rows_written"], 0)
        self.assertEqual(conn.sql_kinds(), ["quality_fact"])

    def test_snapshot_fact_write_failure_does_not_fallback_to_quality_event(self) -> None:
        conn = FakeConnection(fail_on="stock_realtime_daily_snapshot")
        adapter = FakeSnapshotAdapter({"stock:SH:600000": sample_raw_snapshot()})

        with self.assertRaises(RuntimeError):
            execute_one_subscription_snapshot(
                dsn="postgresql://test",
                contract=sample_contract(),
                subscription=sample_subscription(),
                adapter=adapter,
                connection_factory=lambda _dsn: conn,
                snapshot_time=sample_snapshot_time(),
            )

        self.assertEqual(conn.sql_kinds(), ["snapshot_fact"])
        self.assertEqual(conn.transaction_commits, 0)
        self.assertEqual(conn.transaction_rollbacks, 1)

    def test_allowed_write_tables_exclude_downstream_and_minute_tables(self) -> None:
        allowed_text = " ".join(ALLOWED_B1_WRITE_TABLES)
        self.assertIn("stock_realtime_daily_snapshot", allowed_text)
        self.assertIn("common_event_outbox", allowed_text)
        for marker in FORBIDDEN_B1_WRITE_TABLE_MARKERS:
            self.assertNotIn(marker, allowed_text)

    def test_fact_only_allowed_write_tables_exclude_outbox_and_downstream(self) -> None:
        allowed_text = " ".join(ALLOWED_B1_FACT_ONLY_WRITE_TABLES)
        self.assertIn("stock_realtime_daily_snapshot", allowed_text)
        self.assertIn("common_market_data_quality_item", allowed_text)
        self.assertNotIn("common_event_outbox", allowed_text)
        for marker in FORBIDDEN_B1_WRITE_TABLE_MARKERS:
            self.assertNotIn(marker, allowed_text)

    def test_fact_only_postcheck_requires_scoped_event_refs_zero(self) -> None:
        contract = {**sample_contract(), "writes_outbox": False}
        data_snapshot = {
            "target_snapshot_run_counts_by_asset": {
                "stock": {"snapshot_row_count": 1, "snapshot_object_count": 1},
                "index": {"snapshot_row_count": 0, "snapshot_object_count": 0},
                "board": {"snapshot_row_count": 0, "snapshot_object_count": 0},
            },
            "snapshot_outbox_counts_by_type": {},
            "snapshot_outbox_row_count": 0,
            "downstream_inbox_row_count": 0,
            "checkpoint_ref_count": 0,
            "duplicate_snapshot_key_count_by_asset": {"stock": 0, "index": 0, "board": 0},
            "physical_isolation_violation_count_by_asset": {"stock": 0, "index": 0, "board": 0},
        }
        object_results = [
            {
                "asset_kind": "stock",
                "status": "passed",
                "snapshot_rows_written": 1,
                "quality_item_rows_written": 0,
                "outbox_rows_written": 0,
            }
        ]

        checks = build_post_execute_checks(
            contract=contract,
            data_snapshot=data_snapshot,
            object_results=object_results,
        )
        quality_items = build_post_execute_quality_items(
            contract=contract,
            post_checks=checks,
            object_results=object_results,
        )
        failed_codes = {item["gate_code"] for item in quality_items if item["status"] == "failed"}

        self.assertTrue(checks["n3_b1_writes_outbox_false"])
        self.assertTrue(checks["n3_b1_scoped_event_refs_zero"])
        self.assertNotIn("n3_b1_writes_outbox_false", failed_codes)

    def test_post_quality_records_pre_open_source_time_as_p1(self) -> None:
        checks = {
            "n3_b1_snapshot_object_count_matches_b0": True,
            "n3_b1_expected_snapshot_object_counts": {"stock": 1, "index": 0, "board": 0},
            "n3_b1_actual_snapshot_object_counts": {"stock": 1, "index": 0, "board": 0},
            "n3_b1_snapshot_rows_reasonable": True,
            "n3_b1_actual_snapshot_rows_by_asset": {"stock": 1, "index": 0, "board": 0},
            "n3_b1_writes_outbox_false": True,
            "n3_b1_scoped_event_refs_zero": True,
            "n3_b1_scoped_event_refs": {
                "common_event_outbox": 0,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
            },
            "n3_b1_duplicate_snapshot_key_zero": True,
            "n3_b1_duplicate_snapshot_key_count_by_asset": {"stock": 0, "index": 0, "board": 0},
            "n3_b1_physical_table_isolation": True,
            "n3_b1_physical_isolation_violation_count_by_asset": {"stock": 0, "index": 0, "board": 0},
            "n3_b1_no_downstream_consumption_before_rollback": True,
            "n3_b1_outbox_counts_by_type": {},
        }
        quality_items = build_post_execute_quality_items(
            contract={**sample_contract(), "writes_outbox": False},
            post_checks=checks,
            object_results=[
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "subscription_id": 11,
                    "status": "passed",
                    "source_time_status": "source_time_missing_or_preopen",
                    "source_time_warning": True,
                }
            ],
        )

        source_time_items = [
            item for item in quality_items if item["gate_code"] == "n3_b1_pre_open_source_time_not_confirmed"
        ]
        self.assertEqual(len(source_time_items), 1)
        self.assertEqual(source_time_items[0]["severity"], "P1")
        self.assertEqual(source_time_items[0]["status"], "warning")

    def test_board_adapter_maps_tail_trade_date_row(self) -> None:
        adapter = BoardMarketDataAdapter(
            client=FakeBoardClient(
                pd.DataFrame(
                    [
                        {
                            "open": 2392.66,
                            "close": 2369.03,
                            "high": 2398.37,
                            "low": 2351.30,
                            "vol": 76771,
                            "amount": 8476289536,
                            "datetime": "2026-05-22 15:00",
                            "up_count": 6,
                            "down_count": 18,
                        },
                        {
                            "open": 2432.28,
                            "close": 2413.50,
                            "high": 2491.55,
                            "low": 2399.27,
                            "volume": 108899,
                            "amount": 12269034496,
                            "datetime": "2026-05-25 15:00",
                            "up_count": 22,
                            "down_count": 2,
                        },
                    ]
                )
            )
        )

        snapshot = adapter.fetch_snapshot(sample_board_subscription(), "20260525")

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["open"], 2432.28)
        self.assertEqual(snapshot["close"], 2413.50)
        self.assertEqual(snapshot["current_price"], 2413.50)
        self.assertEqual(snapshot["pre_close"], 2369.03)
        self.assertEqual(snapshot["volume"], 108899)
        self.assertEqual(snapshot["amount"], 12269034496)
        self.assertEqual(snapshot["source_path"], "std.index")
        self.assertEqual(snapshot["adapter_name"], "BoardMarketDataAdapter")
        self.assertEqual(snapshot["raw_payload"]["up_count"], 22)
        self.assertEqual(snapshot["raw_payload"]["down_count"], 2)

    def test_board_adapter_empty_result_is_missing(self) -> None:
        adapter = BoardMarketDataAdapter(client=FakeBoardClient(pd.DataFrame()))

        self.assertIsNone(adapter.fetch_snapshot(sample_board_subscription(), "20260525"))

    def test_board_adapter_trade_date_mismatch_is_missing(self) -> None:
        adapter = BoardMarketDataAdapter(
            client=FakeBoardClient(
                pd.DataFrame(
                    [
                        {
                            "open": 2392.66,
                            "close": 2369.03,
                            "high": 2398.37,
                            "low": 2351.30,
                            "volume": 76771,
                            "amount": 8476289536,
                            "datetime": "2026-05-22 15:00",
                        }
                    ]
                )
            )
        )

        self.assertIsNone(adapter.fetch_snapshot(sample_board_subscription(), "20260525"))

    def test_asset_router_routes_stock_to_default_and_index_to_index_adapter(self) -> None:
        default_adapter = RecordingSnapshotAdapter({"default": sample_raw_snapshot()})
        index_adapter = RecordingSnapshotAdapter({"index": sample_raw_snapshot()})
        board_adapter = RecordingSnapshotAdapter({"board": sample_raw_snapshot()})
        router = AssetRoutingRealtimeSnapshotAdapter(
            default_adapter=default_adapter,
            index_adapter=index_adapter,
            board_adapter=board_adapter,
        )

        self.assertEqual(router.fetch_snapshot(sample_subscription(), "20260525"), sample_raw_snapshot())
        self.assertEqual(router.fetch_snapshot(sample_index_subscription(), "20260525"), sample_raw_snapshot())

        self.assertEqual(default_adapter.calls, ["stock:SH:600000"])
        self.assertEqual(index_adapter.calls, ["index:SH:000001"])
        self.assertEqual(board_adapter.calls, [])

    def test_asset_router_routes_tdx_881_board_to_board_adapter(self) -> None:
        default_adapter = RecordingSnapshotAdapter({"default": sample_raw_snapshot()})
        board_adapter = RecordingSnapshotAdapter({"board": sample_raw_snapshot()})
        router = AssetRoutingRealtimeSnapshotAdapter(
            default_adapter=default_adapter,
            board_adapter=board_adapter,
        )

        self.assertEqual(router.fetch_snapshot(sample_board_subscription(), "20260525"), sample_raw_snapshot())

        self.assertEqual(default_adapter.calls, [])
        self.assertEqual(board_adapter.calls, ["board:TDX:881002"])

    def test_asset_router_routes_tdx_880_board_to_board_adapter(self) -> None:
        default_adapter = RecordingSnapshotAdapter({"default": sample_raw_snapshot()})
        board_adapter = RecordingSnapshotAdapter({"board": sample_raw_snapshot()})
        router = AssetRoutingRealtimeSnapshotAdapter(
            default_adapter=default_adapter,
            board_adapter=board_adapter,
        )

        self.assertEqual(router.fetch_snapshot(sample_region_board_subscription(), "20260602"), sample_raw_snapshot())

        self.assertEqual(default_adapter.calls, [])
        self.assertEqual(board_adapter.calls, ["board:TDX:880201"])

    def test_asset_router_routes_bj_index_to_bj_index_adapter(self) -> None:
        default_adapter = RecordingSnapshotAdapter({"default": sample_raw_snapshot()})
        index_adapter = RecordingSnapshotAdapter({"index": sample_raw_snapshot()})
        board_adapter = RecordingSnapshotAdapter({"board": sample_raw_snapshot()})
        bj_index_adapter = RecordingSnapshotAdapter({"default": sample_raw_snapshot()})
        router = AssetRoutingRealtimeSnapshotAdapter(
            default_adapter=default_adapter,
            index_adapter=index_adapter,
            board_adapter=board_adapter,
            bj_index_adapter=bj_index_adapter,
        )

        self.assertEqual(router.fetch_snapshot(sample_bj_index_subscription(), "20260602"), sample_raw_snapshot())

        self.assertEqual(default_adapter.calls, [])
        self.assertEqual(index_adapter.calls, [])
        self.assertEqual(board_adapter.calls, [])
        self.assertEqual(bj_index_adapter.calls, ["index:BJ:899050"])

    def test_index_adapter_uses_mootdx_index_path_with_untrusted_period_label(self) -> None:
        adapter = IndexMarketDataAdapter(
            client=FakeIndexClient(
                pd.DataFrame(
                    [
                        {
                            "open": 3200.0,
                            "close": 3210.0,
                            "high": 3220.0,
                            "low": 3190.0,
                            "volume": 1200,
                            "amount": 330000000,
                            "datetime": "2026-06-12 15:00",
                        }
                    ]
                )
            )
        )

        snapshot = adapter.fetch_snapshot(sample_index_subscription(), "20260612")

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["current_price"], 3210.0)
        self.assertNotIn("snapshot_time", snapshot)
        self.assertEqual(snapshot["raw_snapshot_time_semantics"], "tdx_index_frequency_9_period_label")
        self.assertEqual(snapshot["source_time_trust_level"], "untrusted_period_label")
        self.assertEqual(snapshot["raw_route_market"], 1)
        self.assertEqual(snapshot["raw_route_code"], "000001")
        self.assertEqual(adapter._client.calls, [{"symbol": "000001", "frequency": 9, "start": 0, "offset": 5}])

    def test_index_untrusted_period_label_normalizes_under_reviewed_policy(self) -> None:
        raw_snapshot = {
            "current_price": 3210.0,
            "raw_snapshot_time_label": "2026-06-12T15:00:00+08:00",
            "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
            "source_time_trust_level": "untrusted_period_label",
            "observed_at": "2026-06-12T09:32:10+08:00",
            "fetched_at": "2026-06-12T09:32:10+08:00",
        }

        evidence = build_snapshot_source_time_evidence(
            contract={
                **sample_contract(),
                "for_trade_date": "20260612",
                "source_time_policy": {
                    "mode": "strict_live",
                    "board_source_time_label_handling": "NORMALIZE_TO_OBSERVED_AT",
                    "normalize_to_observed_at_enabled": True,
                },
            },
            raw_snapshot=raw_snapshot,
            default_time=datetime(2026, 6, 12, 9, 32, 11, tzinfo=timezone(timedelta(hours=8))),
        )

        self.assertEqual(evidence["source_time_status"], "source_time_label_normalized")
        self.assertEqual(evidence["snapshot_time_policy"], "observed_at_when_raw_source_time_is_label")

    def test_tushare_bj_index_adapter_maps_index_daily_row(self) -> None:
        adapter = TushareBjIndexSnapshotAdapter(
            client=FakeTushareClient(
                {
                    "20260602": pd.DataFrame(
                        [
                            {
                                "ts_code": "899050.BJ",
                                "trade_date": "20260602",
                                "open": 1210.1,
                                "high": 1222.2,
                                "low": 1201.5,
                                "close": 1218.8,
                                "pre_close": 1209.9,
                                "vol": 88.0,
                                "amount": 99.0,
                            }
                        ]
                    )
                }
            )
        )

        snapshot = adapter.fetch_snapshot(sample_bj_index_subscription(), "20260602")

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["open"], 1210.1)
        self.assertEqual(snapshot["close"], 1218.8)
        self.assertEqual(snapshot["current_price"], 1218.8)
        self.assertEqual(snapshot["pre_close"], 1209.9)
        self.assertEqual(snapshot["volume"], 88.0)
        self.assertEqual(snapshot["amount"], 99.0)
        self.assertEqual(snapshot["source_path"], "tushare.index_daily")
        self.assertEqual(snapshot["external_source"], "tushare")
        self.assertIsNone(snapshot.get("snapshot_time"))

    def test_tushare_bj_index_adapter_uses_previous_close_bootstrap_when_current_day_missing(self) -> None:
        adapter = TushareBjIndexSnapshotAdapter(
            client=FakeTushareClient(
                {
                    "20260602": pd.DataFrame(),
                    "20260601": pd.DataFrame(
                        [
                            {
                                "ts_code": "899050.BJ",
                                "trade_date": "20260601",
                                "open": 1200.1,
                                "high": 1215.2,
                                "low": 1199.5,
                                "close": 1212.8,
                                "pre_close": 1208.0,
                                "vol": 77.0,
                                "amount": 88.0,
                            }
                        ]
                    ),
                }
            )
        )

        snapshot = adapter.fetch_snapshot({**sample_bj_index_subscription(), "prev_trade_date": "20260601"}, "20260602")

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["open"], 1212.8)
        self.assertEqual(snapshot["high"], 1212.8)
        self.assertEqual(snapshot["low"], 1212.8)
        self.assertEqual(snapshot["close"], 1212.8)
        self.assertEqual(snapshot["current_price"], 1212.8)
        self.assertEqual(snapshot["pre_close"], 1212.8)
        self.assertEqual(snapshot["volume"], 0)
        self.assertEqual(snapshot["amount"], 0)
        self.assertEqual(snapshot["source_path"], "tushare.index_daily.previous_trade_date_bootstrap")
        self.assertTrue(snapshot["raw_payload"]["previous_trade_date_bootstrap"])
        self.assertEqual(snapshot["raw_payload"]["source_trade_date"], "20260601")


def sample_contract() -> dict[str, object]:
    return {
        "stage": "N3-B1-preflight",
        "layer_role": "N3_market_data",
        "source_run_id": "market_data_subscription_test",
        "market_data_run_id": "market_data_subscription_test",
        "snapshot_run_id": "realtime_daily_snapshot_20260525__market_data_subscription_test",
        "source_condition_run_id": "condition_layer_test",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
        "expected_row_count": 1,
        "writes_outbox": True,
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
        "source_adapter_plan": [
            {
                "asset_kind": "stock",
                "source_pull_plan_id": 22,
                "adapter_name": "StockMarketDataAdapter",
            }
        ],
    }


def sample_board_contract() -> dict[str, object]:
    return {
        **sample_contract(),
        "for_trade_date": "20260611",
        "source_trade_date": "20260610",
        "prev_trade_date": "20260610",
        "snapshot_run_id": "realtime_daily_snapshot_20260611_standard_outbox_test",
        "source_adapter_plan": [
            {
                "asset_kind": "board",
                "source_pull_plan_id": 163,
                "adapter_name": "BoardMarketDataAdapter",
            }
        ],
    }


def sample_index_contract() -> dict[str, object]:
    return {
        **sample_contract(),
        "for_trade_date": "20260612",
        "source_trade_date": "20260611",
        "prev_trade_date": "20260611",
        "snapshot_run_id": "realtime_daily_snapshot_20260612_standard_outbox_test",
        "source_adapter_plan": [
            {
                "asset_kind": "index",
                "source_pull_plan_id": 166,
                "adapter_name": "IndexMarketDataAdapter",
            }
        ],
    }


def sample_mult_asset_contract() -> dict[str, object]:
    return {
        **sample_contract(),
        "for_trade_date": "20260611",
        "source_trade_date": "20260610",
        "prev_trade_date": "20260610",
        "source_run_id": "market_data_subscription_20260611_test",
        "market_data_run_id": "market_data_subscription_20260611_test",
        "snapshot_run_id": "realtime_daily_snapshot_20260611_standard_outbox_test",
        "source_condition_run_id": "condition_layer_20260610_test",
        "expected_row_count": 3,
        "expected_asset_counts": {
            "stock": {"subscription_count": 1, "object_count": 1},
            "index": {"subscription_count": 1, "object_count": 1},
            "board": {"subscription_count": 1, "object_count": 1},
        },
        "source_time_policy": {
            "mode": "strict_live",
            "source_time_future_guard_enabled": True,
            "future_tolerance_seconds": 120,
            "future_source_time_handling": "P0_BLOCK_NO_OUTBOX",
        },
        "event_contract": {"generated_outbox_events_in_b1_default": ["MarketSnapshotUpdated"]},
        "source_adapter_plan": [
            {
                "asset_kind": "stock",
                "source_pull_plan_id": 169,
                "adapter_name": "StockMarketDataAdapter",
            },
            {
                "asset_kind": "index",
                "source_pull_plan_id": 166,
                "adapter_name": "IndexMarketDataAdapter",
            },
            {
                "asset_kind": "board",
                "source_pull_plan_id": 163,
                "adapter_name": "BoardMarketDataAdapter",
            },
        ],
    }


def sample_readiness() -> dict[str, object]:
    return {
        "stage": "N3-B1-readiness-gate",
        "ready": True,
        "blocked": False,
        "source_run_id": "market_data_subscription_test",
        "snapshot_run_id": "realtime_daily_snapshot_20260525__market_data_subscription_test",
        "for_trade_date": "20260525",
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
    }


def sample_mult_asset_readiness(contract: dict[str, object]) -> dict[str, object]:
    return {
        **sample_readiness(),
        "source_run_id": contract["source_run_id"],
        "snapshot_run_id": contract["snapshot_run_id"],
        "for_trade_date": contract["for_trade_date"],
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
    }


def write_contract_and_readiness(temp_dir: str, contract: dict[str, object], readiness: dict[str, object]) -> dict[str, str]:
    root = Path(temp_dir)
    contract_path = root / "contract.json"
    readiness_path = root / "readiness.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    readiness_path.write_text(json.dumps(readiness, ensure_ascii=False), encoding="utf-8")
    return {
        "contract": str(contract_path),
        "readiness": str(readiness_path),
        "pre_backup": str(root / "pre_backup.json"),
        "post_backup": str(root / "post_backup.json"),
        "json_report": str(root / "report.json"),
        "markdown_report": str(root / "report.md"),
    }


def sample_snapshot_backup(
    contract: dict[str, object],
    *,
    row_counts: dict[str, int] | None = None,
    outbox_count: int = 0,
    outbox_counts_by_type: dict[str, int] | None = None,
    snapshot_run_row: dict[str, object] | None = None,
) -> dict[str, object]:
    row_counts = row_counts or {"stock": 0, "index": 0, "board": 0}
    snapshot_run_id = str(contract["snapshot_run_id"])
    source_run_id = str(contract["source_run_id"])
    for_trade_date = str(contract["for_trade_date"])
    target_snapshot_counts = {
        "stock_realtime_daily_snapshot": int(row_counts.get("stock") or 0),
        "index_realtime_daily_snapshot": int(row_counts.get("index") or 0),
        "board_realtime_daily_snapshot": int(row_counts.get("board") or 0),
        "common_market_data_quality_item": 0,
        "common_market_data_run": 0 if snapshot_run_row is None else 1,
        "common_event_outbox": outbox_count,
        "for_trade_date_marker": 1,
    }
    return {
        "phase": "test",
        "captured_at": "2026-06-11T05:11:00+00:00",
        "source_run_id": source_run_id,
        "snapshot_run_id": snapshot_run_id,
        "for_trade_date": for_trade_date,
        "active_snapshot": {},
        "snapshot_run_exists": False,
        "snapshot_run_row": snapshot_run_row,
        "source_run_row": sample_source_run_row(),
        "target_table_row_counts": {},
        "target_snapshot_run_row_counts": target_snapshot_counts,
        "target_snapshot_run_counts_by_asset": {
            asset: {"snapshot_row_count": int(row_counts.get(asset) or 0), "snapshot_object_count": int(row_counts.get(asset) or 0)}
            for asset in ("stock", "index", "board")
        },
        "duplicate_snapshot_key_count_by_asset": {"stock": 0, "index": 0, "board": 0},
        "physical_isolation_violation_count_by_asset": {"stock": 0, "index": 0, "board": 0},
        "snapshot_outbox_row_count": outbox_count,
        "snapshot_outbox_counts_by_type": outbox_counts_by_type or {},
        "downstream_inbox_row_count": 0,
        "checkpoint_ref_count": 0,
    }


def sample_source_run_row() -> dict[str, object]:
    return {
        "run_id": "market_data_subscription_20260611_test",
        "source_condition_run_id": "condition_layer_20260610_test",
        "for_trade_date": "20260611",
        "source_trade_date": "20260610",
        "prev_trade_date": "20260610",
        "mode": "execute",
        "status": "passed",
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 0,
        "source_scope_row_count": 3,
        "candidate_row_count": 3,
        "subscription_row_count": 3,
        "subscription_object_count": 3,
        "dedup_ratio": 1,
        "market_data_pulled": False,
        "market_data_fact_written": False,
        "downstream_layers_touched": False,
        "worker_started": False,
    }


def sample_subscription() -> dict[str, object]:
    return {
        "asset_kind": "stock",
        "subscription_id": 11,
        "identity_key": "stock:SH:600000",
        "exchange": "SH",
        "code": "600000",
        "display_code": "600000.SH",
        "name": "浦发银行",
        "source_scope_ids": [1, 2],
        "source_condition_pool_ids": [101, 102],
    }


def sample_index_subscription() -> dict[str, object]:
    return {
        "asset_kind": "index",
        "subscription_id": 12,
        "identity_key": "index:SH:000001",
        "exchange": "SH",
        "code": "000001",
        "display_code": "000001.SH",
        "name": "上证指数",
        "source_scope_ids": [3],
        "source_condition_pool_ids": [103],
    }


def sample_board_subscription() -> dict[str, object]:
    return {
        "asset_kind": "board",
        "subscription_id": 13,
        "identity_key": "board:TDX:881002",
        "exchange": "TDX",
        "code": "881002",
        "display_code": "881002",
        "name": "煤炭开采",
        "source_scope_ids": [4],
        "source_condition_pool_ids": [104],
    }


def sample_region_board_subscription() -> dict[str, object]:
    return {
        "asset_kind": "board",
        "subscription_id": 14,
        "identity_key": "board:TDX:880201",
        "exchange": "TDX",
        "code": "880201",
        "display_code": "880201",
        "name": "黑龙江",
        "source_scope_ids": [5],
        "source_condition_pool_ids": [105],
    }


def sample_bj_index_subscription() -> dict[str, object]:
    return {
        "asset_kind": "index",
        "subscription_id": 15,
        "identity_key": "index:BJ:899050",
        "exchange": "BJ",
        "code": "899050",
        "display_code": "899050.BJ",
        "name": "北证50",
        "source_scope_ids": [6],
        "source_condition_pool_ids": [106],
    }


def sample_raw_snapshot() -> dict[str, object]:
    return {
        "open": 10,
        "high": 10.2,
        "low": 9.9,
        "close": 10.1,
        "current_price": 10.1,
        "pre_close": 10,
        "volume": 1000,
        "amount": 10100,
    }


def sample_snapshot_time() -> datetime:
    return datetime(2026, 5, 25, 1, 31, 3, tzinfo=timezone.utc)


class FakeSnapshotAdapter:
    source_version = "fake-snapshot-v1"
    external_source = "fake"

    def __init__(self, rows: dict[str, dict[str, object]], error: Exception | None = None) -> None:
        self.rows = rows
        self.error = error

    def fetch_snapshot(self, subscription: dict[str, object], trade_date: str) -> dict[str, object] | None:
        if self.error is not None:
            raise self.error
        return self.rows.get(str(subscription["identity_key"]))


class FakeBoardClient:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[dict[str, object]] = []

    def index(self, *, symbol: str, frequency: int, start: int, offset: int) -> pd.DataFrame:
        self.calls.append({"symbol": symbol, "frequency": frequency, "start": start, "offset": offset})
        return self.frame


class FakeIndexClient:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[dict[str, object]] = []

    def index(self, *, symbol: str, frequency: int, start: int, offset: int) -> pd.DataFrame:
        self.calls.append({"symbol": symbol, "frequency": frequency, "start": start, "offset": offset})
        return self.frame


class FakeTushareClient:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames
        self.calls: list[dict[str, object]] = []

    def index_daily(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(dict(kwargs))
        return self.frames.get(str(kwargs.get("start_date")), pd.DataFrame())


class RecordingSnapshotAdapter:
    source_version = "recording-v1"
    external_source = "recording"

    def __init__(self, rows: dict[str, dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[str] = []

    def fetch_snapshot(self, subscription: dict[str, object], trade_date: str) -> dict[str, object] | None:
        del trade_date
        self.calls.append(str(subscription["identity_key"]))
        asset_kind = str(subscription["asset_kind"])
        if asset_kind in self.rows:
            return self.rows.get(asset_kind)
        return self.rows.get("default")


class FakeConnection:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.executed_sql: list[str] = []
        self.last_sql = ""
        self.transaction_commits = 0
        self.transaction_rollbacks = 0

    def transaction(self) -> "FakeTransaction":
        return FakeTransaction(self)

    def cursor(self) -> "FakeCursor":
        return FakeCursor(self)

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def sql_kinds(self) -> list[str]:
        kinds = []
        for sql in self.executed_sql:
            if "common_event_outbox" in sql:
                kinds.append("outbox")
            elif "common_market_data_quality_item" in sql:
                kinds.append("quality_fact")
            elif "realtime_daily_snapshot" in sql:
                kinds.append("snapshot_fact")
        return kinds


class FakeTransaction:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def __enter__(self) -> "FakeTransaction":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1
        return False


class FakeCursor:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def execute(self, sql: str, params=None) -> None:  # noqa: ANN001
        self.conn.last_sql = sql
        self.conn.executed_sql.append(sql)
        if self.conn.fail_on and self.conn.fail_on in sql:
            raise RuntimeError(f"forced failure on {self.conn.fail_on}")

    def fetchone(self):  # noqa: ANN201
        if "realtime_daily_snapshot" in self.conn.last_sql:
            return {"snapshot_id": 101}
        if "common_market_data_quality_item" in self.conn.last_sql:
            return {"quality_item_id": 303}
        if "common_event_outbox" in self.conn.last_sql:
            return {"event_id": "event-test"}
        return {"id": 1}


if __name__ == "__main__":
    unittest.main()
