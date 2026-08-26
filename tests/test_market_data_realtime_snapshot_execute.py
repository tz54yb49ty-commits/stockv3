import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

from ashare_v3.market.event_factory import build_n3_market_event
from ashare_v3.market.realtime_snapshot_execute import (
    ALLOWED_B1_FACT_ONLY_WRITE_TABLES,
    ALLOWED_B1_WRITE_TABLES,
    AssetRoutingRealtimeSnapshotAdapter,
    BoardMarketDataAdapter,
    FORBIDDEN_B1_WRITE_TABLE_MARKERS,
    IndexMarketDataAdapter,
    MootdxRealtimeSnapshotAdapter,
    RealtimeSnapshotExecuteError,
    TushareBjIndexSnapshotAdapter,
    build_snapshot_record,
    build_default_mootdx_endpoint_probe,
    build_snapshot_source_time_evidence,
    commit_snapshot_attempt_transaction,
    build_post_execute_checks,
    build_post_execute_quality_items,
    ensure_clean_snapshot_target,
    ensure_executable_contract,
    ensure_execute_authorized,
    execute_one_subscription_snapshot,
    prepare_one_subscription_snapshot,
    prepare_mootdx_snapshot_batch,
    run_realtime_daily_snapshot_execute,
    write_failed_snapshot_attempt_transaction,
    write_prepared_subscription_snapshots,
)
from ashare_v3.market.realtime_snapshot_execute_contract import build_source_time_policy
from ashare_v3.mootdx_client import EndpointConfig, MootdxEndpointManager


