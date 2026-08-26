from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ashare_v3.market.mootdx_batch_attempt import (
    MootdxBatchObjectTracker,
    MootdxEndpointWideRequiredObjectsEmpty,
    build_mootdx_minute_semantic_probe,
    _minute_sentinel_valid,
    is_endpoint_transport_exception,
    run_mootdx_batch_attempt,
)
from ashare_v3.mootdx_client import EndpointConfig, MootdxEndpointManager
from ashare_v3.quote_transport import QuoteTransportConnectionError


CHECKS = {
    "stock_quote": True,
    "stock_daily_bars": True,
    "index_daily_bars": True,
    "scope_sentinels": True,
}


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


def manager(cache_path: Path, *, mode: str) -> MootdxEndpointManager:
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
    return {"checks": dict(CHECKS)}


def minute_probe_row(trade_date: str, label: str, *, close: float = 10) -> dict:
    return {
        "bar_time": datetime.strptime(
            f"{trade_date} {label}",
            "%Y%m%d %H:%M",
        ).replace(tzinfo=ZoneInfo("Asia/Shanghai")),
        "close": close,
    }


def full_day_minute_rows(first_label: str) -> list[dict]:
    morning_start = datetime.strptime(
        f"20260717 {first_label}",
        "%Y%m%d %H:%M",
    ).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    afternoon_label = "13:00" if first_label == "09:30" else "13:01"
    afternoon_start = datetime.strptime(
        f"20260717 {afternoon_label}",
        "%Y%m%d %H:%M",
    ).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return [
        {"bar_time": start + timedelta(minutes=index), "close": 10}
        for start in (morning_start, afternoon_start)
        for index in range(120)
    ]


