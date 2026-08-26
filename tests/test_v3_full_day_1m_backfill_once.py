from __future__ import annotations

from pathlib import Path
import inspect
import tempfile
import unittest
from unittest.mock import patch

from ashare_v3.market.mootdx_batch_attempt import MootdxBatchAttemptOutcome
from ashare_v3.mootdx_client import EndpointConfig, MootdxEndpointManager
from scripts.run_v3_20260612_full_day_1m_backfill_once import (
    build_adapter_rows,
    winning_transport_provenance,
)


CHECKS = {
    "stock_quote": True,
    "stock_daily_bars": True,
    "index_daily_bars": True,
    "scope_sentinels": True,
    "minute_scope_sentinels": True,
}


def manager(path: Path, mode: str) -> MootdxEndpointManager:
    return MootdxEndpointManager(
        endpoint_pool_version="test",
        transport="mootdx",
        endpoints=(
            EndpointConfig("primary", "192.0.2.1", 7709, 10, True, False, "frozen", "frozen", "protocol_passed"),
            EndpointConfig("secondary", "192.0.2.2", 7709, 20, True, False, "frozen", "frozen", "protocol_passed"),
        ),
        n1_failover_mode="observe",
        n3_failover_mode=mode,
        circuit_open_seconds=300,
        required_empty_object_threshold=3,
        health_cache_path=path,
    )


def passing_probe(row, make_client):  # noqa: ANN001, ANN201
    del row, make_client
    return {"checks": dict(CHECKS)}


class FakeAdapter:
    def __init__(self, endpoint_id: str, calls: list[tuple[str, str]], *, fail_primary: bool) -> None:
        self.endpoint_id = endpoint_id
        self.calls = calls
        self.fail_primary = fail_primary

    def fetch_minute_bars(self, subscription, trade_date):  # noqa: ANN001, ANN201
        del trade_date
        identity = str(subscription["identity_key"])
        self.calls.append((self.endpoint_id, identity))
        if self.fail_primary and self.endpoint_id == "primary":
            raise TimeoutError("primary transport failed")
        return [{"bar_time": "2026-06-12T09:30:00+08:00"}] * 240