class RealtimeSnapshotExecuteTest(unittest.TestCase):
    def test_tdxpy_bj_stock_scope_blocks_before_probe_business_fact_or_event(self) -> None:
        bj_subscription = {
            **sample_subscription(),
            "identity_key": "stock:BJ:830001",
            "exchange": "BJ",
            "code": "830001",
        }
        with tempfile.TemporaryDirectory() as tmp:
            health_path = Path(tmp) / "health.json"
            manager = fake_endpoint_manager(health_path, mode="active")
            probe_calls: list[str] = []
            business_calls: list[str] = []

            with self.assertRaisesRegex(
                RealtimeSnapshotExecuteError,
                "BLOCKED_N3_TDXPY_BJ_STOCK_QUOTE_UNSUPPORTED:stock:BJ:830001",
            ):
                prepare_mootdx_snapshot_batch(
                    contract=sample_contract(),
                    subscriptions=[bj_subscription],
                    manager=manager,
                    probe=lambda endpoint, make_client: probe_calls.append(endpoint.endpoint_id)
                    or passing_endpoint_probe(endpoint, make_client),
                    client_factory=lambda selection: business_calls.append(selection.endpoint_id),
                    transport="tdxpy",
                    snapshot_time=sample_snapshot_time(),
                )

            self.assertEqual(probe_calls, [])
            self.assertEqual(business_calls, [])
            self.assertFalse(health_path.exists())

    def test_snapshot_program_error_does_not_failover_or_open_endpoint_circuit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = fake_endpoint_manager(Path(tmp) / "health.json", mode="active")
            calls: list[str] = []

            class ProgramBugClient:
                def quotes(self, **kwargs):  # noqa: ANN003, ANN201
                    raise KeyError("local snapshot contract bug")

            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=[sample_subscription()],
                manager=manager,
                probe=passing_endpoint_probe,
                client_factory=lambda selection: calls.append(selection.endpoint_id) or ProgramBugClient(),
                snapshot_time=sample_snapshot_time(),
            )

            self.assertEqual(
                manager._health_for("primary", transport="mootdx").state,
                "healthy",
            )

        self.assertEqual(calls, ["primary"])
        self.assertEqual(outcome.attempts[0]["failure_kind"], "unclassified_program_failure")
        self.assertFalse(outcome.attempts[0]["retry_allowed"])
        self.assertTrue(all(item["snapshot_record"] is None for item in prepared))

    def test_active_both_endpoints_fail_writes_no_success_fact_or_event_and_closes_all_attempts(self) -> None:
        class ClosableFailingClient(FailingSnapshotClient):
            def __init__(self, endpoint_id: str) -> None:
                self.endpoint_id = endpoint_id
                self.close_calls = 0

            def close(self) -> None:
                self.close_calls += 1

        with tempfile.TemporaryDirectory() as tmp:
            clients: list[ClosableFailingClient] = []

            def client_factory(selection):  # noqa: ANN001, ANN202
                client = ClosableFailingClient(selection.endpoint_id)
                clients.append(client)
                return client

            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=[sample_subscription()],
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_endpoint_probe,
                client_factory=client_factory,
                snapshot_time=sample_snapshot_time(),
            )

        conn = FakeConnection()
        results = write_failed_snapshot_attempt_transaction(
            dsn="unused",
            contract=sample_contract(),
            source_run_row={},
            started_at="2026-05-25T01:00:00+00:00",
            prepared_snapshots=prepared,
            outcome=outcome,
            connection_factory=lambda dsn: conn,
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual([client.endpoint_id for client in clients], ["primary", "secondary"])
        self.assertEqual([client.close_calls for client in clients], [1, 1])
        self.assertNotIn("snapshot_fact", conn.sql_kinds())
        self.assertNotIn("MarketSnapshotUpdated", "\n".join(conn.executed_sql))
        self.assertTrue(all(result["snapshot_rows_written"] == 0 for result in results))
        self.assertTrue(all(result["event_type"] == "MarketDataDelayed" for result in results))

    def test_secondary_replay_writes_one_fact_event_and_keeps_source_run_and_dedup_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=[sample_subscription()],
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_endpoint_probe,
                client_factory=lambda selection: (
                    FailingSnapshotClient()
                    if selection.endpoint_id == "primary"
                    else PassingSnapshotClient(sample_raw_snapshot())
                ),
                snapshot_time=sample_snapshot_time(),
            )

        self.assertEqual(outcome.status, "passed")
        self.assertEqual(len(prepared), 1)
        record = prepared[0]["snapshot_record"]
        baseline_record = dict(record)
        baseline_record["raw_json"] = {}

        def event_for(value):  # noqa: ANN001, ANN202
            return build_n3_market_event(
                event_type="MarketSnapshotUpdated",
                asset_kind=str(value["asset_kind"]),
                identity_key=str(value["identity_key"]),
                trade_date=str(value["trade_date"]),
                snapshot_time=value["snapshot_time"].isoformat(),
                event_time=value["snapshot_time"],
                source_run_id=str(value["run_id"]),
                source_adapter=str(value["source_adapter"]),
                payload={
                    "subscription_id": value["subscription_id"],
                    "pull_plan_id": value["pull_plan_id"],
                    "run_id": value["run_id"],
                    "source_adapter": value["source_adapter"],
                    "data_quality_status": value["data_quality_status"],
                    "snapshot_id": 101,
                },
            )

        baseline_event = event_for(baseline_record)
        failover_event = event_for(record)
        self.assertEqual(failover_event.source_run_id, baseline_event.source_run_id)
        self.assertEqual(failover_event.dedup_key, baseline_event.dedup_key)
        self.assertEqual(failover_event.event_id, baseline_event.event_id)

        conn = FakeConnection()
        results = write_prepared_subscription_snapshots(
            dsn="unused",
            contract=sample_contract(),
            prepared_snapshots=prepared,
            connection_factory=lambda dsn: conn,
        )
        self.assertEqual(conn.sql_kinds(), ["snapshot_fact", "outbox"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["snapshot_rows_written"], 1)
        self.assertEqual(results[0]["outbox_rows_written"], 1)

    def test_realtime_mootdx_adapters_require_manager_pinned_clients(self) -> None:
        for adapter_type in (MootdxRealtimeSnapshotAdapter, IndexMarketDataAdapter, BoardMarketDataAdapter):
            with self.subTest(adapter=adapter_type.__name__):
                with self.assertRaisesRegex(RealtimeSnapshotExecuteError, "manager-selected pinned client"):
                    adapter_type()
        with self.assertRaisesRegex(RealtimeSnapshotExecuteError, "requires pinned stock/index/board adapters"):
            AssetRoutingRealtimeSnapshotAdapter()

    def test_default_endpoint_probe_requires_protocol_data_semantics_and_batch_sentinel(self) -> None:
        client = ProtocolProbeClient()
        probe = build_default_mootdx_endpoint_probe([sample_subscription()])

        result = probe(object(), lambda profile: client)

        self.assertEqual(result["checks"], {
            "stock_quote": True,
            "stock_daily_bars": True,
            "index_daily_bars": True,
            "scope_sentinels": True,
        })
        self.assertEqual(
            [call["kind"] for call in client.calls],
            ["quotes", "bars", "index_bars", "quotes"],
        )

    def test_default_endpoint_probe_rejects_constructed_client_with_invalid_market_data(self) -> None:
        probe = build_default_mootdx_endpoint_probe([sample_subscription()])

        result = probe(object(), lambda profile: InvalidProtocolProbeClient())

        self.assertEqual(result["checks"], {
            "stock_quote": False,
            "stock_daily_bars": False,
            "index_daily_bars": False,
            "scope_sentinels": False,
        })

    def test_default_endpoint_probe_rejects_missing_or_wrong_response_identity(self) -> None:
        subscriptions = [sample_subscription(), sample_index_subscription(), sample_board_subscription()]
        for client in (MissingIdentityProtocolProbeClient(), WrongIdentityProtocolProbeClient()):
            with self.subTest(client=type(client).__name__):
                result = build_default_mootdx_endpoint_probe(subscriptions)(
                    object(),
                    lambda profile, value=client: value,
                )
                self.assertFalse(all(result["checks"].values()))

    def test_default_endpoint_probe_excludes_bj_route_but_checks_sh_index_sentinel(self) -> None:
        client = ProtocolProbeClient()
        probe = build_default_mootdx_endpoint_probe(
            [sample_bj_index_subscription(), sample_index_subscription()]
        )

        result = probe(object(), lambda profile: client)

        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(
            [call for call in client.calls if call["kind"] == "index"],
            [{"kind": "index", "symbol": "000001"}],
        )

    def test_default_endpoint_probe_matches_router_for_bj_and_missing_exchange_stock(self) -> None:
        client = ProtocolProbeClient()
        bj_stock = {**sample_subscription(), "identity_key": "stock:BJ:830001", "exchange": "BJ", "code": "830001"}
        missing_exchange_stock = {
            **sample_subscription(),
            "identity_key": "stock:UNKNOWN:600002",
            "exchange": "",
            "code": "600002",
        }

        result = build_default_mootdx_endpoint_probe(
            [bj_stock, missing_exchange_stock, sample_bj_index_subscription()]
        )(object(), lambda profile: client)

        self.assertTrue(all(result["checks"].values()))
        sentinel_quote_calls = [
            call for call in client.calls
            if call["kind"] == "quotes" and call["symbol"] != "600000"
        ]
        self.assertEqual(sentinel_quote_calls, [{"kind": "quotes", "symbol": "830001"}])

    def test_mootdx_snapshot_batch_active_discards_primary_and_traces_secondary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_manager = fake_endpoint_manager(Path(tmp) / "health.json", mode="active")
            clients: list[str] = []

            def client_factory(selection):  # noqa: ANN001, ANN202
                clients.append(selection.endpoint_id)
                if selection.endpoint_id == "primary":
                    return FailingSnapshotClient()
                return PassingSnapshotClient(sample_raw_snapshot())

            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=[sample_subscription()],
                manager=batch_manager,
                probe=passing_endpoint_probe,
                client_factory=client_factory,
                snapshot_time=sample_snapshot_time(),
            )

        self.assertEqual(clients, ["primary", "secondary"])
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(prepared[0]["write_kind"], "snapshot")
        raw_json_value = prepared[0]["snapshot_record"]["raw_json"]
        raw_json = getattr(raw_json_value, "obj", raw_json_value)
        self.assertEqual(raw_json["attempt_id"], f"{sample_contract()['snapshot_run_id']}__attempt_2")
        self.assertEqual(raw_json["endpoint_id"], "secondary")

    def test_mootdx_snapshot_batch_observe_failure_has_no_secondary_success_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_manager = fake_endpoint_manager(Path(tmp) / "health.json", mode="observe")
            clients: list[str] = []
            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=[sample_subscription()],
                manager=batch_manager,
                probe=passing_endpoint_probe,
                client_factory=lambda selection: clients.append(selection.endpoint_id) or FailingSnapshotClient(),
                snapshot_time=sample_snapshot_time(),
            )

        self.assertEqual(clients, ["primary"])
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(prepared[0]["write_kind"], "quality")
        self.assertIsNone(prepared[0]["snapshot_record"])
        self.assertIsNone(prepared[0]["object_result"]["event_type"])
        self.assertEqual(prepared[0]["object_result"]["outbox_rows_written"], 0)

    def test_endpoint_failure_transaction_writes_only_failed_run_quality_and_delayed_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=[sample_subscription()],
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="observe"),
                probe=passing_endpoint_probe,
                client_factory=lambda selection: FailingSnapshotClient(),
                snapshot_time=sample_snapshot_time(),
            )
        conn = FakeConnection()

        results = write_failed_snapshot_attempt_transaction(
            dsn="unused",
            contract=sample_contract(),
            source_run_row={},
            started_at="2026-05-25T01:00:00+00:00",
            prepared_snapshots=prepared,
            outcome=outcome,
            connection_factory=lambda dsn: conn,
        )

        sql = "\n".join(conn.executed_sql).lower()
        self.assertEqual(conn.transaction_commits, 1)
        self.assertEqual(conn.transaction_rollbacks, 0)
        self.assertIn("common_market_data_quality_item", sql)
        self.assertIn("common_event_outbox", sql)
        self.assertNotIn("insert into stock_realtime_daily_snapshot", sql)
        self.assertEqual(results[0]["event_type"], "MarketDataDelayed")
        self.assertEqual(results[0]["snapshot_rows_written"], 0)
        self.assertEqual(results[0]["outbox_rows_written"], 1)

        rollback_conn = FakeConnection(fail_on="UPDATE common_market_data_run")
        with self.assertRaises(RuntimeError):
            write_failed_snapshot_attempt_transaction(
                dsn="unused",
                contract=sample_contract(),
                source_run_row={},
                started_at="2026-05-25T01:00:00+00:00",
                prepared_snapshots=prepared,
                outcome=outcome,
                connection_factory=lambda dsn: rollback_conn,
            )
        self.assertEqual(rollback_conn.transaction_commits, 0)
        self.assertEqual(rollback_conn.transaction_rollbacks, 1)

    def test_multi_object_partial_snapshot_attempt_replays_secondary_from_first(self) -> None:
        subscriptions = [
            sample_subscription(),
            {**sample_subscription(), "subscription_id": 12, "identity_key": "stock:SH:600001", "code": "600001"},
        ]
        calls: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=subscriptions,
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_endpoint_probe,
                client_factory=lambda selection: PartialSnapshotClient(selection.endpoint_id, calls),
                snapshot_time=sample_snapshot_time(),
            )

        self.assertEqual(
            calls,
            [
                ("primary", "600000"),
                ("primary", "600001"),
                ("secondary", "600000"),
                ("secondary", "600001"),
            ],
        )
        self.assertEqual(outcome.status, "passed")
        self.assertEqual([row["write_kind"] for row in prepared], ["snapshot", "snapshot"])

    def test_observe_multi_object_snapshot_failure_has_no_secondary_business_fetch(self) -> None:
        subscriptions = [
            sample_subscription(),
            {**sample_subscription(), "subscription_id": 12, "identity_key": "stock:SH:600001", "code": "600001"},
        ]
        calls: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=subscriptions,
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="observe"),
                probe=passing_endpoint_probe,
                client_factory=lambda selection: PartialSnapshotClient(selection.endpoint_id, calls),
                snapshot_time=sample_snapshot_time(),
            )

        self.assertEqual(calls, [("primary", "600000"), ("primary", "600001")])
        self.assertEqual(outcome.status, "failed")
        self.assertTrue(all(row["write_kind"] == "quality" for row in prepared))
        self.assertTrue(all(row["object_result"]["outbox_rows_written"] == 0 for row in prepared))

    def test_one_empty_snapshot_then_nonempty_stays_primary_as_missing_quality(self) -> None:
        subscriptions = [
            sample_subscription(),
            {**sample_subscription(), "subscription_id": 12, "identity_key": "stock:SH:600001", "code": "600001"},
        ]
        calls: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=subscriptions,
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_endpoint_probe,
                client_factory=lambda selection: EmptyThenSnapshotClient(selection.endpoint_id, calls),
                snapshot_time=sample_snapshot_time(),
            )

        self.assertEqual(calls, [("primary", "600000"), ("primary", "600001")])
        self.assertEqual(outcome.status, "passed")
        self.assertEqual([row["write_kind"] for row in prepared], ["quality", "snapshot"])
        self.assertEqual(prepared[0]["object_result"]["quality_status"], "missing")
        self.assertEqual(prepared[0]["object_result"]["outbox_rows_written"], 0)

    def test_three_empty_snapshots_replay_secondary_from_first(self) -> None:
        subscriptions = [
            {**sample_subscription(), "subscription_id": 11 + index, "identity_key": f"stock:SH:60000{index}", "code": f"60000{index}"}
            for index in range(3)
        ]
        calls: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=subscriptions,
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_endpoint_probe,
                client_factory=lambda selection: EmptyPrimarySnapshotClient(selection.endpoint_id, calls),
                snapshot_time=sample_snapshot_time(),
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
        self.assertTrue(all(row["write_kind"] == "snapshot" for row in prepared))

    def test_snapshot_batch_second_write_failure_rolls_back_outer_transaction(self) -> None:
        subscriptions = [
            sample_subscription(),
            {**sample_subscription(), "subscription_id": 12, "identity_key": "stock:SH:600001", "code": "600001"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=subscriptions,
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_endpoint_probe,
                client_factory=lambda selection: PartialSnapshotClient(selection.endpoint_id, []),
                snapshot_time=sample_snapshot_time(),
            )
        self.assertEqual(outcome.status, "passed")
        conn = AtomicSnapshotConnection()

        with self.assertRaisesRegex(RuntimeError, "second snapshot"):
            write_prepared_subscription_snapshots(
                dsn="unused",
                contract={**sample_contract(), "writes_outbox": True},
                prepared_snapshots=prepared,
                connection_factory=lambda dsn: conn,
            )

        self.assertEqual(conn.outer_commits, 0)
        self.assertEqual(conn.outer_rollbacks, 1)

    def test_snapshot_finalizer_failure_rolls_back_run_facts_events_and_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=[sample_subscription()],
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_endpoint_probe,
                client_factory=lambda selection: PassingSnapshotClient(sample_raw_snapshot()),
                snapshot_time=sample_snapshot_time(),
            )
        conn = FakeConnection()
        snapshot = sample_snapshot_backup(
            sample_contract(),
            row_counts={"stock": 1, "index": 0, "board": 0},
            outbox_count=1,
            outbox_counts_by_type={"MarketSnapshotUpdated": 1},
        )

        with self.assertRaisesRegex(RuntimeError, "finalizer failed"):
            commit_snapshot_attempt_transaction(
                dsn="unused",
                contract=sample_contract(),
                source_run_row={},
                started_at="2026-05-25T01:00:00+00:00",
                prepared_snapshots=prepared,
                outcome=outcome,
                connection_factory=lambda dsn: conn,
                data_snapshot_builder=lambda cur: snapshot,
                finalizer=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("finalizer failed")),
            )

        self.assertEqual(conn.transaction_commits, 0)
        self.assertEqual(conn.transaction_rollbacks, 1)

    def test_source_time_failure_is_attempt_failure_and_active_replays_full_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clients: list[str] = []

            def client_factory(selection):  # noqa: ANN001, ANN202
                clients.append(selection.endpoint_id)
                row = sample_raw_snapshot()
                if selection.endpoint_id == "primary":
                    row["snapshot_time"] = "2026-05-26T10:00:00+08:00"
                return PassingSnapshotClient(row)

            prepared, outcome = prepare_mootdx_snapshot_batch(
                contract=sample_contract(),
                subscriptions=[sample_subscription()],
                manager=fake_endpoint_manager(Path(tmp) / "health.json", mode="active"),
                probe=passing_endpoint_probe,
                client_factory=client_factory,
                snapshot_time=sample_snapshot_time(),
            )

        self.assertEqual(clients, ["primary", "secondary"])
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(prepared[0]["write_kind"], "snapshot")

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
            index_adapter=RecordingSnapshotAdapter({}),
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
            index_adapter=RecordingSnapshotAdapter({}),
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


