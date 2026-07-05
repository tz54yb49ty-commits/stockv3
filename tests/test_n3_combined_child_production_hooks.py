import unittest
from types import SimpleNamespace


MIDDAY_BRIDGE_PROOF_KIND = "index_board_1m_hint_projection_v1_midday_bridge_v1"


def _args(**overrides):
    values = {
        "for_trade_date": "20260630",
        "source_run_id": "source_run",
        "target_run_id": "target_run",
        "hint_proof_kind": MIDDAY_BRIDGE_PROOF_KIND,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _report(step_id: str = "step"):
    return {
        "step_id": step_id,
        "target_absence_checked": True,
        "target_absence_check_status": "passed",
    }


class _N3PSourceFetchBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def load_n3p_current_source_scope(self, *, args, report, dependencies):
        self.calls.append("scope")
        return {
            "trade_date": args.for_trade_date,
            "for_trade_date": args.for_trade_date,
            "n4_context_status": "passed",
            "subscription_status": "passed",
            "a1_cumulative_status": "passed",
            "stock_object_count": 1,
            "index_object_count": 1,
            "board_object_count": 0,
        }

    def fetch_n3p_current_market_rows(self, *, args, report, dependencies, scope):
        self.calls.append("fetch")
        return {
            "proof_input_time": "2026-06-30T10:16:00+08:00",
            "stock_quote_rows": [
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SZ:300001",
                    "price": 10.5,
                    "amount": 1000,
                    "source_time": "2026-06-30T10:16:00+08:00",
                    "source_marker": "mootdx_quotes",
                }
            ],
            "index_board_1m_rows": [
                {
                    "asset_kind": "index",
                    "identity_key": "index:SH:000001",
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
        from scripts.n3p_current_source_fetch_provider import compute_n3p_current_source_payload_hash

        self.calls.append("artifact")
        return {
            "payload_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_payload.json",
            "report_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_report.json",
            "payload_hash": compute_n3p_current_source_payload_hash(payload),
            "file_sha256": "file_hash_1016",
        }

    def register_n3p_source_payload_run(self, *, args, report, dependencies, source_payload):
        self.calls.append("register")
        self.registered_source_payload_run_id = source_payload["source_payload_run_id"]
        return {
            "source_payload_registered": True,
            "database_written": True,
            "writes_n3p_metric_rows": False,
        }


class N3CombinedChildProductionHooksTest(unittest.TestCase):
    def test_n3p_source_hook_fetches_and_registers_without_metric_rows_or_outbox(self) -> None:
        from scripts import n3_combined_child_production_hooks as hooks
        from scripts.n3_combined_child_real_runners import N3RealIODependencies

        calls: list[str] = []
        test_case = self

        class Fetcher:
            def fetch_n3p_current_source_payload(self, *, args, report, dependencies):
                calls.append(f"fetch:{args.target_run_id}:{report['step_id']}")
                test_case.assertIs(dependencies.market_fetch_adapter, self)
                return {
                    "source_payload_run_id": args.target_run_id,
                    "actual_proof_minute": "1016",
                    "source_artifact_path": "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_payload.json",
                    "payload_hash": "hash1016",
                    "stock_quote_rows": 1761,
                    "index_board_1m_rows": 6256,
                    "market_data_pulled": True,
                }

        class Registrar:
            def register_n3p_source_payload_run(self, *, args, report, dependencies, source_payload):
                calls.append(f"register:{source_payload['source_payload_run_id']}")
                return {
                    "source_payload_registered": True,
                    "database_written": True,
                    "writes_n3p_metric_rows": False,
                }

        dependencies = N3RealIODependencies(
            market_fetch_adapter=Fetcher(),
            source_payload_registrar=Registrar(),
        )
        payload = hooks.n3p_current_source_fetch_and_register(
            args=_args(target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1016_v1"),
            report=_report("n3p_current_source_fetch"),
            dependencies=dependencies,
        )

        self.assertEqual(calls, ["fetch:n3p_mixed_realtime_source_payload_20260630_until_1016_v1:n3p_current_source_fetch", "register:n3p_mixed_realtime_source_payload_20260630_until_1016_v1"])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(payload["source_payload_run_id"], "n3p_mixed_realtime_source_payload_20260630_until_1016_v1")
        self.assertEqual(payload["payload_hash"], "hash1016")
        self.assertTrue(payload["market_data_pulled"])
        self.assertTrue(payload["database_written"])
        self.assertFalse(payload["writes_n3p_metric_rows"])
        self.assertFalse(payload["writes_outbox"])
        self.assertFalse(payload["consumes_outbox"])
        self.assertFalse(payload["updates_inbox_or_checkpoint"])
        self.assertFalse(payload["starts_worker"])
        self.assertFalse(payload["touches_n4_n5_n6"])

    def test_concrete_n3p_source_provider_normalizes_artifact_lineage_and_registration(self) -> None:
        from scripts.n3_combined_child_production_hooks import n3p_current_source_fetch_and_register
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchProvider, compute_n3p_current_source_payload_hash

        backend = _N3PSourceFetchBackend()
        provider = N3PCurrentSourceFetchProvider(backend=backend)
        args = _args(
            for_trade_date="20260630",
            target_run_id="n3p_mixed_realtime_source_payload_20260630_until_1016_v1",
            requested_until_hhmm="1016",
        )
        payload = n3p_current_source_fetch_and_register(
            args=args,
            report=_report("n3p_current_source_fetch"),
            dependencies=N3RealIODependencies(
                market_fetch_adapter=provider,
                source_payload_registrar=provider,
            ),
        )

        self.assertEqual(backend.calls, ["scope", "fetch", "artifact", "register"])
        self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(payload["actual_proof_minute"], "1016")
        self.assertEqual(payload["actual_until_hhmm"], "1016")
        self.assertEqual(payload["source_payload_run_id"], "n3p_mixed_realtime_source_payload_20260630_until_1016_v1")
        self.assertEqual(payload["payload_path"], "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_payload.json")
        self.assertEqual(payload["report_path"], "docs/intraday_live_current/20260630/N3P_mixed_realtime_1016_source_fetch_report.json")
        self.assertEqual(payload["payload_hash"], compute_n3p_current_source_payload_hash(payload))
        self.assertEqual(payload["source_payload_counts"], {"stock_quote_rows": 1, "index_board_1m_rows": 1})
        self.assertTrue(payload["market_data_pulled"])
        self.assertTrue(payload["database_written"])
        self.assertFalse(payload["writes_n3p_metric_rows"])
        self.assertFalse(payload["writes_outbox"])
        self.assertFalse(payload["consumes_outbox"])
        self.assertFalse(payload["updates_inbox_or_checkpoint"])
        self.assertFalse(payload["starts_worker"])
        self.assertFalse(payload["touches_n4_n5_n6"])
        self.assertFalse(payload["side_effects"]["market_data_pulled"])
        self.assertFalse(payload["side_effects"]["database_written"])

    def test_concrete_n3p_source_provider_refuses_requested_hhmm_relabel(self) -> None:
        from scripts.n3_combined_child_production_hooks import n3p_current_source_fetch_and_register
        from scripts.n3_combined_child_real_runners import N3RealIODependencies
        from scripts.n3p_current_source_fetch_provider import N3PCurrentSourceFetchProvider

        backend = _N3PSourceFetchBackend()
        provider = N3PCurrentSourceFetchProvider(backend=backend)
        payload = n3p_current_source_fetch_and_register(
            args=_args(
                for_trade_date="20260630",
                target_run_id="n3p_mixed_realtime_source_payload_20260630_until_0935_v1",
                requested_until_hhmm="0935",
            ),
            report=_report("n3p_current_source_fetch"),
            dependencies=N3RealIODependencies(
                market_fetch_adapter=provider,
                source_payload_registrar=provider,
            ),
        )

        self.assertEqual(backend.calls, ["scope", "fetch"])
        self.assertEqual(payload["result"], "BLOCKED_N3P_SOURCE_TIME_RELABEL_RISK")
        self.assertIn("actual_until_hhmm=1016", payload["reason"])
        self.assertFalse(payload["database_written"])
        self.assertFalse(payload["market_data_pulled"])

    def test_n3p_source_payload_validation_rejects_bad_current_rows(self) -> None:
        from scripts.n3p_current_source_fetch_provider import validate_n3p_current_source_payload

        base_row = {
            "asset_kind": "index",
            "identity_key": "index:SH:000001",
            "bar_time": "2026-06-30T10:16:00+08:00",
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "amount": 100,
            "source_marker": "mootdx_index_frequency_8",
        }
        cases = [
            ("canonical_1130_forbidden", [{**base_row, "bar_time": "2026-06-30T11:30:00+08:00"}]),
            ("fake_source_marker", [{**base_row, "source_marker": "synthetic_mootdx_index_frequency_8"}]),
            ("duplicate_object_minute", [base_row, dict(base_row)]),
            ("row_after_proof_input_time", [{**base_row, "bar_time": "2026-06-30T10:17:00+08:00"}]),
        ]
        for expected_reason, rows in cases:
            with self.subTest(expected_reason=expected_reason):
                result = validate_n3p_current_source_payload(
                    {
                        "stock_quote_rows": [],
                        "index_board_1m_rows": rows,
                        "proof_input_time": "2026-06-30T10:16:00+08:00",
                    },
                    for_trade_date="20260630",
                    proof_input_time="2026-06-30T10:16:00+08:00",
                )

                self.assertFalse(result["valid"])
                self.assertIn(expected_reason, result["blocked_reasons"])

    def test_n3p_preflight_and_execute_hooks_call_lower_level_writer(self) -> None:
        from scripts import n3_combined_child_production_hooks as hooks
        from scripts.n3_combined_child_real_runners import N3RealIODependencies

        calls: list[str] = []

        class Planner:
            def build_n3p_trigger_proof_preflight(self, *, args, report, dependencies):
                calls.append(f"preflight:{args.source_run_id}:{args.target_run_id}")
                return {"rows_total": 2322, "metric_ready": 2301, "metric_not_ready": 21}

        class Writer:
            def execute_n3p_trigger_proof(self, *, args, report, dependencies):
                calls.append(f"execute:{args.source_run_id}:{args.target_run_id}")
                return {
                    "rows_written": {"stock": 2026, "index": 18, "board": 278},
                    "database_written": True,
                    "writes_outbox": False,
                }

        args = _args(source_run_id="n3p_mixed_realtime_source_payload_20260630_until_1016_v1", target_run_id="n3p_target_1016")
        preflight = hooks.n3p_trigger_proof_preflight_plan(
            args=args,
            report=_report("n3p_trigger_proof_preflight"),
            dependencies=N3RealIODependencies(artifact_reader=Planner()),
        )
        execute = hooks.n3p_trigger_proof_execute_write(
            args=args,
            report=_report("n3p_trigger_proof_execute"),
            dependencies=N3RealIODependencies(db_writer=Writer()),
        )

        self.assertEqual(calls, ["preflight:n3p_mixed_realtime_source_payload_20260630_until_1016_v1:n3p_target_1016", "execute:n3p_mixed_realtime_source_payload_20260630_until_1016_v1:n3p_target_1016"])
        self.assertEqual(preflight["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(execute["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(preflight["rows_total"], 2322)
        self.assertEqual(execute["rows_written"], {"stock": 2026, "index": 18, "board": 278})
        self.assertFalse(preflight["writes_outbox"])
        self.assertFalse(execute["writes_outbox"])
        self.assertFalse(execute["touches_n4_n5_n6"])

    def test_hint_hooks_enforce_midday_bridge_kind_and_index_board_scope(self) -> None:
        from scripts import n3_combined_child_production_hooks as hooks
        from scripts.n3_combined_child_real_runners import N3RealIODependencies

        calls: list[str] = []

        class Fetcher:
            def fetch_n3_hint_frequency8_source(self, *, args, report, dependencies):
                calls.append(f"hint_fetch:{args.hint_proof_kind}")
                return {
                    "actual_proof_minute": "1300",
                    "source_artifact_path": "docs/intraday_live_current/20260630/N3_hint_index_board_1m_1300_midday_bridge_frequency8_payload.json",
                    "payload_hash": "hint_hash",
                    "asset_scope": "index_board_only",
                    "stock_rows": 0,
                    "market_data_pulled": True,
                }

        class Planner:
            def build_n3_hint_proof_preflight(self, *, args, report, dependencies):
                calls.append(f"hint_preflight:{args.target_run_id}")
                return {
                    "proof_rows_total": 24,
                    "projection_distribution": {"volume_up": 7, "shrink_down": 1, "none": 16, "unknown": 0},
                    "stock_rows": 0,
                }

        class Writer:
            def execute_n3_hint_projection_write_plan(self, *, args, report, dependencies):
                calls.append(f"hint_execute:{args.target_run_id}")
                return {
                    "written_rows": {"index": 0, "board": 24, "stock": 0},
                    "database_written": True,
                    "stock_rows": 0,
                }

        args = _args(target_run_id="realtime_hint_projection_metric_20260630_until_1300__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__sub")
        source = hooks.n3_hint_frequency8_source_fetch(
            args=args,
            report=_report("n3_hint_source_fetch"),
            dependencies=N3RealIODependencies(market_fetch_adapter=Fetcher()),
        )
        preflight = hooks.n3_hint_proof_preflight_plan(
            args=args,
            report=_report("n3_hint_proof_preflight"),
            dependencies=N3RealIODependencies(artifact_reader=Planner()),
        )
        execute = hooks.n3_hint_proof_execute_write(
            args=args,
            report=_report("n3_hint_proof_execute"),
            dependencies=N3RealIODependencies(db_writer=Writer()),
        )

        self.assertEqual(calls, [f"hint_fetch:{MIDDAY_BRIDGE_PROOF_KIND}", f"hint_preflight:{args.target_run_id}", f"hint_execute:{args.target_run_id}"])
        self.assertEqual(source["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
        self.assertEqual(preflight["projection_distribution"]["shrink_down"], 1)
        self.assertEqual(execute["written_rows"], {"index": 0, "board": 24, "stock": 0})
        self.assertEqual(source["asset_scope"], "index_board_only")
        self.assertFalse(source["writes_outbox"])
        self.assertFalse(preflight["writes_outbox"])
        self.assertFalse(execute["writes_outbox"])

    def test_missing_lower_level_hook_and_legacy_hint_kind_fail_closed(self) -> None:
        from scripts import n3_combined_child_production_hooks as hooks
        from scripts.n3_combined_child_real_runners import N3RealIODependencies

        missing = hooks.n3p_current_source_fetch_and_register(
            args=_args(),
            report=_report("n3p_current_source_fetch"),
            dependencies=N3RealIODependencies(),
        )
        self.assertEqual(missing["result"], "BLOCKED_MISSING_N3_PRODUCTION_ENTRYPOINT")
        self.assertTrue(str(missing["reason"]).startswith("BLOCKED_MISSING_N3_PRODUCTION_ENTRYPOINT:n3p_current_source_fetch"))
        self.assertFalse(missing["writes_outbox"])

        legacy = hooks.n3_hint_proof_execute_write(
            args=_args(hint_proof_kind="index_board_1m_hint_projection_v1"),
            report=_report("n3_hint_proof_execute"),
            dependencies=N3RealIODependencies(db_writer=object()),
        )
        self.assertEqual(legacy["result"], "BLOCKED_HINT_PROOF_KIND")
        self.assertIn(MIDDAY_BRIDGE_PROOF_KIND, legacy["reason"])
        self.assertFalse(legacy["writes_outbox"])


if __name__ == "__main__":
    unittest.main()
