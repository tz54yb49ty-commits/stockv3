import unittest
from types import SimpleNamespace
from unittest.mock import patch


class N3CombinedChildRealRunnersTest(unittest.TestCase):
    def test_default_real_runners_are_bound_to_production_adapter_and_fail_closed(self) -> None:
        from scripts.n3_combined_child_real_runners import (
            DEFAULT_N3_REAL_IO_DEPENDENCIES,
            DEFAULT_N3_REAL_RUNNER_OPERATIONS,
            N3_REAL_RUNNER_STEP_IDS,
            build_n3_real_layer_runner,
        )

        self.assertIsNotNone(DEFAULT_N3_REAL_RUNNER_OPERATIONS.fetch_n3p_current_source)
        self.assertIsNotNone(DEFAULT_N3_REAL_RUNNER_OPERATIONS.preflight_n3p_trigger_proof)
        self.assertIsNotNone(DEFAULT_N3_REAL_RUNNER_OPERATIONS.fetch_n3_hint_source)
        self.assertIsNotNone(DEFAULT_N3_REAL_RUNNER_OPERATIONS.preflight_n3_hint_proof)
        self.assertIsNotNone(DEFAULT_N3_REAL_RUNNER_OPERATIONS.execute_n3_hint_proof)

        for step_id in N3_REAL_RUNNER_STEP_IDS:
            with self.subTest(step_id=step_id):
                runner = build_n3_real_layer_runner(step_id)
                self.assertIsNotNone(runner)
                args = SimpleNamespace(target_run_id=f"{step_id}_target")
                if step_id.startswith("n3_hint_"):
                    args.hint_proof_kind = "index_board_1m_hint_projection_v1_midday_bridge_v1"
                payload = runner(
                    args=args,
                    report={
                        "step_id": step_id,
                        "target_absence_checked": True,
                        "target_absence_check_status": "passed",
                    },
                )

                self.assertIsNotNone(DEFAULT_N3_REAL_IO_DEPENDENCIES.market_fetch_adapter)
                if step_id == "n3p_current_source_fetch":
                    self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_SCOPE_NOT_READY")
                    self.assertTrue(str(payload["reason"]).startswith("BLOCKED_N3P_SOURCE_SCOPE_NOT_READY"))
                elif step_id == "n3p_trigger_proof_preflight":
                    self.assertEqual(payload["result"], "BLOCKED_SOURCE_PAYLOAD_CONTRACT")
                    self.assertTrue(str(payload["reason"]).startswith("BLOCKED_SOURCE_PAYLOAD_CONTRACT:missing_preflight_input:"))
                elif step_id == "n3_hint_source_fetch":
                    self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_SCOPE_NOT_READY")
                    self.assertTrue(str(payload["reason"]).startswith("BLOCKED_N3_HINT_SOURCE_SCOPE_NOT_READY"))
                elif step_id == "n3_hint_proof_preflight":
                    self.assertEqual(payload["result"], "BLOCKED_N3_HINT_PROOF_PREFLIGHT")
                    self.assertTrue(str(payload["reason"]).startswith("BLOCKED_N3_HINT_PROOF_PREFLIGHT:missing_source_artifact_path"))
                else:
                    self.assertEqual(payload["result"], "BLOCKED_N3_HINT_PROOF_EXECUTE")
                    self.assertTrue(str(payload["reason"]).startswith("BLOCKED_N3_HINT_PROOF_EXECUTE:missing_contract_or_preflight_path"))
                self.assertTrue(payload["real_runner_wired"])
                self.assertTrue(payload["real_io_operation_wired"])
                self.assertTrue(payload["production_adapter_wired"])
                self.assertTrue(payload["target_absence_checked"])
                self.assertFalse(payload["execute_contract_ready"])
                self.assertFalse(payload.get("dry_run_dependency_only", False))
                self.assertFalse(payload["writes_outbox"])
                self.assertFalse(payload["consumes_outbox"])
                self.assertFalse(payload["updates_inbox_or_checkpoint"])
                self.assertFalse(payload["starts_worker"])
                self.assertFalse(payload["touches_n4_n5_n6"])

    def test_default_operations_fail_closed_when_dependency_object_is_missing(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies, N3_REAL_RUNNER_STEP_IDS, build_n3_real_layer_runner

        for step_id in N3_REAL_RUNNER_STEP_IDS:
            with self.subTest(step_id=step_id):
                runner = build_n3_real_layer_runner(step_id, dependencies=N3RealIODependencies())
                args = SimpleNamespace(target_run_id=f"{step_id}_target")
                if step_id.startswith("n3_hint_"):
                    args.hint_proof_kind = "index_board_1m_hint_projection_v1_midday_bridge_v1"
                payload = runner(
                    args=args,
                    report={
                        "step_id": step_id,
                        "target_absence_checked": True,
                        "target_absence_check_status": "passed",
                    },
                )

                self.assertEqual(payload["result"], "BLOCKED_MISSING_N3_REAL_IO")
                self.assertTrue(str(payload["reason"]).startswith(f"BLOCKED_MISSING_N3_REAL_IO:{step_id}"))
                self.assertTrue(payload["real_io_operation_wired"])
                self.assertFalse(payload["execute_contract_ready"])

    def test_injected_real_runner_operation_is_called_and_normalized(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies, N3RealRunnerOperations, build_n3_real_layer_runner

        calls: list[str] = []

        def operation(*, args, report, dependencies):
            calls.append(report["step_id"])
            self.assertEqual(dependencies.artifact_writer, "fake_artifact_writer")
            return {
                "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
                "actual_proof_minute": "1016",
                "received_target_run_id": args.target_run_id,
            }

        runner = build_n3_real_layer_runner(
            "n3p_current_source_fetch",
            operations=N3RealRunnerOperations(fetch_n3p_current_source=operation),
            dependencies=N3RealIODependencies(artifact_writer="fake_artifact_writer"),
        )
        payload = runner(
            args=SimpleNamespace(target_run_id="target_run"),
            report={
                "step_id": "n3p_current_source_fetch",
                "target_absence_checked": True,
                "target_absence_check_status": "passed",
            },
        )

        self.assertEqual(calls, ["n3p_current_source_fetch"])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertTrue(payload["real_runner_wired"])
        self.assertTrue(payload["real_io_operation_wired"])
        self.assertEqual(payload["source_payload_run_id"], "n3p_mixed_realtime_source_payload_20260630_until_1016_v1")
        self.assertEqual(payload["actual_proof_minute"], "1016")
        self.assertEqual(payload["received_target_run_id"], "target_run")

    def test_missing_real_runner_operation_fails_closed_with_exact_step_reason(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealRunnerOperations, build_n3_real_layer_runner

        runner = build_n3_real_layer_runner(
            "n3_hint_proof_execute",
            operations=N3RealRunnerOperations(),
        )
        payload = runner(
            args=SimpleNamespace(target_run_id="target_run"),
            report={
                "step_id": "n3_hint_proof_execute",
                "target_absence_checked": True,
                "target_absence_check_status": "passed",
            },
        )

        self.assertEqual(payload["result"], "BLOCKED_MISSING_N3_REAL_IO")
        self.assertEqual(payload["reason"], "BLOCKED_MISSING_N3_REAL_IO:n3_hint_proof_execute")
        self.assertFalse(payload["writes_outbox"])
        self.assertFalse(payload["touches_n4_n5_n6"])

    def test_default_operations_call_injected_production_dependency(self) -> None:
        from scripts.n3_combined_child_real_runners import N3RealIODependencies, build_n3_real_layer_runner

        class FakeProductionMarketAdapter:
            test_case = self

            def __init__(self) -> None:
                self.calls: list[str] = []

            def fetch_n3p_current_source(self, *, args, report, dependencies):
                self.calls.append("fetch_n3p_current_source")
                self.test_case.assertEqual(dependencies.market_fetch_adapter, self)
                return {
                    "actual_proof_minute": "1016",
                    "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
                    "market_data_pulled": True,
                    "database_written": True,
                    "writes_n3p_metric_rows": False,
                }

        adapter = FakeProductionMarketAdapter()
        runner = build_n3_real_layer_runner(
            "n3p_current_source_fetch",
            dependencies=N3RealIODependencies(market_fetch_adapter=adapter),
        )
        payload = runner(
            args=SimpleNamespace(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1016_v1"),
            report={
                "step_id": "n3p_current_source_fetch",
                "target_absence_checked": True,
                "target_absence_check_status": "passed",
            },
        )

        self.assertEqual(adapter.calls, ["fetch_n3p_current_source"])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertTrue(payload["real_io_operation_wired"])
        self.assertTrue(payload["market_data_pulled"])
        self.assertTrue(payload["database_written"])
        self.assertFalse(payload["writes_n3p_metric_rows"])

    def test_default_production_adapter_calls_module_level_entrypoints(self) -> None:
        from scripts.n3_combined_child_real_runners import build_n3_real_layer_runner

        entrypoint_calls: list[str] = []

        def fake_entrypoint(*, args, report, dependencies):
            entrypoint_calls.append(report["step_id"])
            return {
                "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                "target_run_id": args.target_run_id,
                "entrypoint_called": report["step_id"],
                "writes_outbox": False,
                "consumes_outbox": False,
                "updates_inbox_or_checkpoint": False,
                "starts_worker": False,
                "touches_n4_n5_n6": False,
            }

        patches = [
            patch("scripts.n3_combined_child_real_runners.run_n3p_current_source_fetch", fake_entrypoint),
            patch("scripts.n3_combined_child_real_runners.run_n3p_trigger_proof_preflight", fake_entrypoint),
            patch("scripts.n3_combined_child_real_runners.run_n3_hint_source_fetch", fake_entrypoint),
            patch("scripts.n3_combined_child_real_runners.run_n3_hint_proof_preflight", fake_entrypoint),
            patch("scripts.n3_combined_child_real_runners.run_n3_hint_proof_execute", fake_entrypoint),
        ]
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

        for step_id in (
            "n3p_current_source_fetch",
            "n3p_trigger_proof_preflight",
            "n3_hint_source_fetch",
            "n3_hint_proof_preflight",
            "n3_hint_proof_execute",
        ):
            with self.subTest(step_id=step_id):
                args = SimpleNamespace(target_run_id=f"{step_id}_target")
                if step_id.startswith("n3_hint_"):
                    args.hint_proof_kind = "index_board_1m_hint_projection_v1_midday_bridge_v1"
                runner = build_n3_real_layer_runner(step_id)
                payload = runner(
                    args=args,
                    report={
                        "step_id": step_id,
                        "target_absence_checked": True,
                        "target_absence_check_status": "passed",
                    },
                )

                self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
                self.assertEqual(payload["entrypoint_called"], step_id)
                self.assertFalse(payload["writes_outbox"])
                self.assertFalse(payload["touches_n4_n5_n6"])

        self.assertEqual(
            entrypoint_calls,
            [
                "n3p_current_source_fetch",
                "n3p_trigger_proof_preflight",
                "n3_hint_source_fetch",
                "n3_hint_proof_preflight",
                "n3_hint_proof_execute",
            ],
        )

    def test_default_production_adapter_exposes_hint_frequency8_entrypoint_without_implicit_io(self) -> None:
        from scripts.n3_combined_child_real_runners import N3ProductionRealIOAdapter, N3RealIODependencies

        adapter = N3ProductionRealIOAdapter()
        self.assertTrue(callable(getattr(adapter, "fetch_n3_hint_frequency8_source", None)))

        payload = adapter.fetch_n3_hint_frequency8_source(
            args=SimpleNamespace(
                target_run_id="n3_hint_index_board_1m_source_payload_20260630_until_1500_v1",
                hint_proof_kind="index_board_1m_hint_projection_v1_midday_bridge_v1",
            ),
            report={"step_id": "n3_hint_source_fetch"},
            dependencies=N3RealIODependencies(market_fetch_adapter=adapter),
        )

        self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_SCOPE_NOT_READY")
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["writes_outbox"])
        self.assertFalse(payload["touches_n4_n5_n6"])

    def test_default_production_adapter_exposes_hint_proof_preflight_entrypoint(self) -> None:
        from scripts.n3_combined_child_real_runners import N3ProductionRealIOAdapter, N3RealIODependencies

        calls = []

        class Backend:
            def build_n3_hint_proof_preflight(self, *, args, report, dependencies):
                calls.append((args.target_run_id, report["step_id"], dependencies.artifact_reader))
                return {
                    "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                    "target_run_id": args.target_run_id,
                    "stock_rows": 0,
                    "market_data_pulled": False,
                    "database_written": False,
                    "writes_outbox": False,
                }

        adapter = N3ProductionRealIOAdapter(hint_proof_preflight_backend=Backend())
        self.assertTrue(callable(getattr(adapter, "build_n3_hint_proof_preflight", None)))

        payload = adapter.build_n3_hint_proof_preflight(
            args=SimpleNamespace(
                target_run_id="realtime_hint_projection_metric_20260701_until_1044__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1",
                hint_proof_kind="index_board_1m_hint_projection_v1_midday_bridge_v1",
            ),
            report={"step_id": "n3_hint_proof_preflight"},
            dependencies=N3RealIODependencies(artifact_reader=adapter),
        )

        self.assertEqual(calls, [(payload["target_run_id"], "n3_hint_proof_preflight", adapter)])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["writes_outbox"])

    def test_default_production_adapter_exposes_hint_proof_execute_entrypoint(self) -> None:
        from scripts.n3_combined_child_real_runners import N3ProductionRealIOAdapter, N3RealIODependencies

        calls = []

        class Backend:
            def execute_n3_hint_projection_write_plan(self, *, args, report, dependencies):
                calls.append((args.target_run_id, report["step_id"], dependencies.db_writer))
                return {
                    "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                    "target_run_id": args.target_run_id,
                    "rows_written": {"index": 0, "board": 6, "stock": 0},
                    "database_written": True,
                    "writes_outbox": False,
                    "stock_rows": 0,
                }

        adapter = N3ProductionRealIOAdapter(hint_proof_execute_backend=Backend())
        self.assertTrue(callable(getattr(adapter, "execute_n3_hint_projection_write_plan", None)))

        payload = adapter.execute_n3_hint_projection_write_plan(
            args=SimpleNamespace(
                target_run_id="realtime_hint_projection_metric_20260701_until_1044__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1",
                hint_proof_kind="index_board_1m_hint_projection_v1_midday_bridge_v1",
            ),
            report={"step_id": "n3_hint_proof_execute"},
            dependencies=N3RealIODependencies(db_writer=adapter),
        )

        self.assertEqual(calls, [(payload["target_run_id"], "n3_hint_proof_execute", adapter)])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertTrue(payload["database_written"])
        self.assertFalse(payload["writes_outbox"])
        self.assertEqual(payload["stock_rows"], 0)

    def test_default_hint_source_wrapper_reaches_frequency8_entrypoint(self) -> None:
        from scripts.n3_combined_child_real_runners import N3ProductionRealIOAdapter, build_n3_real_layer_runner

        calls: list[str] = []
        test_case = self

        def fake_frequency8_entrypoint(adapter, *, args, report, dependencies):
            calls.append(f"{report['step_id']}:{args.hint_proof_kind}")
            test_case.assertIs(dependencies.market_fetch_adapter, adapter)
            return {
                "actual_proof_minute": "1500",
                "source_artifact_path": "docs/intraday_live_current/20260630/N3_hint_index_board_1m_1500_midday_bridge_frequency8_payload.json",
                "payload_hash": "hint_hash",
                "asset_scope": "index_board_only",
                "stock_rows": 0,
                "market_data_pulled": True,
                "database_written": False,
                "writes_outbox": False,
            }

        with patch.object(N3ProductionRealIOAdapter, "fetch_n3_hint_frequency8_source", fake_frequency8_entrypoint):
            runner = build_n3_real_layer_runner("n3_hint_source_fetch")
            payload = runner(
                args=SimpleNamespace(
                    target_run_id="n3_hint_index_board_1m_source_payload_20260630_until_1500_v1",
                    hint_proof_kind="index_board_1m_hint_projection_v1_midday_bridge_v1",
                ),
                report={
                    "step_id": "n3_hint_source_fetch",
                    "target_absence_checked": True,
                    "target_absence_check_status": "passed",
                },
            )

        self.assertEqual(calls, ["n3_hint_source_fetch:index_board_1m_hint_projection_v1_midday_bridge_v1"])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(payload["asset_scope"], "index_board_only")
        self.assertEqual(payload["stock_rows"], 0)
        self.assertFalse(payload["writes_outbox"])
        self.assertFalse(payload["touches_n4_n5_n6"])

    def test_default_production_adapter_reaches_lower_level_hook_module(self) -> None:
        from scripts.n3_combined_child_real_runners import build_n3_real_layer_runner

        hook_calls: list[str] = []

        def fake_hook(*, args, report, dependencies):
            hook_calls.append(f"{report['step_id']}:{args.target_run_id}")
            return {
                "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                "target_run_id": args.target_run_id,
                "lower_level_hook_called": True,
                "writes_outbox": False,
            }

        with patch(
            "scripts.n3_combined_child_production_hooks.n3p_current_source_fetch_and_register",
            fake_hook,
        ):
            runner = build_n3_real_layer_runner("n3p_current_source_fetch")
            payload = runner(
                args=SimpleNamespace(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1016_v1"),
                report={
                    "step_id": "n3p_current_source_fetch",
                    "target_absence_checked": True,
                    "target_absence_check_status": "passed",
                },
            )

        self.assertEqual(hook_calls, ["n3p_current_source_fetch:n3p_mixed_realtime_source_payload_20260630_until_1016_v1"])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertTrue(payload["lower_level_hook_called"])
        self.assertFalse(payload["writes_outbox"])

    def test_production_adapter_wires_concrete_n3p_source_payload_provider(self) -> None:
        from scripts.n3_combined_child_real_runners import N3ProductionRealIOAdapter, N3RealIODependencies
        from scripts.n3p_current_source_fetch_provider import compute_n3p_current_source_payload_hash

        calls: list[str] = []

        class Backend:
            def load_n3p_current_source_scope(self, *, args, report, dependencies):
                calls.append("scope")
                return {
                    "for_trade_date": args.for_trade_date,
                    "n4_context_status": "passed",
                    "subscription_status": "passed",
                    "a1_cumulative_status": "passed",
                }

            def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope):
                calls.append("fetch")
                return {
                    "proof_input_time": "2026-06-30T10:16:00+08:00",
                    "stock_quote_rows": [
                        {
                            "asset_kind": "stock",
                            "identity_key": "stock:SZ:300001",
                            "price": 1,
                            "amount": 100,
                            "source_time": "2026-06-30T10:16:00+08:00",
                            "source_marker": "mootdx_quotes",
                        }
                    ],
                    "index_board_1m_rows": [
                        {
                            "asset_kind": "board",
                            "identity_key": "board:TDX:881001",
                            "bar_time": "2026-06-30T10:16:00+08:00",
                            "open": 1,
                            "high": 1,
                            "low": 1,
                            "close": 1,
                            "amount": 100,
                            "source_marker": "mootdx_index_frequency_8",
                        }
                    ],
                }

            def write_n3p_current_source_artifacts(self, *, args, report, dependencies, payload, fetch_report):
                calls.append("artifact")
                return {
                    "payload_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_payload.json",
                    "report_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_report.json",
                    "payload_hash": compute_n3p_current_source_payload_hash(payload),
                }

            def register_n3p_source_payload_run(self, *, args, report, dependencies, source_payload):
                calls.append("register")
                return {"source_payload_registered": True, "database_written": True}

        adapter = N3ProductionRealIOAdapter(n3p_source_fetch_backend=Backend())
        dependencies = N3RealIODependencies(
            market_fetch_adapter=adapter,
            source_payload_registrar=adapter,
        )
        fetched = adapter.fetch_n3p_current_source_payload(
            args=SimpleNamespace(
                for_trade_date="20260630",
                target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
                requested_until_hhmm="1016",
            ),
            report={"step_id": "n3p_current_source_fetch", "target_absence_checked": True},
            dependencies=dependencies,
        )
        registered = adapter.register_n3p_source_payload_run(
            args=SimpleNamespace(target_run_id=fetched["source_payload_run_id"]),
            report={"step_id": "n3p_current_source_fetch"},
            dependencies=dependencies,
            source_payload=fetched,
        )

        self.assertEqual(calls, ["scope", "fetch", "artifact", "register"])
        self.assertEqual(fetched["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(fetched["actual_until_hhmm"], "1016")
        self.assertEqual(fetched["payload_hash"], compute_n3p_current_source_payload_hash(fetched))
        self.assertEqual(fetched["source_payload_run_id"], "n3p_mixed_realtime_source_payload_20260630_until_1016_v1")
        self.assertFalse(fetched["writes_n3p_metric_rows"])
        self.assertFalse(fetched["writes_outbox"])
        self.assertTrue(registered["database_written"])


if __name__ == "__main__":
    unittest.main()