class FailingSnapshotClient:
    def quotes(self, *, symbol: str):  # noqa: ANN201
        del symbol
        raise TimeoutError("primary batch failed after partial transport work")


class PassingSnapshotClient:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    def quotes(self, *, symbol: str):  # noqa: ANN201
        del symbol
        return [dict(self.row)]


class PartialSnapshotClient:
    def __init__(self, endpoint_id: str, calls: list[tuple[str, str]]) -> None:
        self.endpoint_id = endpoint_id
        self.calls = calls

    def quotes(self, *, symbol: str):  # noqa: ANN201
        self.calls.append((self.endpoint_id, symbol))
        if self.endpoint_id == "primary" and symbol == "600001":
            raise TimeoutError("primary failed after one snapshot")
        return [sample_raw_snapshot()]


class EmptyThenSnapshotClient:
    def __init__(self, endpoint_id: str, calls: list[tuple[str, str]]) -> None:
        self.endpoint_id = endpoint_id
        self.calls = calls

    def quotes(self, *, symbol: str):  # noqa: ANN201
        self.calls.append((self.endpoint_id, symbol))
        return [] if symbol == "600000" else [sample_raw_snapshot()]


class EmptyPrimarySnapshotClient(EmptyThenSnapshotClient):
    def quotes(self, *, symbol: str):  # noqa: ANN201
        self.calls.append((self.endpoint_id, symbol))
        return [] if self.endpoint_id == "primary" else [sample_raw_snapshot()]


class ProtocolProbeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def quotes(self, *, symbol: str):  # noqa: ANN201
        self.calls.append({"kind": "quotes", "symbol": symbol})
        return [{"code": symbol, "price": 10.1}]

    def bars(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        self.calls.append({"kind": "bars", "symbol": symbol})
        return [
            {"code": symbol, "datetime": "2026-07-16", "close": 10},
            {"code": symbol, "datetime": "2026-07-17", "close": 10.1},
            {"code": symbol, "datetime": "2026-07-18", "close": 10.2},
        ]

    def index_bars(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        self.calls.append({"kind": "index_bars", "symbol": symbol})
        return [{"code": symbol, "datetime": "2026-07-18", "close": 3500}]

    def index(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        self.calls.append({"kind": "index", "symbol": symbol})
        return [{"code": symbol, "datetime": "2026-07-18", "close": 3500}]


class InvalidProtocolProbeClient:
    def quotes(self, *, symbol: str):  # noqa: ANN201
        return [{"code": symbol, "price": 0}]

    def bars(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        return [{"code": "wrong", "datetime": "2026-07-18", "close": 10}]

    def index_bars(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        return []

    def index(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        return []


class MissingIdentityProtocolProbeClient(ProtocolProbeClient):
    def quotes(self, *, symbol: str):  # noqa: ANN201
        return [{"price": 10.1}]

    def bars(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        return [{"datetime": f"2026-07-{day}", "close": 10} for day in (16, 17, 18)]

    def index_bars(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        return [{"datetime": "2026-07-18", "close": 3500}]

    def index(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        return [{"datetime": "2026-07-18", "close": 3500}]


class WrongIdentityProtocolProbeClient(ProtocolProbeClient):
    def quotes(self, *, symbol: str):  # noqa: ANN201
        return [{"code": "999999", "price": 10.1}]

    def bars(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        return [
            {"code": "999999", "datetime": f"2026-07-{day}", "close": 10}
            for day in (16, 17, 18)
        ]

    def index_bars(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        return [{"code": "999999", "datetime": "2026-07-18", "close": 3500}]

    def index(self, *, symbol: str, frequency: int, start: int, offset: int):  # noqa: ANN201
        return [{"code": "999999", "datetime": "2026-07-18", "close": 3500}]


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


def passing_endpoint_probe(row, make_client):  # noqa: ANN001, ANN201
    del row, make_client
    return {
        "checks": {
            "stock_quote": True,
            "stock_daily_bars": True,
            "index_daily_bars": True,
            "scope_sentinels": True,
        }
    }


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
        self.depth = 0

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


class AtomicSnapshotConnection:
    def __init__(self) -> None:
        self.depth = 0
        self.snapshot_writes = 0
        self.last_sql = ""
        self.outer_commits = 0
        self.outer_rollbacks = 0

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return None
    def transaction(self): return AtomicSnapshotTransaction(self)
    def cursor(self): return AtomicSnapshotCursor(self)


class AtomicSnapshotTransaction:
    def __init__(self, conn: AtomicSnapshotConnection) -> None:
        self.conn = conn
        self.is_outer = False

    def __enter__(self):
        self.is_outer = self.conn.depth == 0
        self.conn.depth += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.depth -= 1
        if self.is_outer:
            if exc_type is None:
                self.conn.outer_commits += 1
            else:
                self.conn.outer_rollbacks += 1
        return False


class AtomicSnapshotCursor:
    def __init__(self, conn: AtomicSnapshotConnection) -> None:
        self.conn = conn

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return None

    def execute(self, sql: str, params=None) -> None:  # noqa: ANN001
        self.conn.last_sql = sql
        if "realtime_daily_snapshot" in sql:
            self.conn.snapshot_writes += 1
            if self.conn.snapshot_writes == 2:
                raise RuntimeError("second snapshot write failed")

    def fetchone(self):  # noqa: ANN201
        if "realtime_daily_snapshot" in self.conn.last_sql:
            return {"snapshot_id": 101}
        if "common_event_outbox" in self.conn.last_sql:
            return {"event_id": "event-test"}
        return {"id": 1}


class FakeTransaction:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def __enter__(self) -> "FakeTransaction":
        self.is_outer = self.conn.depth == 0
        self.conn.depth += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.conn.depth -= 1
        if self.is_outer:
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