class MootdxBatchAttemptTest(unittest.TestCase):
    def test_minute_sentinel_accepts_consistent_full_day_label_conventions(self) -> None:
        for convention, first_label, last_label in (
            ("canonical_interval_start", "09:30", "14:59"),
            ("provider_close_label", "09:31", "15:00"),
        ):
            with self.subTest(convention=convention):
                rows = full_day_minute_rows(first_label)
                self.assertEqual(len(rows), 240)
                self.assertEqual(rows[0]["bar_time"].strftime("%H:%M"), first_label)
                self.assertEqual(rows[-1]["bar_time"].strftime("%H:%M"), last_label)
                self.assertTrue(
                    _minute_sentinel_valid(rows, trade_date="20260717")
                )

    def test_minute_sentinel_rejects_mixed_or_invalid_labels_and_rows(self) -> None:
        valid = full_day_minute_rows("09:31")
        cases = {
            "mixed_boundary_conventions": [
                minute_probe_row("20260717", "09:30"),
                minute_probe_row("20260717", "15:00"),
            ],
            "lunch_1131": [minute_probe_row("20260717", "11:31")],
            "lunch_1200": [minute_probe_row("20260717", "12:00")],
            "after_close": [minute_probe_row("20260717", "15:01")],
            "wrong_date": [minute_probe_row("20260716", "09:31")],
            "duplicate": [valid[0], dict(valid[0])],
            "nonmonotonic": [valid[1], valid[0]],
            "zero_close": [{**valid[0], "close": 0}],
        }

        for case, rows in cases.items():
            with self.subTest(case=case):
                self.assertFalse(
                    _minute_sentinel_valid(rows, trade_date="20260717")
                )

    def test_endpoint_transport_classifier_is_narrow_and_preserves_program_errors(self) -> None:
        class TdxConnectionError(Exception):
            pass

        for exc in (
            TimeoutError("timeout"),
            ConnectionError("connection"),
            OSError("socket"),
            QuoteTransportConnectionError("typed transport"),
            TdxConnectionError("typed tdx connection"),
        ):
            with self.subTest(error_type=type(exc).__name__):
                self.assertTrue(is_endpoint_transport_exception(exc))

        for exc in (
            KeyError("local contract"),
            AssertionError("local invariant"),
            ValueError("local normalization"),
        ):
            with self.subTest(error_type=type(exc).__name__):
                self.assertFalse(is_endpoint_transport_exception(exc))

    def test_resolved_transport_factory_is_shared_by_probe_and_business_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[tuple[str, str, str]] = []

            def transport_factory(selection, profile, *, transport):  # noqa: ANN001, ANN202
                calls.append((selection.selection_reason, profile, transport))
                return ClosableAttemptClient(selection.endpoint_id)

            outcome = run_mootdx_batch_attempt(
                manager=manager(Path(tmp) / "health.json", mode="active"),
                batch_id="batch-shared-transport",
                probe=lambda row, make_client: (
                    make_client("std").close()
                    or {"checks": dict(CHECKS)}
                ),
                transport="tdxpy",
                transport_factory=transport_factory,
                fetch_batch=lambda client, selection: [selection.transport],
            )

        self.assertEqual(outcome.status, "passed")
        self.assertEqual(outcome.result, ["tdxpy"])
        self.assertEqual([row[2] for row in calls], ["tdxpy", "tdxpy", "tdxpy"])
        self.assertEqual(outcome.attempts[0]["transport"], "tdxpy")
        self.assertEqual(outcome.attempts[0]["source_transport"], "tdxpy")

    def test_tdxpy_business_failure_never_opens_mootdx_circuit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="observe")

            def transport_factory(selection, profile, *, transport):  # noqa: ANN001, ANN202
                del profile, transport
                if selection.selection_reason == "stable_priority_primary_healthy":
                    raise QuoteTransportConnectionError("tdxpy failed")
                return ClosableAttemptClient(selection.endpoint_id)

            outcome = run_mootdx_batch_attempt(
                manager=endpoint_manager,
                batch_id="batch-tdxpy-circuit",
                probe=lambda row, make_client: (
                    make_client("std").close()
                    or {"checks": dict(CHECKS)}
                ),
                transport="tdxpy",
                transport_factory=transport_factory,
                fetch_batch=lambda client, selection: ["forbidden"],
            )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(endpoint_manager._health_for("primary", transport="tdxpy").state, "open")
        self.assertNotEqual(endpoint_manager._health_for("primary", transport="mootdx").state, "open")

    def test_empty_threshold_is_attempt_local_and_repeated_identity_does_not_increment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="active")
            selection = endpoint_manager.select_for_batch(
                batch_id="tracker-selection",
                probe=passing_probe,
            )
            first_attempt = MootdxBatchObjectTracker(endpoint_manager, selection)
            for identity in ("stock:SH:600000", "stock:SH:600000", "stock:SH:600001"):
                result = first_attempt.record(identity_key=identity, value=[], empty=True)
                self.assertEqual(result.status, "empty_required_object")

            second_attempt = MootdxBatchObjectTracker(endpoint_manager, selection)
            result = second_attempt.record(identity_key="stock:SH:600002", value=[], empty=True)

        self.assertEqual(result.status, "empty_required_object")

    def test_only_three_attempt_local_distinct_empties_open_circuit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="active")
            selection = endpoint_manager.select_for_batch(
                batch_id="tracker-three-distinct",
                probe=passing_probe,
            )
            tracker = MootdxBatchObjectTracker(endpoint_manager, selection)
            tracker.record(identity_key="stock:SH:600000", value=[], empty=True)
            tracker.record(identity_key="stock:SH:600001", value=[], empty=True)

            with self.assertRaises(MootdxEndpointWideRequiredObjectsEmpty):
                tracker.record(identity_key="stock:SH:600002", value=[], empty=True)

            self.assertEqual(
                endpoint_manager._health_for(
                    selection.endpoint_id,
                    transport=selection.transport,
                ).state,
                "open",
            )

    def test_one_empty_then_nonempty_stays_on_primary_and_resets_counter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="active")
            calls: list[tuple[str, str]] = []

            def fetch(client, selection):  # noqa: ANN001, ANN202
                tracker = MootdxBatchObjectTracker(endpoint_manager, selection)
                first = tracker.record(identity_key="stock:SH:600000", value=[], empty=True)
                calls.append((client, first.status))
                second = tracker.record(identity_key="stock:SH:600001", value=[1], empty=False)
                calls.append((client, second.status))
                return [first, second]

            outcome = run_mootdx_batch_attempt(
                manager=endpoint_manager,
                batch_id="batch-one-empty",
                probe=passing_probe,
                client_factory=lambda selection: selection.endpoint_id,
                fetch_batch=fetch,
            )

        self.assertEqual(calls, [("primary", "empty_required_object"), ("primary", "passed")])
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(len(outcome.attempts), 1)

    def test_three_distinct_consecutive_empties_active_replays_secondary_from_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="active")
            calls: list[tuple[str, str]] = []

            def fetch(client, selection):  # noqa: ANN001, ANN202
                tracker = MootdxBatchObjectTracker(endpoint_manager, selection)
                results = []
                for identity in ("stock:SH:600000", "stock:SH:600001", "stock:SH:600002"):
                    calls.append((client, identity))
                    empty = client == "primary"
                    results.append(tracker.record(identity_key=identity, value=[] if empty else [1], empty=empty))
                return results

            outcome = run_mootdx_batch_attempt(
                manager=endpoint_manager,
                batch_id="batch-three-empty-active",
                probe=passing_probe,
                client_factory=lambda selection: selection.endpoint_id,
                fetch_batch=fetch,
            )

        self.assertEqual(
            calls,
            [
                ("primary", "stock:SH:600000"),
                ("primary", "stock:SH:600001"),
                ("primary", "stock:SH:600002"),
                ("secondary", "stock:SH:600000"),
                ("secondary", "stock:SH:600001"),
                ("secondary", "stock:SH:600002"),
            ],
        )
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(outcome.winning_attempt_id, "batch-three-empty-active__attempt_2")

    def test_three_distinct_consecutive_empties_observe_blocks_without_secondary_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="observe")
            calls: list[str] = []

            def fetch(client, selection):  # noqa: ANN001, ANN202
                tracker = MootdxBatchObjectTracker(endpoint_manager, selection)
                for identity in ("stock:SH:600000", "stock:SH:600001", "stock:SH:600002"):
                    calls.append(client)
                    tracker.record(identity_key=identity, value=[], empty=True)
                return []

            outcome = run_mootdx_batch_attempt(
                manager=endpoint_manager,
                batch_id="batch-three-empty-observe",
                probe=passing_probe,
                client_factory=lambda selection: selection.endpoint_id,
                fetch_batch=fetch,
            )

        self.assertEqual(calls, ["primary", "primary", "primary"])
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.attempts[-1]["status"], "selection_blocked")

    def test_minute_semantic_probe_checks_deterministic_active_kind_sentinels(self) -> None:
        adapter = FakeMinuteProbeAdapter()
        probe = build_mootdx_minute_semantic_probe(
            subscriptions=[
                {"asset_kind": "stock", "identity_key": "stock:SH:600001", "code": "600001"},
                {"asset_kind": "stock", "identity_key": "stock:SH:600000", "code": "600000"},
                {"asset_kind": "index", "identity_key": "index:SH:000001", "code": "000001"},
            ],
            trade_date="20260717",
            adapter_factory=lambda client: adapter,
        )

        result = probe(object(), lambda profile: object())

        self.assertTrue(result["checks"]["minute_scope_sentinels"])
        self.assertEqual(
            result["sentinel_identity_keys"],
            ["stock:SH:600000", "index:SH:000001"],
        )
        self.assertEqual(adapter.calls, [("stock", "600000"), ("index", "000001")])

    def test_minute_semantic_probe_rejects_wrong_trade_date_or_invalid_label(self) -> None:
        probe = build_mootdx_minute_semantic_probe(
            subscriptions=[{"asset_kind": "board", "identity_key": "board:TDX:881001", "code": "881001"}],
            trade_date="20260717",
            adapter_factory=lambda client: FakeMinuteProbeAdapter(wrong_date=True),
        )

        result = probe(object(), lambda profile: object())

        self.assertFalse(result["checks"]["minute_scope_sentinels"])

    def test_minute_semantic_probe_supports_family_specific_fetch_method(self) -> None:
        adapter = FakeMinuteProbeAdapter()
        probe = build_mootdx_minute_semantic_probe(
            subscriptions=[{"asset_kind": "stock", "identity_key": "stock:SH:600000", "code": "600000"}],
            trade_date="20260717",
            adapter_factory=lambda client: adapter,
            fetch_rows=lambda value, subscription, date: value.fetch_full_day_minute_bars(subscription, date),
        )

        result = probe(object(), lambda profile: object())

        self.assertTrue(result["checks"]["minute_scope_sentinels"])
        self.assertEqual(adapter.calls, [("stock", "600000")])

    def test_primary_success_returns_one_complete_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []
            outcome = run_mootdx_batch_attempt(
                manager=manager(Path(tmp) / "health.json", mode="active"),
                batch_id="batch-success",
                probe=passing_probe,
                client_factory=lambda selection: selection.endpoint_id,
                fetch_batch=lambda client, selection: calls.append(client) or ["complete"],
            )

        self.assertEqual(calls, ["primary"])
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(outcome.result, ["complete"])
        self.assertEqual(outcome.winning_attempt_id, "batch-success__attempt_1")
        self.assertEqual(len(outcome.attempts), 1)

    def test_observe_primary_failure_records_would_switch_without_secondary_batch_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fetch(client, selection):  # noqa: ANN001, ANN202
                calls.append(client)
                raise TimeoutError("partial primary data must be discarded")

            outcome = run_mootdx_batch_attempt(
                manager=manager(Path(tmp) / "health.json", mode="observe"),
                batch_id="batch-observe",
                probe=passing_probe,
                client_factory=lambda selection: selection.endpoint_id,
                fetch_batch=fetch,
            )

        self.assertEqual(calls, ["primary"])
        self.assertEqual(outcome.status, "failed")
        self.assertIsNone(outcome.result)
        self.assertIsNone(outcome.winning_attempt_id)
        self.assertEqual(outcome.attempts[-1]["would_switch_to"], "secondary")
        self.assertEqual(outcome.attempts[-1]["status"], "selection_blocked")

    def test_active_replays_entire_batch_once_on_secondary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fetch(client, selection):  # noqa: ANN001, ANN202
                calls.append(client)
                if client == "primary":
                    raise ConnectionError("discard primary partial result")
                return ["secondary-complete"]

            outcome = run_mootdx_batch_attempt(
                manager=manager(Path(tmp) / "health.json", mode="active"),
                batch_id="batch-active",
                probe=passing_probe,
                client_factory=lambda selection: selection.endpoint_id,
                fetch_batch=fetch,
            )

        self.assertEqual(calls, ["primary", "secondary"])
        self.assertEqual(outcome.status, "passed")
        self.assertEqual(outcome.result, ["secondary-complete"])
        self.assertEqual(outcome.winning_attempt_id, "batch-active__attempt_2")
        self.assertTrue(outcome.attempts[-1]["failover_performed"])

    def test_unclassified_program_errors_do_not_retry_or_open_circuit(self) -> None:
        for error in (KeyError("local contract bug"), AssertionError("local invariant bug")):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as tmp:
                endpoint_manager = manager(Path(tmp) / "health.json", mode="active")
                calls: list[str] = []

                def fetch(client, selection):  # noqa: ANN001, ANN202
                    del selection
                    calls.append(client)
                    raise error

                outcome = run_mootdx_batch_attempt(
                    manager=endpoint_manager,
                    batch_id=f"batch-program-error-{type(error).__name__}",
                    probe=passing_probe,
                    client_factory=lambda selection: selection.endpoint_id,
                    fetch_batch=fetch,
                )

                self.assertEqual(calls, ["primary"])
                self.assertEqual(outcome.status, "failed")
                self.assertEqual(outcome.attempts[0]["failure_kind"], "unclassified_program_failure")
                self.assertEqual(
                    endpoint_manager._health_for("primary", transport="mootdx").state,
                    "healthy",
                )

    def test_each_failed_and_winning_attempt_closes_its_client_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clients: list[ClosableAttemptClient] = []

            def client_factory(selection):  # noqa: ANN001, ANN202
                client = ClosableAttemptClient(selection.endpoint_id)
                clients.append(client)
                return client

            outcome = run_mootdx_batch_attempt(
                manager=manager(Path(tmp) / "health.json", mode="active"),
                batch_id="batch-client-close",
                probe=passing_probe,
                client_factory=client_factory,
                fetch_batch=lambda client, selection: client.fetch(),
            )

        self.assertEqual(outcome.result, ["secondary-complete"])
        self.assertEqual([(client.endpoint_id, client.close_calls) for client in clients], [
            ("primary", 1),
            ("secondary", 1),
        ])

    def test_program_failure_still_closes_client_and_close_failure_discards_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="observe")
            program_client = ClosableAttemptClient("primary")
            program_outcome = run_mootdx_batch_attempt(
                manager=endpoint_manager,
                batch_id="batch-program-close",
                probe=passing_probe,
                client_factory=lambda selection: program_client,
                fetch_batch=lambda client, selection: (_ for _ in ()).throw(KeyError("bug")),
            )
        self.assertEqual(program_client.close_calls, 1)
        self.assertEqual(program_outcome.attempts[0]["failure_kind"], "unclassified_program_failure")

        with tempfile.TemporaryDirectory() as tmp:
            clients: list[ClosableAttemptClient] = []

            def close_failing_factory(selection):  # noqa: ANN001, ANN202
                client = ClosableAttemptClient(
                    selection.endpoint_id,
                    close_fails=selection.endpoint_id == "primary",
                )
                clients.append(client)
                return client

            close_outcome = run_mootdx_batch_attempt(
                manager=manager(Path(tmp) / "health.json", mode="active"),
                batch_id="batch-close-failure",
                probe=passing_probe,
                client_factory=close_failing_factory,
                fetch_batch=lambda client, selection: [f"{client.endpoint_id}-complete"],
            )

        self.assertEqual(close_outcome.result, ["secondary-complete"])
        self.assertEqual(close_outcome.attempts[0]["failure_kind"], "client_close_failure")
        self.assertEqual([client.close_calls for client in clients], [1, 1])

    def test_both_attempts_fail_returns_no_result_and_never_tries_third_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fetch(client, selection):  # noqa: ANN001, ANN202
                calls.append(client)
                raise OSError("attempt failed")

            outcome = run_mootdx_batch_attempt(
                manager=manager(Path(tmp) / "health.json", mode="active"),
                batch_id="batch-both-fail",
                probe=passing_probe,
                client_factory=lambda selection: selection.endpoint_id,
                fetch_batch=fetch,
            )

        self.assertEqual(calls, ["primary", "secondary"])
        self.assertEqual(outcome.status, "failed")
        self.assertIsNone(outcome.result)
        self.assertEqual(len(outcome.attempts), 2)

    def test_initial_observe_selection_blocked_never_constructs_batch_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client_calls: list[str] = []

            def probe(row, make_client):  # noqa: ANN001, ANN202
                del make_client
                return {
                    "checks": (
                        dict(CHECKS)
                        if row.endpoint_id == "secondary"
                        else {**CHECKS, "scope_sentinels": False}
                    )
                }

            outcome = run_mootdx_batch_attempt(
                manager=manager(Path(tmp) / "health.json", mode="observe"),
                batch_id="batch-preflight-blocked",
                probe=probe,
                client_factory=lambda selection: client_calls.append(selection.endpoint_id),
                fetch_batch=lambda client, selection: ["forbidden"],
            )

        self.assertEqual(client_calls, [])
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.attempts[0]["would_switch_to"], "secondary")


