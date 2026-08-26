import importlib
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from scripts.n3_combined_child_real_runners import N3RealIODependencies, N3RealRunnerOperations


N4_CONTEXT_RUN_ID = "trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1"
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"
MIDDAY_BRIDGE_PROOF_KIND = "index_board_1m_hint_projection_v1_midday_bridge_v1"


def _base_argv(*, hint: bool = False, source_run_id: str = "source_run", target_run_id: str = "target_run") -> list[str]:
    argv = [
        "--for-trade-date",
        "20260630",
        "--n4-context-run-id",
        N4_CONTEXT_RUN_ID,
        "--subscription-run-id",
        SUBSCRIPTION_RUN_ID,
        "--source-condition-run-id",
        "condition_layer_20260629_source_20260629_for_20260630_v1",
        "--source-run-id",
        source_run_id,
        "--target-run-id",
        target_run_id,
        "--execute",
        "--user-confirmed",
        "--json",
    ]
    if hint:
        argv.extend(["--hint-proof-kind", MIDDAY_BRIDGE_PROOF_KIND])
    return argv


def _run_module(module_name: str, argv: list[str], **kwargs):
    module = importlib.import_module(module_name)
    stdout = StringIO()
    with redirect_stdout(stdout):
        code = module.main(argv, **kwargs)
    return code, json.loads(stdout.getvalue())


