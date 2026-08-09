import inspect
from pathlib import Path
import tempfile
import unittest
from datetime import datetime

from ashare_v3.market import today_minute_execute
from ashare_v3.market.today_minute_execute import (
    ASIA_SHANGHAI,
    MootdxTodayMinuteAdapter,
    TodayMinuteExecuteError,
    build_post_execute_checks,
    build_post_execute_quality_items,
    build_today_minute_fact_records,
    classify_today_minute_object_status,
    commit_today_minute_attempt_transaction,
    ensure_executable_plan,
    filter_closed_today_minute_rows,
    prepare_mootdx_today_minute_batch,
    write_prepared_today_minute_batch,
)
from ashare_v3.market.mootdx_batch_attempt import MootdxBatchAttemptOutcome
from ashare_v3.mootdx_client import EndpointConfig, MootdxEndpointManager


class TdxConnectionError(Exception):
    pass


class TodayMinuteExecuteTest(unittest.TestCase):
    def test_local_program_error_does_not_failover_or_open_endpoint_circuit(self) -> None:
        plan = {**sample_c0_plan(), "expected_bar_count_per_object": 1}
        with tempfile.TemporaryDirectory() as tmp:
            manager = fake_endpoint_manager(Path(tmp) / "health.json", mode="active")
            calls: list[str] = []

            class ProgramBugClient:
                def bars(self, **kwargs):  # noqa: ANN003, ANN201
                    raise KeyError("local minute contract bug")

            prepared, outcome = prepare_mootdx_today_minute_batch(
                plan=plan,
                subscriptions=[sample_subscription()],
                manager=manager,
                probe=passing_probe,
                client_factory=lambda selection: calls.append(selection.endpoint_id) or ProgramBugClient(),
            )

            self.assertEqual(
                manager._health_for("primary", transport="mootdx").state,
                "healthy",
            )

        self.assertEqual(calls, ["primary"])
        self.assertEqual(prepared, [])
        self.assertEqual(outcome.attempts[0]["failure_kind"], "unclassified_program_failure")
        self.assertFalse(outcome.attempts[0]["retry_allowed"])

    def test_today_minute_adapter_requires_manager_pinned_client(self) -> None:
        with self.assertRaisesRegex(TodayMinuteExecuteError, "manager-selected pinned client"):
            MootdxTodayMinuteAdapter()

    def test_active_batch_replays_all_today_minutes_once_and_traces_secondary(self) -> None:
        plan = {
            **sample_c0_plan(),
            "expected_bar_count_per_object": 1,
            "expected_minute_rows": 1,
            "expected_minute_rows_by_asset_kind": {"stock": 1, "index": 0, "board": 0},
        }
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def client_factory(selection):  # noqa: ANN001, ANN202
                calls.append(selection.endpoint_id)
                return FailingMinuteClient() if selection.endpoint_id == "primary" else FakeMootdxClient()

            prepared, outcome = prepare_mootdx_today_minute_batch(
                plan=plan,
                subscriptions=[sample_subscription()],
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_probe,
                client_factory=client_factory,
            )

        self.assertEqual(calls, ["primary", "secondary"])
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(len(prepared[0]["minute_records"]), 1)
        raw_json = prepared[0]["minute_records"][0]["raw_json"]
        self.assertEqual(raw_json["endpoint_id"], "secondary")
        self.assertEqual(raw_json["attempt_id"], f"{plan['today_minute_run_id']}__attempt_2")

    def test_observe_batch_failure_returns_no_today_minute_records(self) -> None:
        plan = {**sample_c0_plan(), "expected_bar_count_per_object": 1}
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []
            prepared, outcome = prepare_mootdx_today_minute_batch(
                plan=plan,
                subscriptions=[sample_subscription()],
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="observe"),
                probe=passing_probe,
                client_factory=lambda selection: calls.append(selection.endpoint_id) or FailingMinuteClient(),
            )

        self.assertEqual(calls, ["primary"])
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(prepared, [])

    def test_multi_object_partial_attempt_is_discarded_and_secondary_restarts_from_first(self) -> None:
        plan = {
            **sample_c0_plan(),
            "expected_bar_count_per_object": 1,
            "today_minute_object_count_by_asset_kind": {"stock": 2, "index": 0, "board": 0},
        }
        second = {**sample_subscription(), "subscription_id": 12, "identity_key": "stock:SH:600001", "code": "600001"}
        business_calls: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_today_minute_batch(
                plan=plan,
                subscriptions=[sample_subscription(), second],
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_probe,
                client_factory=lambda selection: PartialMinuteClient(selection.endpoint_id, business_calls),
            )

        self.assertEqual(
            business_calls,
            [
                ("primary", "600000"),
                ("primary", "600001"),
                ("secondary", "600000"),
                ("secondary", "600001"),
            ],
        )
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(len(prepared), 2)
        self.assertTrue(
            all(row["raw_json"]["endpoint_id"] == "secondary" for item in prepared for row in item["minute_records"])
        )

    def test_one_empty_then_nonempty_is_object_quality_without_secondary_fetch(self) -> None:
        plan = {**sample_c0_plan(), "expected_bar_count_per_object": 1}
        subscriptions = [
            sample_subscription(),
            {**sample_subscription(), "subscription_id": 12, "identity_key": "stock:SH:600001", "code": "600001"},
        ]
        calls: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_today_minute_batch(
                plan=plan,
                subscriptions=subscriptions,
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_probe,
                client_factory=lambda selection: EmptyThenNonemptyMinuteClient(selection.endpoint_id, calls),
            )

        self.assertEqual(calls, [("primary", "600000"), ("primary", "600001")])
        self.assertEqual(outcome.status, "passed")
        self.assertEqual([item["status"] for item in prepared], ["failed", "passed"])
        self.assertEqual(prepared[0]["minute_records"], [])

    def test_three_consecutive_empty_today_objects_replay_secondary_from_first(self) -> None:
        plan = {**sample_c0_plan(), "expected_bar_count_per_object": 1}
        subscriptions = [
            {**sample_subscription(), "subscription_id": 11 + index, "identity_key": f"stock:SH:60000{index}", "code": f"60000{index}"}
            for index in range(3)
        ]
        calls: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_today_minute_batch(
                plan=plan,
                subscriptions=subscriptions,
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_probe,
                client_factory=lambda selection: EmptyPrimaryMinuteClient(selection.endpoint_id, calls),
            )

        self.assertEqual(
            calls,
            [
                ("primary", "600000"),
                ("primary", "600001"),
                ("primary", "600002"),
                ("secondary", "600000"),
                ("secondary", "600001"),
                ("secondary", "600002"),
            ],
        )
        self.assertEqual(outcome.status, "passed")
        self.assertTrue(all(item["status"] == "passed" for item in prepared))

    def test_winning_batch_db_failure_rolls_back_single_outer_transaction(self) -> None:
        conn = AtomicBatchConnection(fail_on_call=2)
        prepared = [
            {"subscription": sample_subscription(), "minute_records": [{"raw_json": {}, "record": 1}]},
            {
                "subscription": {**sample_subscription(), "identity_key": "stock:SH:600001"},
                "minute_records": [{"raw_json": {}, "record": 2}],
            },
        ]

        with self.assertRaises(RuntimeError):
            write_prepared_today_minute_batch(
                dsn="unused",
                prepared=prepared,
                connection_factory=lambda dsn: conn,
            )

        self.assertEqual(conn.executemany_calls, 2)
        self.assertEqual(conn.transaction_commits, 0)
        self.assertEqual(conn.transaction_rollbacks, 1)

    def test_run_insert_and_winning_batch_share_one_outer_transaction(self) -> None:
        conn = AtomicBatchConnection(fail_on_call=99)
        prepared = [
            {
                "subscription": sample_subscription(),
                "minute_records": [],
                "status": "failed",
                "expected_bar_count": 1,
                "actual_bar_count": 0,
                "error_message": "object missing",
                "mootdx_batch_attempt": {"winning_attempt_id": "attempt-1", "attempts": []},
            }
        ]

        results = write_prepared_today_minute_batch(
            dsn="unused",
            prepared=prepared,
            connection_factory=lambda dsn: conn,
            run_context=(sample_c0_plan(), {}, "2026-05-25T01:00:00+00:00", "plan.json"),
        )

        self.assertEqual(conn.execute_calls, 1)
        self.assertEqual(conn.transaction_commits, 1)
        self.assertEqual(conn.transaction_rollbacks, 0)
        self.assertEqual(
            results[0]["quality_visible"]["mootdx_batch_attempt"]["winning_attempt_id"],
            "attempt-1",
        )
        run_raw_json = getattr(conn.execute_values[0][-1], "obj", conn.execute_values[0][-1])
        self.assertEqual(run_raw_json["mootdx_batch_attempt"]["winning_attempt_id"], "attempt-1")

    def test_finalizer_failure_rolls_back_run_facts_and_quality_outer_transaction(self) -> None:
        conn = AtomicBatchConnection(fail_on_call=99)
        outcome = MootdxBatchAttemptOutcome(
            batch_id="batch",
            status="failed",
            result=None,
            winning_attempt_id=None,
            attempts=({"attempt_id": "attempt-1", "status": "failed"},),
        )
        snapshot = {
            "active_snapshot": {},
            "target_today_minute_run_row_counts_by_asset": {
                asset: {"minute_row_count": 0, "minute_object_count": 0}
                for asset in ("stock", "index", "board")
            },
            "duplicate_minute_key_count_by_asset": {asset: 0 for asset in ("stock", "index", "board")},
            "physical_isolation_violation_count_by_asset": {asset: 0 for asset in ("stock", "index", "board")},
            "outbox_rows_for_run": 0,
            "inbox_rows_for_run": 0,
        }

        with self.assertRaisesRegex(RuntimeError, "finalizer failed"):
            commit_today_minute_attempt_transaction(
                dsn="unused",
                plan=sample_c0_plan(),
                source_run_row={},
                started_at="2026-05-25T01:00:00+00:00",
                c0_plan_path="plan.json",
                prepared=[],
                failed_results=[],
                outcome=outcome,
                pre_backup={"active_snapshot": {}, "outbox_rows_for_run": 0, "inbox_rows_for_run": 0},
                connection_factory=lambda dsn: conn,
                data_snapshot_builder=lambda cur: snapshot,
                finalizer=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("finalizer failed")),
            )

        self.assertEqual(conn.transaction_commits, 0)
        self.assertEqual(conn.transaction_rollbacks, 1)

    def test_today_minute_execute_uses_c1_physical_normalizer_not_legacy_bridge(self) -> None:
        source = inspect.getsource(today_minute_execute)

        self.assertIn("normalize_c1_physical_intraday_1m_labels", source)
        self.assertNotIn("normalize_mootdx_intraday_1m_labels", source)
        self.assertNotIn("mootdx_intraday_1300_to_1130", source)

    def test_execute_requires_double_confirmation(self) -> None:
        with self.assertRaises(TodayMinuteExecuteError):
            ensure_executable_plan(
                sample_c0_plan(),
                execute=True,
                user_confirmed=False,
                for_trade_date="20260525",
                today_minute_run_id="today_minute_bar_1m_20260525_until_1411__source",
            )

    def test_execute_rejects_run_id_mismatch(self) -> None:
        with self.assertRaises(TodayMinuteExecuteError):
            ensure_executable_plan(
                sample_c0_plan(),
                execute=True,
                user_confirmed=True,
                for_trade_date="20260525",
                today_minute_run_id="today_minute_bar_1m_20260525_until_1410__source",
            )

    def test_execute_rejects_invalid_expected_bar_count_before_writing(self) -> None:
        cases = ["missing", None, 0]
        for value in cases:
            with self.subTest(value=value):
                plan = sample_c0_plan()
                if value == "missing":
                    plan.pop("expected_bar_count_per_object")
                else:
                    plan["expected_bar_count_per_object"] = value

                with self.assertRaisesRegex(TodayMinuteExecuteError, "expected_bar_count_per_object"):
                    ensure_executable_plan(
                        plan,
                        execute=True,
                        user_confirmed=True,
                        for_trade_date="20260525",
                        today_minute_run_id="today_minute_bar_1m_20260525_until_1411__source",
                    )

    def test_filter_closed_today_minute_rows_keeps_trade_date_and_closed_session_minutes(self) -> None:
        latest = datetime(2026, 5, 25, 14, 11, tzinfo=ASIA_SHANGHAI)
        rows = [
            minute_row("2026-05-25 09:31"),
            minute_row("2026-05-25 11:31"),
            minute_row("2026-05-25 14:11"),
            minute_row("2026-05-25 14:12"),
            minute_row("2026-05-22 14:11"),
        ]

        filtered = filter_closed_today_minute_rows(rows, trade_date="20260525", latest_closed_minute=latest)

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in filtered], ["09:31", "14:11"])

    def test_mootdx_current_day_raw_1300_is_morning_close_and_1301_is_afternoon_open(self) -> None:
        client = FakeMootdxClient(
            rows=[
                raw_minute_row("2026-06-22 11:29"),
                raw_minute_row("2026-06-22 13:00"),
                raw_minute_row("2026-06-22 13:01"),
            ]
        )
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        rows = adapter.fetch_minute_bars(subscription("stock", "600036"), "20260622")

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in rows], ["11:28", "11:29", "13:00"])
        self.assertEqual(rows[1]["raw_source_label"], "13:00")
        self.assertEqual(rows[1]["physical_c1_label"], "11:29")
        self.assertEqual(rows[2]["raw_source_label"], "13:01")
        self.assertEqual(rows[2]["physical_c1_label"], "13:00")

    def test_mootdx_current_day_raw_1130_maps_to_physical_1129_for_c1(self) -> None:
        client = FakeMootdxClient(rows=[raw_minute_row("2026-06-22 11:30")])
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        rows = adapter.fetch_minute_bars(subscription("stock", "600036"), "20260622")

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in rows], ["11:29"])
        self.assertEqual(rows[0]["raw_source_label"], "11:30")
        self.assertEqual(rows[0]["physical_c1_label"], "11:29")
        self.assertEqual(rows[0]["raw_payload"]["time_label_normalization"], "mootdx_intraday_1130_to_physical_1129")

    def test_mootdx_current_day_raw_1300_supplies_physical_1129_during_trading(self) -> None:
        raw_1129 = raw_minute_row("2026-06-22 11:29")
        raw_1129["amount"] = 111
        raw_1300 = raw_minute_row("2026-06-22 13:00")
        raw_1300["amount"] = 333
        client = FakeMootdxClient(rows=[raw_1129, raw_1300])
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        rows = adapter.fetch_minute_bars(subscription("stock", "600036"), "20260622")

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in rows], ["11:28", "11:29"])
        self.assertEqual(rows[1]["raw_source_label"], "13:00")
        self.assertEqual(rows[1]["physical_c1_label"], "11:29")
        self.assertEqual(rows[1]["amount"], 333)

    def test_mootdx_historical_1130_is_not_rewritten_or_required_to_have_1300(self) -> None:
        client = FakeMootdxClient(
            rows=[
                raw_minute_row("2026-06-18 11:29"),
                raw_minute_row("2026-06-18 11:30"),
                raw_minute_row("2026-06-18 13:01"),
            ]
        )
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        rows = adapter.fetch_minute_bars(subscription("stock", "600036"), "20260618")

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in rows], ["11:29", "11:30", "13:01"])
        self.assertNotIn("time_label_normalization", rows[1]["raw_payload"])

    def test_mootdx_current_day_raw_1130_and_1300_dedupe_as_same_physical_1129(self) -> None:
        client = FakeMootdxClient(
            rows=[
                raw_minute_row("2026-06-22 11:30"),
                raw_minute_row("2026-06-22 13:00"),
            ]
        )
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        rows = adapter.fetch_minute_bars(subscription("stock", "600036"), "20260622")

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in rows], ["11:29"])
        self.assertEqual(rows[0]["raw_source_label"], "11:30")
        self.assertEqual(rows[0]["physical_c1_label"], "11:29")

    def test_mootdx_current_day_without_1130_or_1300_remains_missing(self) -> None:
        client = FakeMootdxClient(
            rows=[
                raw_minute_row("2026-06-22 11:29"),
                raw_minute_row("2026-06-22 13:01"),
            ]
        )
        adapter = MootdxTodayMinuteAdapter(client=client, intraday_trade_date="20260622")

        rows = adapter.fetch_minute_bars(subscription("stock", "600036"), "20260622")

        self.assertEqual([row["bar_time"].strftime("%H:%M") for row in rows], ["11:28", "13:00"])
        status, _ = classify_today_minute_object_status(
            actual_count=len(rows),
            expected_count=3,
            error_message=None,
            quality_visible_no_trade_proof=None,
        )
        self.assertEqual(status, "partial")

    def test_default_no_trade_proof_supports_20260622_002217(self) -> None:
        adapter = MootdxTodayMinuteAdapter(client=FakeMootdxClient(), intraday_trade_date="20260622")

        proof = adapter.quality_visible_no_trade_proof(
            subscription={**sample_subscription(), "identity_key": "stock:SZ:002217", "code": "002217"},
            trade_date="20260622",
            actual_rows=[minute_row("2026-06-22 13:01")],
            expected_bar_count=190,
            latest_closed_minute=datetime(2026, 6, 22, 14, 10, tzinfo=ASIA_SHANGHAI),
        )

        self.assertIsNotNone(proof)
        self.assertEqual(proof["reason"], "source_suspended")
        self.assertEqual(proof["identity_key"], "stock:SZ:002217")

    def test_adapter_routes_stock_to_bars_and_index_board_to_index_bars(self) -> None:
        client = FakeMootdxClient()
        adapter = MootdxTodayMinuteAdapter(client=client)

        adapter.fetch_minute_bars(subscription("stock", "600000"), "20260525")
        adapter.fetch_minute_bars(subscription("index", "000905"), "20260525")
        adapter.fetch_minute_bars(subscription("board", "881001"), "20260525")

        self.assertEqual(client.calls, [("bars", "600000", 8), ("index_bars", "000905", 8), ("index_bars", "881001", 8)])

    def test_build_today_minute_fact_records_marks_rows_as_today_and_no_outbox_trace(self) -> None:
        records = build_today_minute_fact_records(
            plan=sample_c0_plan(),
            subscription=sample_subscription(),
            normalized_rows=[minute_row("2026-05-25 14:11")],
            adapter_name="StockMarketDataAdapter",
            adapter=FakeAdapter(),
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["run_id"], "today_minute_bar_1m_20260525_until_1411__source")
        self.assertEqual(record["trade_date"], "20260525")
        self.assertFalse(record["is_previous_day_preload"])
        self.assertEqual(record["raw_json"]["required_data_kind"], "minute_bar_1m")
        self.assertEqual(record["raw_json"]["writes_outbox"], False)
        self.assertNotIn("event_id", record["raw_json"])

    def test_source_no_trade_proof_marks_partial_object_quality_visible(self) -> None:
        status, quality_status = classify_today_minute_object_status(
            actual_count=120,
            expected_count=190,
            error_message=None,
            quality_visible_no_trade_proof={"reason": "source_suspended", "identity_key": "stock:SZ:002217"},
        )

        self.assertEqual(status, "source_no_trade_quality_visible")
        self.assertEqual(quality_status, "source_no_trade_quality_visible")

    def test_non_suspended_missing_minutes_remain_partial(self) -> None:
        status, quality_status = classify_today_minute_object_status(
            actual_count=120,
            expected_count=190,
            error_message=None,
            quality_visible_no_trade_proof=None,
        )

        self.assertEqual(status, "partial")
        self.assertEqual(quality_status, "partial")

    def test_quality_visible_no_trade_is_reported_without_ordinary_partial_blocker(self) -> None:
        object_results = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SZ:002217",
                "status": "source_no_trade_quality_visible",
                "quality_status": "source_no_trade_quality_visible",
                "expected_bar_count": 190,
                "actual_bar_count": 120,
                "missing_bar_count": 70,
                "minute_rows_written": 120,
                "error_message": None,
                "quality_visible": {
                    "status": "source_no_trade",
                    "reason": "source_suspended",
                    "identity_key": "stock:SZ:002217",
                },
            }
        ]
        checks = build_post_execute_checks(
            plan=sample_c0_plan(),
            pre_backup={"outbox_rows_for_run": 0, "inbox_rows_for_run": 0, "active_snapshot": {"run": "before"}},
            data_snapshot={
                "target_today_minute_run_row_counts_by_asset": {
                    "stock": {"minute_row_count": 120, "minute_object_count": 1},
                    "index": {"minute_row_count": 0, "minute_object_count": 0},
                    "board": {"minute_row_count": 0, "minute_object_count": 0},
                },
                "duplicate_minute_key_count_by_asset": {"stock": 0, "index": 0, "board": 0},
                "physical_isolation_violation_count_by_asset": {"stock": 0, "index": 0, "board": 0},
                "outbox_rows_for_run": 0,
                "inbox_rows_for_run": 0,
                "active_snapshot": {"run": "before"},
            },
            object_results=object_results,
        )

        items = build_post_execute_quality_items(
            plan=sample_c0_plan(),
            post_checks=checks,
            object_results=object_results,
        )

        self.assertEqual(checks["n3_c1_partial_or_missing_objects"], 0)
        self.assertEqual(checks["n3_c1_quality_visible_no_trade_objects"], 1)
        self.assertIn("n3_c1_quality_visible_no_trade_objects", {item["gate_code"] for item in items})
        self.assertNotIn("n3_c1_partial_or_missing_objects", {item["gate_code"] for item in items})

    def test_ordinary_partial_object_is_p0_failed_quality_gate(self) -> None:
        object_results = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600036",
                "status": "partial",
                "quality_status": "partial",
                "expected_bar_count": 190,
                "actual_bar_count": 120,
                "missing_bar_count": 70,
                "minute_rows_written": 120,
                "error_message": None,
            }
        ]
        checks = build_post_execute_checks(
            plan=sample_c0_plan(),
            pre_backup={"outbox_rows_for_run": 0, "inbox_rows_for_run": 0, "active_snapshot": {"run": "before"}},
            data_snapshot={
                "target_today_minute_run_row_counts_by_asset": {
                    "stock": {"minute_row_count": 120, "minute_object_count": 1},
                    "index": {"minute_row_count": 0, "minute_object_count": 0},
                    "board": {"minute_row_count": 0, "minute_object_count": 0},
                },
                "duplicate_minute_key_count_by_asset": {"stock": 0, "index": 0, "board": 0},
                "physical_isolation_violation_count_by_asset": {"stock": 0, "index": 0, "board": 0},
                "outbox_rows_for_run": 0,
                "inbox_rows_for_run": 0,
                "active_snapshot": {"run": "before"},
            },
            object_results=object_results,
        )

        items = build_post_execute_quality_items(
            plan=sample_c0_plan(),
            post_checks=checks,
            object_results=object_results,
        )
        partial_item = next(item for item in items if item["gate_code"] == "n3_c1_partial_or_missing_objects")

        self.assertEqual(checks["n3_c1_partial_or_missing_objects"], 1)
        self.assertEqual(partial_item["severity"], "P0")
        self.assertEqual(partial_item["status"], "failed")