if __name__ == "__main__":
    unittest.main()


class FakeMinuteProbeAdapter:
    def __init__(self, *, wrong_date: bool = False) -> None:
        self.wrong_date = wrong_date
        self.calls: list[tuple[str, str]] = []

    def fetch_minute_bars(self, subscription, trade_date):  # noqa: ANN001, ANN201
        self.calls.append((str(subscription["asset_kind"]), str(subscription["code"])))
        date_value = "20260716" if self.wrong_date else trade_date
        return [
            {
                "bar_time": datetime.strptime(f"{date_value} 09:30", "%Y%m%d %H:%M").replace(
                    tzinfo=ZoneInfo("Asia/Shanghai")
                ),
                "close": 10,
            }
        ]

    def fetch_full_day_minute_bars(self, subscription, trade_date):  # noqa: ANN001, ANN201
        return self.fetch_minute_bars(subscription, trade_date)


class ClosableAttemptClient:
    def __init__(self, endpoint_id: str, *, close_fails: bool = False) -> None:
        self.endpoint_id = endpoint_id
        self.close_fails = close_fails
        self.close_calls = 0

    def fetch(self) -> list[str]:
        if self.endpoint_id == "primary":
            raise TimeoutError("primary transport failure")
        return ["secondary-complete"]

    def close(self) -> None:
        self.close_calls += 1
        if self.close_fails:
            raise RuntimeError("close failed")