class N3CombinedChildRealIOImplementationTest(unittest.TestCase):
    def test_production_n3p_source_fetch_binds_low_level_market_adapter_without_network(self) -> None:
        from scripts.n3_combined_child_real_runners import N3ProductionRealIOAdapter
        from scripts.n3p_current_source_fetch_provider import N3PCurrentMarketFetchAdapter

        adapter = N3ProductionRealIOAdapter()

        backend = adapter._n3p_source_fetch_provider.backend
        self.assertIsInstance(backend.market_fetcher, N3PCurrentMarketFetchAdapter)

    def test_production_hint_source_fetch_binds_low_level_market_adapter_without_network(self) -> None:
        from scripts.n3_combined_child_real_runners import N3ProductionRealIOAdapter
        from scripts.n3_hint_frequency8_source_provider import N3HintFrequency8MarketFetchAdapter

        adapter = N3ProductionRealIOAdapter()

        backend = adapter._n3_hint_source_fetch_provider.backend
        self.assertIsInstance(backend.market_fetcher, N3HintFrequency8MarketFetchAdapter)

    def test_default_confirmed_execute_fails_closed_without_remaining_production_entrypoints(self) -> None:
        # N3P current-source fetch, HINT frequency=8 source, HINT proof
        # preflight, and HINT proof execute expose production entrypoints.
        # Without exact materialized artifacts, execute still fails closed.
        wrappers = [
            ("scripts.run_n3_hint_index_board_1m_source_fetch_once", True, "n3_hint_source_fetch"),
            ("scripts.run_n3_hint_index_board_1m_proof_preflight_once", True, "n3_hint_proof_preflight"),
            ("scripts.run_n3_hint_index_board_1m_proof_execute_once", True, "n3_hint_proof_execute"),
        ]
        for module_name, is_hint, step_id in wrappers:
            with self.subTest(module=module_name):
                patcher = (
                    patch(
                        "scripts.n3_hint_frequency8_source_provider._connect_db",
                        side_effect=RuntimeError("test scope loader unavailable"),
                    )
                    if step_id == "n3_hint_source_fetch"
                    else None
                )
                if patcher is None:
                    code, payload = _run_module(module_name, _base_argv(hint=is_hint))
                else:
                    with patcher:
                        code, payload = _run_module(module_name, _base_argv(hint=is_hint))

                self.assertEqual(code, 2)
                if step_id == "n3_hint_source_fetch":
                    self.assertEqual(payload["result"], "BLOCKED_N3_HINT_SOURCE_SCOPE_NOT_READY")
                    self.assertTrue(str(payload["reason"]).startswith("BLOCKED_N3_HINT_SOURCE_SCOPE_NOT_READY"))
                elif step_id == "n3_hint_proof_preflight":
                    self.assertEqual(payload["result"], "BLOCKED_N3_HINT_PROOF_PREFLIGHT")
                    self.assertTrue(str(payload["reason"]).startswith("BLOCKED_N3_HINT_PROOF_PREFLIGHT:missing_source_artifact_path"))
                else:
                    self.assertEqual(payload["result"], "BLOCKED_N3_HINT_PROOF_EXECUTE")
                    self.assertTrue(str(payload["reason"]).startswith("BLOCKED_N3_HINT_PROOF_EXECUTE:missing_contract_or_preflight_path"))
                self.assertTrue(payload["target_absence_checked"])
                self.assertTrue(payload["real_io_operation_wired"])
                self.assertTrue(payload["production_adapter_wired"])
                self.assertFalse(payload["writes_outbox"])
                self.assertFalse(payload["consumes_outbox"])
                self.assertFalse(payload["updates_inbox_or_checkpoint"])
                self.assertFalse(payload["starts_worker"])
                self.assertFalse(payload["touches_n4_n5_n6"])

    def test_default_n3p_preflight_entrypoint_is_bound_to_production_provider(self) -> None:
        from scripts.n3_combined_child_real_runners import N3ProductionRealIOAdapter

        class Backend:
            def build_n3p_trigger_proof_preflight(self, *, args, report, dependencies):
                self.called = (args.source_run_id, args.target_run_id, report["step_id"], dependencies.artifact_reader)
                return {
                    "proposed_n3p_metric_target_run_id": args.target_run_id,
                    "source_payload_run_id": args.source_run_id,
                    "actual_until_hhmm": "1530",
                    "plan_only_row_counts": {"stock": 2026, "index": 18, "board": 278, "total": 2322},
                    "metric_ready": 2301,
                    "metric_not_ready": 21,
                    "not_ready_reason_distribution": {
                        "formal_amount_chain_missing:M:prev_quarterly_avg": 13,
                        "formal_amount_chain_missing:Q:prev_yearly_avg": 8,
                    },
                    "target_absence": {"status": "passed"},
                    "rollback_ready": True,
                    "not_n5_final_proof": True,
                    "action_confirmation_ready": False,
                    "database_written": False,
                    "market_data_pulled": False,
                }

        backend = Backend()
        adapter = N3ProductionRealIOAdapter(n3p_source_fetch_backend=backend)
        code, payload = _run_module(
            "scripts.run_n3p_trigger_proof_preflight_once",
            _base_argv(
                source_run_id="n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
                target_run_id=(
                    "realtime_action_confirmation_metric_20260630_until_1530__asset_all__"
                    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                    f"{SUBSCRIPTION_RUN_ID}"
                ),
            ),
            real_io_dependencies=N3RealIODependencies(
                artifact_reader=adapter,
                db_connection=adapter,
            ),
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(
            backend.called,
            (
                "n3p_mixed_realtime_source_payload_20260630_until_1530_v1",
                (
                    "realtime_action_confirmation_metric_20260630_until_1530__asset_all__"
                    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                    f"{SUBSCRIPTION_RUN_ID}"
                ),
                "n3p_trigger_proof_preflight",
                adapter,
            ),
        )
        self.assertEqual(payload["plan_only_row_counts"]["total"], 2322)
        self.assertTrue(payload["not_n5_final_proof"])
        self.assertFalse(payload["action_confirmation_ready"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["market_data_pulled"])
        self.assertFalse(payload["writes_outbox"])
        self.assertFalse(payload["touches_n4_n5_n6"])

    def test_n3p_preflight_plan_only_materializes_contract_and_preflight_artifacts(self) -> None:
        from scripts.n3_combined_child_real_runners import N3ProductionRealIOAdapter

        target_run_id = (
            "realtime_action_confirmation_metric_20260630_until_1016__asset_all__"
            "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
            f"{SUBSCRIPTION_RUN_ID}"
        )
        source_run_id = "n3p_mixed_realtime_source_payload_20260630_until_1016_v1"

        class Backend:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def build_n3p_trigger_proof_preflight(self, *, args, report, dependencies):
                self.calls.append(report["step_id"])
                return {
                    "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                    "target_run_id": args.target_run_id,
                    "source_payload_run_id": args.source_run_id,
                    "source_payload_hash": "hash1016",
                    "for_trade_date": args.for_trade_date,
                    "source_trade_date": "20260629",
                    "n4_context_run_id": args.n4_context_run_id,
                    "subscription_run_id": args.subscription_run_id,
                    "plan_only_row_counts": {"stock": 2026, "index": 18, "board": 278, "total": 2322},
                    "metric_ready": 2301,
                    "metric_not_ready": 21,
                    "target_absence": {"status": "passed"},
                    "rollback_readiness": {"status": "ready"},
                    "not_n5_final_proof": True,
                    "writes_outbox": False,
                    "writer_contract": {
                        "target_run_id": args.target_run_id,
                        "source_scope": {
                            "for_trade_date": args.for_trade_date,
                            "source_trade_date": "20260629",
                            "source_payload_run_id": args.source_run_id,
                            "source_payload_hash": "hash1016",
                            "source_subscription_run_id": args.subscription_run_id,
                            "n4_context_run_id": args.n4_context_run_id,
                        },
                        "expected_rows": {
                            "stock": 2026,
                            "index": 18,
                            "board": 278,
                            "total": 2322,
                            "metric_ready": 2301,
                            "metric_not_ready": 21,
                        },
                    },
                    "writer_preflight": {
                        "result": "PREFLIGHT_PASS",
                        "target_run_id": args.target_run_id,
                        "source_payload_run_id": args.source_run_id,
                        "source_payload_hash": "hash1016",
                        "plan_only_row_counts": {"stock": 2026, "index": 18, "board": 278, "total": 2322},
                        "metric_ready": 2301,
                        "metric_not_ready": 21,
                        "writes_outbox": False,
                        "not_n5_final_proof": True,
                    },
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            contract_path = Path(tmpdir) / "contract.json"
            preflight_path = Path(tmpdir) / "preflight.json"
            backend = Backend()
            adapter = N3ProductionRealIOAdapter(n3p_trigger_proof_preflight_backend=backend)
            argv = _base_argv(source_run_id=source_run_id, target_run_id=target_run_id)
            argv.remove("--execute")
            argv.remove("--user-confirmed")
            argv.extend(
                [
                    "--contract-path",
                    str(contract_path),
                    "--preflight-path",
                    str(preflight_path),
                ]
            )

            code, payload = _run_module(
                "scripts.run_n3p_trigger_proof_preflight_once",
                argv,
                real_io_dependencies=N3RealIODependencies(
                    artifact_reader=adapter,
                    db_connection=adapter,
                ),
            )

            self.assertEqual(code, 0)
            self.assertEqual(backend.calls, ["n3p_trigger_proof_preflight"])
            self.assertTrue(payload["preflight_artifacts_materialized"])
            self.assertTrue(contract_path.exists())
            self.assertTrue(preflight_path.exists())
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))

        self.assertEqual(contract["target_run_id"], target_run_id)
        self.assertEqual(contract["source_scope"]["source_payload_run_id"], source_run_id)
        self.assertEqual(contract["source_scope"]["source_payload_hash"], "hash1016")
        self.assertEqual(contract["expected_rows"]["total"], 2322)
        self.assertEqual(preflight["target_run_id"], target_run_id)
        self.assertEqual(preflight["source_payload_run_id"], source_run_id)
        self.assertEqual(preflight["source_payload_hash"], "hash1016")
        self.assertEqual(preflight["plan_only_row_counts"]["total"], 2322)
        self.assertEqual(preflight["metric_ready"], 2301)
        self.assertEqual(preflight["metric_not_ready"], 21)
        self.assertFalse(preflight["writes_outbox"])

    def test_hint_preflight_plan_only_materializes_contract_and_preflight_artifacts(self) -> None:
        from scripts.n3_combined_child_real_runners import N3ProductionRealIOAdapter

        target_run_id = (
            "realtime_hint_projection_metric_20260630_until_1044__asset_index_board__"
            f"{MIDDAY_BRIDGE_PROOF_KIND}__{SUBSCRIPTION_RUN_ID}"
        )
        source_artifact_path = (
            "docs/intraday_live_current/20260630/"
            "N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json"
        )

        class Backend:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def build_n3_hint_proof_preflight(self, *, args, report, dependencies):
                self.calls.append(report["step_id"])
                return {
                    "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                    "target_run_id": args.target_run_id,
                    "source_artifact_path": args.source_artifact_path,
                    "source_artifact_payload_hash": "hint-hash",
                    "source_artifact_file_sha256": "file-sha",
                    "proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
                    "proof_rows_total": 6,
                    "rows_by_asset": {"board": 6, "index": 0, "stock": 0},
                    "stock_rows": 0,
                    "projection_type_distribution": {"volume_up": 1, "shrink_down": 0, "none": 5, "unknown": 0},
                    "writes_outbox": False,
                    "writer_contract": {
                        "target_run_id": args.target_run_id,
                        "source_artifact_path": args.source_artifact_path,
                        "source_artifact_payload_hash": "hint-hash",
                        "proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
                        "expected_rows": {"board": 6, "index": 0, "stock": 0, "total": 6},
                        "write_plan": {"rows_by_asset": {"board": 6, "index": 0, "stock": 0}},
                    },
                    "writer_preflight": {
                        "result": "PREFLIGHT_PASS",
                        "target_run_id": args.target_run_id,
                        "source_artifact_path": args.source_artifact_path,
                        "source_artifact_payload_hash": "hint-hash",
                        "proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
                        "proof_rows_total": 6,
                        "rows_by_asset": {"board": 6, "index": 0, "stock": 0},
                        "stock_rows": 0,
                        "writes_outbox": False,
                    },
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            contract_path = Path(tmpdir) / "hint_contract.json"
            preflight_path = Path(tmpdir) / "hint_preflight.json"
            backend = Backend()
            adapter = N3ProductionRealIOAdapter(hint_proof_preflight_backend=backend)
            argv = _base_argv(hint=True, target_run_id=target_run_id)
            argv.remove("--execute")
            argv.remove("--user-confirmed")
            argv.extend(
                [
                    "--source-artifact-path",
                    source_artifact_path,
                    "--contract-path",
                    str(contract_path),
                    "--preflight-path",
                    str(preflight_path),
                ]
            )

            code, payload = _run_module(
                "scripts.run_n3_hint_index_board_1m_proof_preflight_once",
                argv,
                real_io_dependencies=N3RealIODependencies(
                    artifact_reader=adapter,
                    db_connection=adapter,
                ),
            )

            self.assertEqual(code, 0)
            self.assertEqual(backend.calls, ["n3_hint_proof_preflight"])
            self.assertTrue(payload["preflight_artifacts_materialized"])
            self.assertTrue(contract_path.exists())
            self.assertTrue(preflight_path.exists())
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))

        self.assertEqual(contract["target_run_id"], target_run_id)
        self.assertEqual(contract["source_artifact_path"], source_artifact_path)
        self.assertEqual(contract["source_artifact_payload_hash"], "hint-hash")
        self.assertEqual(contract["proof_kind"], MIDDAY_BRIDGE_PROOF_KIND)
        self.assertEqual(contract["expected_rows"]["total"], 6)
        self.assertEqual(preflight["target_run_id"], target_run_id)
        self.assertEqual(preflight["source_artifact_path"], source_artifact_path)
        self.assertEqual(preflight["proof_kind"], MIDDAY_BRIDGE_PROOF_KIND)
        self.assertEqual(preflight["proof_rows_total"], 6)
        self.assertFalse(preflight["writes_outbox"])

    def test_default_wrapper_operations_use_mocked_production_dependencies(self) -> None:
        class FakeMarketAdapter:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def fetch_n3p_current_source(self, *, args, report, dependencies):
                self.calls.append(args.target_run_id)
                return {
                    "actual_proof_minute": "1016",
                    "source_payload_run_id": args.target_run_id,
                    "market_data_pulled": True,
                    "database_written": True,
                    "writes_n3p_metric_rows": False,
                }

        adapter = FakeMarketAdapter()
        code, payload = _run_module(
            "scripts.run_n3p_current_source_fetch_once",
            _base_argv(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1016_v1"),
            real_io_dependencies=N3RealIODependencies(market_fetch_adapter=adapter),
        )

        self.assertEqual(code, 0)
        self.assertEqual(adapter.calls, ["n3p_mixed_realtime_source_payload_20260630_until_1016_v1"])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertTrue(payload["real_io_operation_wired"])
        self.assertEqual(payload["source_payload_run_id"], "n3p_mixed_realtime_source_payload_20260630_until_1016_v1")
        self.assertTrue(payload["market_data_pulled"])
        self.assertTrue(payload["database_written"])
        self.assertFalse(payload["writes_n3p_metric_rows"])

    def test_mocked_n3p_source_fetch_returns_artifact_and_lineage_contract(self) -> None:
        calls: list[str] = []

        def fetch_n3p_current_source(*, args, report, dependencies):
            calls.append("fetch")
            self.assertEqual(dependencies.market_fetch_adapter, "fake_market")
            self.assertEqual(dependencies.artifact_writer, "fake_artifact_writer")
            self.assertEqual(dependencies.source_payload_registrar, "fake_registrar")
            self.assertTrue(report["target_absence_checked"])
            return {
                "actual_proof_minute": "1016",
                "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
                "artifact_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_payload.json",
                "payload_hash": "hash1016",
                "market_data_pulled_expected": True,
                "database_write_expected": True,
            }

        code, payload = _run_module(
            "scripts.run_n3p_current_source_fetch_once",
            _base_argv(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1016_v1"),
            real_runner_operations=N3RealRunnerOperations(fetch_n3p_current_source=fetch_n3p_current_source),
            real_io_dependencies=N3RealIODependencies(
                market_fetch_adapter="fake_market",
                artifact_writer="fake_artifact_writer",
                source_payload_registrar="fake_registrar",
            ),
        )

        self.assertEqual(code, 0)
        self.assertEqual(calls, ["fetch"])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertTrue(payload["real_io_operation_wired"])
        self.assertEqual(payload["actual_proof_minute"], "1016")
        self.assertEqual(payload["source_payload_run_id"], "n3p_mixed_realtime_source_payload_20260630_until_1016_v1")
        self.assertEqual(payload["payload_hash"], "hash1016")
        self.assertFalse(payload["side_effects"]["market_data_pulled"])
        self.assertFalse(payload["side_effects"]["database_written"])

    def test_mocked_n3p_preflight_receives_exact_source_and_target_run_ids(self) -> None:
        calls: list[tuple[str, str]] = []

        def preflight_n3p_trigger_proof(*, args, report, dependencies):
            calls.append((args.source_run_id, args.target_run_id))
            self.assertEqual(dependencies.db_connection, "fake_db")
            return {
                "baseline_frozen": True,
                "rows_total": 2322,
                "metric_ready": 2301,
                "metric_not_ready": 21,
                "rollback_sql_path": "sql/N3P_20260630_1016_trigger_proof_rollback.sql",
            }

        code, payload = _run_module(
            "scripts.run_n3p_trigger_proof_preflight_once",
            _base_argv(
                source_run_id="n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
                target_run_id=(
                    "realtime_action_confirmation_metric_20260630_until_1016__asset_all__"
                    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                    f"{SUBSCRIPTION_RUN_ID}"
                ),
            ),
            real_runner_operations=N3RealRunnerOperations(preflight_n3p_trigger_proof=preflight_n3p_trigger_proof),
            real_io_dependencies=N3RealIODependencies(db_connection="fake_db"),
        )

        self.assertEqual(code, 0)
        self.assertEqual(
            calls,
            [
                (
                    "n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
                    (
                        "realtime_action_confirmation_metric_20260630_until_1016__asset_all__"
                        "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                        f"{SUBSCRIPTION_RUN_ID}"
                    ),
                )
            ],
        )
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertTrue(payload["baseline_frozen"])
        self.assertEqual(payload["rollback_sql_path"], "sql/N3P_20260630_1016_trigger_proof_rollback.sql")

    def test_mocked_hint_source_fetch_enforces_index_board_midday_bridge_scope(self) -> None:
        calls: list[str] = []

        def fetch_n3_hint_source(*, args, report, dependencies):
            calls.append(args.hint_proof_kind)
            self.assertEqual(args.hint_proof_kind, MIDDAY_BRIDGE_PROOF_KIND)
            self.assertEqual(dependencies.market_fetch_adapter, "fake_index_client")
            return {
                "actual_proof_minute": "1300",
                "artifact_path": "docs/intraday_live_current/20260630/N3_hint_index_board_1m_1300_midday_bridge_frequency8_payload.json",
                "payload_hash": "hint_hash",
                "asset_scope": "index_board_only",
                "stock_rows": 0,
                "market_data_pulled_expected": True,
            }

        code, payload = _run_module(
            "scripts.run_n3_hint_index_board_1m_source_fetch_once",
            _base_argv(hint=True, target_run_id="n3_hint_index_board_1m_source_payload_20260630_until_1300_v1"),
            real_runner_operations=N3RealRunnerOperations(fetch_n3_hint_source=fetch_n3_hint_source),
            real_io_dependencies=N3RealIODependencies(market_fetch_adapter="fake_index_client"),
        )

        self.assertEqual(code, 0)
        self.assertEqual(calls, [MIDDAY_BRIDGE_PROOF_KIND])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(payload["asset_scope"], "index_board_only")
        self.assertEqual(payload["stock_rows"], 0)

    def test_mocked_hint_preflight_and_execute_return_distribution_and_rollback(self) -> None:
        def preflight_n3_hint_proof(*, args, report, dependencies):
            self.assertEqual(dependencies.artifact_reader, "fake_artifact_reader")
            return {
                "proof_rows_total": 24,
                "projection_distribution": {"volume_up": 7, "shrink_down": 1, "none": 16, "unknown": 0},
                "rollback_sql_path": "sql/N3_hint_index_board_1m_20260630_1300_midday_bridge_v1_rollback.sql",
                "rollback_ready": True,
            }

        code, preflight = _run_module(
            "scripts.run_n3_hint_index_board_1m_proof_preflight_once",
            _base_argv(hint=True),
            real_runner_operations=N3RealRunnerOperations(preflight_n3_hint_proof=preflight_n3_hint_proof),
            real_io_dependencies=N3RealIODependencies(artifact_reader="fake_artifact_reader"),
        )

        self.assertEqual(code, 0)
        self.assertEqual(preflight["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertTrue(preflight["rollback_ready"])
        self.assertEqual(preflight["projection_distribution"]["shrink_down"], 1)

        def execute_n3_hint_proof(*, args, report, dependencies):
            self.assertEqual(dependencies.db_writer, "fake_db_writer")
            self.assertEqual(dependencies.rollback_sql_writer, "fake_rollback_writer")
            return {
                "written_rows": {"index": 0, "board": 24, "stock": 0},
                "rollback_sql_path": "sql/N3_hint_index_board_1m_20260630_1300_midday_bridge_v1_rollback.sql",
                "database_write_expected": True,
            }

        code, execute = _run_module(
            "scripts.run_n3_hint_index_board_1m_proof_execute_once",
            _base_argv(hint=True),
            real_runner_operations=N3RealRunnerOperations(execute_n3_hint_proof=execute_n3_hint_proof),
            real_io_dependencies=N3RealIODependencies(
                db_writer="fake_db_writer",
                rollback_sql_writer="fake_rollback_writer",
            ),
        )

        self.assertEqual(code, 0)
        self.assertEqual(execute["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(execute["written_rows"], {"index": 0, "board": 24, "stock": 0})
        self.assertFalse(execute["writes_outbox"])
        self.assertFalse(execute["side_effects"]["database_written"])

    def test_target_absence_failure_blocks_before_mocked_operation(self) -> None:
        calls: list[str] = []

        def fetch_n3p_current_source(**_kwargs):
            calls.append("operation")
            return {"actual_proof_minute": "1016"}

        def target_absence_checker(*, args, report):
            calls.append("absence")
            return {"result": "BLOCKED_TARGET_DIRTY", "status": "dirty", "target_run_id": args.target_run_id}

        code, payload = _run_module(
            "scripts.run_n3p_current_source_fetch_once",
            _base_argv(),
            real_runner_operations=N3RealRunnerOperations(fetch_n3p_current_source=fetch_n3p_current_source),
            target_absence_checker=target_absence_checker,
        )

        self.assertEqual(code, 2)
        self.assertEqual(calls, ["absence"])
        self.assertEqual(payload["result"], "BLOCKED_TARGET_DIRTY")

    def test_execute_without_confirmation_blocks_before_mocked_operation(self) -> None:
        calls: list[str] = []

        def fetch_n3p_current_source(**_kwargs):
            calls.append("operation")
            return {"actual_proof_minute": "1016"}

        argv = _base_argv()
        argv.remove("--user-confirmed")
        code, payload = _run_module(
            "scripts.run_n3p_current_source_fetch_once",
            argv,
            real_runner_operations=N3RealRunnerOperations(fetch_n3p_current_source=fetch_n3p_current_source),
        )

        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertEqual(payload["result"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