class FakeMootdxClient:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or [raw_minute_row()]
        self.calls: list[tuple[str, str, int]] = []

    def bars(self, *, symbol: str, frequency: int, start: int, offset: int) -> list[dict[str, object]]:
        self.calls.append(("bars", symbol, frequency))
        return list(self.rows)

    def index_bars(self, *, symbol: str, frequency: int, start: int, offset: int) -> list[dict[str, object]]:
        self.calls.append(("index_bars", symbol, frequency))
        return list(self.rows)


class FailingMinuteClient:
    def bars(self, **kwargs):  # noqa: ANN003, ANN201
        raise TdxConnectionError("discard partial minute batch")

    def index_bars(self, **kwargs):  # noqa: ANN003, ANN201
        raise TdxConnectionError("discard partial minute batch")


class PartialMinuteClient:
    def __init__(self, endpoint_id: str, calls: list[tuple[str, str]]) -> None:
        self.endpoint_id = endpoint_id
        self.calls = calls

    def bars(self, *, symbol: str, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append((self.endpoint_id, symbol))
        if self.endpoint_id == "primary" and symbol == "600001":
            raise TimeoutError("second object failed after first succeeded")
        return [raw_minute_row()]

    def index_bars(self, *, symbol: str, **kwargs):  # noqa: ANN003, ANN201
        return self.bars(symbol=symbol, **kwargs)


class EmptyThenNonemptyMinuteClient:
    def __init__(self, endpoint_id: str, calls: list[tuple[str, str]]) -> None:
        self.endpoint_id = endpoint_id
        self.calls = calls

    def bars(self, *, symbol: str, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append((self.endpoint_id, symbol))
        return [] if symbol == "600000" else [raw_minute_row()]

    def index_bars(self, *, symbol: str, **kwargs):  # noqa: ANN003, ANN201
        return self.bars(symbol=symbol, **kwargs)


class EmptyPrimaryMinuteClient(EmptyThenNonemptyMinuteClient):
    def bars(self, *, symbol: str, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append((self.endpoint_id, symbol))
        return [] if self.endpoint_id == "primary" else [raw_minute_row()]


class AtomicBatchConnection:
    def __init__(self, *, fail_on_call: int) -> None:
        self.fail_on_call = fail_on_call
        self.executemany_calls = 0
        self.execute_calls = 0
        self.execute_values = []
        self.transaction_commits = 0
        self.transaction_rollbacks = 0

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN204
        return None

    def transaction(self):  # noqa: ANN201
        return AtomicBatchTransaction(self)

    def cursor(self):  # noqa: ANN201
        return AtomicBatchCursor(self)


class AtomicBatchTransaction:
    def __init__(self, conn: AtomicBatchConnection) -> None:
        self.conn = conn

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN204
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1
        return False


class AtomicBatchCursor:
    def __init__(self, conn: AtomicBatchConnection) -> None:
        self.conn = conn

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN204
        return None

    def executemany(self, sql, values):  # noqa: ANN001, ANN201
        self.conn.executemany_calls += 1
        if self.conn.executemany_calls == self.conn.fail_on_call:
            raise RuntimeError("simulated second object write failure")

    def execute(self, sql, values):  # noqa: ANN001, ANN201
        self.conn.execute_calls += 1
        self.conn.execute_values.append(values)


def fake_endpoint_manager(cache_path: Path, *, mode: str) -> MootdxEndpointManager:
    def endpoint(endpoint_id: str, host: str, priority: int) -> EndpointConfig:
        return EndpointConfig(
            endpoint_id=endpoint_id,
            host=host,
            port=7709,
            priority=priority,
            enabled=True,
            quarantined=False,
            provenance_url="https://example.invalid/frozen",
            provenance_commit="frozen",
            local_validation_status="protocol_passed",
        )

    return MootdxEndpointManager(
        endpoint_pool_version="test-pool-v1",
        transport="mootdx",
        endpoints=(
            endpoint("primary", "115.238.56.198", 10),
            endpoint("secondary", "180.153.18.170", 20),
        ),
        n1_failover_mode="observe",
        n3_failover_mode=mode,
        circuit_open_seconds=300,
        required_empty_object_threshold=3,
        health_cache_path=cache_path,
    )


def passing_probe(row, make_client):  # noqa: ANN001, ANN201
    del row, make_client
    return {
        "checks": {
            "stock_quote": True,
            "stock_daily_bars": True,
            "index_daily_bars": True,
            "scope_sentinels": True,
            "minute_scope_sentinels": True,
        }
    }


class FakeAdapter:
    source_version = "fake.today.minute.v1"
    external_source = "fake"


def sample_c0_plan() -> dict[str, object]:
    return {
        "stage": "N3-C0",
        "layer_role": "N3_market_data",
        "blocked": False,
        "source_market_data_run_id": "source",
        "today_minute_run_id": "today_minute_bar_1m_20260525_until_1411__source",
        "source_condition_run_id": "condition_layer",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "latest_closed_minute": "2026-05-25T14:11:00+08:00",
        "expected_bar_count_per_object": 191,
        "expected_minute_rows": 191,
        "expected_minute_rows_by_asset_kind": {"stock": 191, "index": 0, "board": 0},
        "today_minute_object_count_by_asset_kind": {"stock": 1, "index": 0, "board": 0},
        "event_outbox_write_required_in_execute": False,
        "generated_event_types_for_execute": [],
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
        "execute_contract": {"writes_outbox": False},
    }


def sample_subscription() -> dict[str, object]:
    return {
        "subscription_id": 11,
        "pull_plan_id": 22,
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "exchange": "SH",
        "code": "600000",
        "display_code": "600000.SH",
        "name": "浦发银行",
        "source_scope_ids": [1],
        "source_condition_pool_ids": [101],
    }


def subscription(asset_kind: str, code: str) -> dict[str, object]:
    return {"asset_kind": asset_kind, "code": code}


def minute_row(value: str) -> dict[str, object]:
    return {
        "bar_time": datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=ASIA_SHANGHAI),
        "open": 10,
        "high": 10.1,
        "low": 9.9,
        "close": 10.05,
        "volume": 100,
        "amount": 1000,
        "raw_payload": {"datetime": value},
    }


def raw_minute_row(value: str = "2026-05-25 14:11") -> dict[str, object]:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
    return {
        "datetime": value,
        "open": 10,
        "high": 10.1,
        "low": 9.9,
        "close": 10.05,
        "vol": 100,
        "amount": 1000,
        "year": parsed.year,
        "month": parsed.month,
        "day": parsed.day,
        "hour": parsed.hour,
        "minute": parsed.minute,
    }


if __name__ == "__main__":
    unittest.main()