class FullDayBackfillEndpointTest(unittest.TestCase):
    def test_winning_transport_provenance_enters_fact_builder_writer_and_success_report(self) -> None:
        from ashare_v3.market import v3_full_day_replay_plan as plan
        from scripts import run_v3_20260612_full_day_1m_backfill_once as runner

        provenance = {
            "batch_id": "batch-1",
            "winning_attempt_id": "attempt-2",
            "attempt_id": "attempt-2",
            "endpoint_pool_version": "pool-v1",
            "endpoint_id": "secondary",
            "endpoint_host": "192.0.2.2",
            "endpoint_port": 7709,
            "transport": "tdxpy",
            "source_transport": "tdxpy",
            "pool_probe_summary": {"passed_endpoint_ids": ["secondary"]},
            "endpoint_probe_results": [{"endpoint_id": "secondary", "passed": True}],
        }
        context = {
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "exchange": "SH",
            "code": "600000",
        }
        adapter_rows = {
            "stock:SH:600000": [
                {
                    "bar_time": "2026-06-12T09:30:00+08:00",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                    "amount": 1,
                }
                for _ in range(240)
            ]
        }
        records, object_results = plan.build_full_day_backfill_records_for_context(
            context_rows=[context],
            retained_rows_by_identity={},
            adapter_rows_by_identity=adapter_rows,
            backfill_run_id="backfill-run",
            source_condition_run_id="condition-run",
            for_trade_date="20260612",
            transport_provenance=provenance,
        )
        self.assertEqual(records["stock"][0]["raw_json"]["source_transport"], "tdxpy")
        self.assertEqual(records["stock"][0]["raw_json"]["attempt_id"], "attempt-2")
        self.assertEqual(object_results[0]["transport_provenance"], provenance)

        fetch_results = [{
            "status": "passed",
            "endpoint_attempt": {
                "batch_id": "batch-1",
                "winning_attempt_id": "attempt-2",
                "attempts": [provenance],
            },
        }]
        self.assertEqual(winning_transport_provenance(fetch_results), provenance)

        reports: list[dict] = []
        with (
            patch.object(runner.plan, "require_full_day_backfill_execute_flags"),
            patch.object(runner.plan, "fetch_full_day_backfill_context_rows", return_value=[context]),
            patch.object(runner.plan, "fetch_retained_today_minute_rows_by_identity", return_value={}),
            patch.object(runner, "build_adapter_rows", return_value=(adapter_rows, fetch_results)),
            patch.object(
                runner.plan,
                "build_full_day_backfill_records_for_context",
                return_value=(records, object_results),
            ) as builder,
            patch.object(
                runner.plan,
                "write_full_day_backfill_to_db",
                return_value={
                    "records_planned": 240,
                    "p_counts": {"P0": 0, "P1": 0, "P2": 0},
                    "pre_counts": {},
                    "post_counts": {},
                    "quality_items": [],
                },
            ) as writer,
            patch.object(runner.plan, "write_json", side_effect=lambda path, value: reports.append(value)),
            patch.object(runner.plan, "write_text"),
        ):
            result = runner.main(["--execute", "--user-confirmed"])

        self.assertEqual(result, 0)
        self.assertEqual(builder.call_args.kwargs["transport_provenance"], provenance)
        self.assertEqual(writer.call_args.kwargs["transport_provenance"], provenance)
        self.assertEqual(reports[-1]["transport_provenance"], provenance)

    def test_production_entrypoint_delegates_default_transport_to_shared_batch_factory(self) -> None:
        from scripts import run_v3_20260612_full_day_1m_backfill_once as runner

        signature = inspect.signature(runner.build_adapter_rows)
        self.assertIsNone(signature.parameters["endpoint_client_factory"].default)
        self.assertNotIn("create_mootdx_client", inspect.getsource(runner))

    def test_all_retained_fast_path_skips_manager_probe_and_client(self) -> None:
        row = {"asset_kind": "stock", "identity_key": "stock:SH:600000", "code": "600000"}
        retained = {"stock:SH:600000": [{}] * 240}
        with patch(
            "scripts.run_v3_20260612_full_day_1m_backfill_once.MootdxEndpointManager.from_toml"
        ) as from_toml:
            adapter_rows, results = build_adapter_rows(
                context_rows=[row],
                retained_rows_by_identity=retained,
                minute_trade_date="20260612",
                progress_every=100,
                endpoint_probe=lambda *args: self.fail("probe must not run"),
                endpoint_client_factory=lambda selection: self.fail("client must not be built"),
            )

        from_toml.assert_not_called()
        self.assertEqual(adapter_rows, {})
        self.assertEqual(results[0]["status"], "skipped_fetch")

    def test_default_minute_probe_uses_family_specific_required_checks(self) -> None:
        outcome = MootdxBatchAttemptOutcome(
            batch_id="full_day_1m_backfill:20260612",
            status="passed",
            result=({}, []),
            winning_attempt_id="attempt-1",
            attempts=(),
        )
        with patch(
            "scripts.run_v3_20260612_full_day_1m_backfill_once.run_mootdx_batch_attempt",
            return_value=outcome,
        ) as run_attempt:
            build_adapter_rows(
                context_rows=[
                    {"asset_kind": "stock", "identity_key": "stock:SH:600000", "code": "600000"}
                ],
                retained_rows_by_identity={},
                minute_trade_date="20260612",
                progress_every=100,
                endpoint_manager=object(),
            )

        self.assertEqual(run_attempt.call_args.kwargs["required_checks"], ("minute_scope_sentinels",))

    def test_active_transport_failure_replays_complete_batch_on_secondary(self) -> None:
        rows = [
            {"asset_kind": "stock", "identity_key": "stock:SH:600000", "code": "600000"},
            {"asset_kind": "stock", "identity_key": "stock:SH:600001", "code": "600001"},
        ]
        calls: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            adapter_rows, results = build_adapter_rows(
                context_rows=rows,
                retained_rows_by_identity={},
                minute_trade_date="20260612",
                progress_every=100,
                endpoint_manager=manager(Path(tmp) / "health.json", "active"),
                endpoint_probe=passing_probe,
                endpoint_client_factory=lambda selection: selection.endpoint_id,
                adapter_factory=lambda endpoint_id: FakeAdapter(endpoint_id, calls, fail_primary=True),
            )

        self.assertEqual(
            calls,
            [
                ("primary", "stock:SH:600000"),
                ("secondary", "stock:SH:600000"),
                ("secondary", "stock:SH:600001"),
            ],
        )
        self.assertEqual(set(adapter_rows), {"stock:SH:600000", "stock:SH:600001"})
        self.assertTrue(all(row["endpoint_attempt"]["winning_attempt_id"].endswith("__attempt_2") for row in results))

    def test_observe_transport_failure_never_fetches_secondary(self) -> None:
        rows = [{"asset_kind": "stock", "identity_key": "stock:SH:600000", "code": "600000"}]
        calls: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            adapter_rows, results = build_adapter_rows(
                context_rows=rows,
                retained_rows_by_identity={},
                minute_trade_date="20260612",
                progress_every=100,
                endpoint_manager=manager(Path(tmp) / "health.json", "observe"),
                endpoint_probe=passing_probe,
                endpoint_client_factory=lambda selection: selection.endpoint_id,
                adapter_factory=lambda endpoint_id: FakeAdapter(endpoint_id, calls, fail_primary=True),
            )

        self.assertEqual(calls, [("primary", "stock:SH:600000")])
        self.assertEqual(adapter_rows, {})
        self.assertEqual(results[0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
