import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import run_n3_n4_n5_realtime_chain_once as chain


ASIA_SHANGHAI = timezone(timedelta(hours=8))


def resolved_20260612_lineage() -> dict:
    return {
        "status": "resolved",
        "reason": "auto_lineage_resolved",
        "for_trade_date": "20260612",
        "subscription_run_id": "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
        "preload_run_id": "previous_day_minute_preload_20260611_for_20260612__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
        "source_condition_run_id": "condition_layer_20260611_source_20260611_for_20260612_v1",
    }


def passed_n3_report() -> dict:
    return {
        "status": "passed",
        "reason": "bounded_pass_complete",
        "for_trade_date": "20260612",
        "latest_closed_minute": "2026-06-12T09:31:00+08:00",
        "latest_closed_minute_hhmm": "0931",
        "effective_hhmm": "0931",
        "stage_run_ids": {
            "B1": "realtime_daily_snapshot_20260612_until_0931__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
            "C1": "today_minute_bar_1m_20260612_until_0931__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
            "B2": "realtime_projection_metric_20260612_until_0931__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
        },
        "executed_child_command_count": 3,
    }


class Completed:
    def __init__(self, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class RealtimeChainWrapperTests(unittest.TestCase):
    def test_stage_ids_are_deterministic_for_20260612_hhmm(self):
        ids = chain.build_stage_ids(
            for_trade_date="20260612",
            hhmm="0931",
            subscription_run_id=resolved_20260612_lineage()["subscription_run_id"],
            source_condition_run_id=resolved_20260612_lineage()["source_condition_run_id"],
        )

        self.assertEqual(
            ids.b1_standard_outbox_run_id,
            "realtime_daily_snapshot_20260612_standard_outbox_until_0931__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
        )
        self.assertIn("trace_aligned_standard_outbox_until_0931", ids.b2_trace_projection_run_id)
        self.assertEqual(
            ids.n4_context_run_id,
            "trigger_context_snapshot_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
        )
        self.assertIn("n4_production_semantic_replay_20260612_market_snapshot_updated_until_0931", ids.n4_run_id)
        self.assertEqual(
            ids.n3_action_metric_run_id,
            "action_confirmation_projection_metric_20260612_until_0931_from_n4_production_semantic_replay_20260612_market_snapshot_updated_until_0931_v1",
        )
        self.assertEqual(
            ids.n3_action_subscription_run_id,
            "market_data_subscription_20260612_action_confirmation_until_0931_scope__n4_production_semantic_replay_20260612_market_snapshot_updated_until_0931_v1",
        )
        self.assertEqual(
            ids.n3_action_today_minute_run_id,
            "today_minute_bar_1m_20260612_until_0931_action_confirmation_scope__n4_production_semantic_replay_20260612_market_snapshot_updated_until_0931_v1",
        )
        self.assertEqual(
            ids.n3_action_preload_run_id,
            "previous_day_minute_preload_20260612_until_0931_action_confirmation_scope__n4_production_semantic_replay_20260612_market_snapshot_updated_until_0931_v1",
        )
        self.assertEqual(
            ids.n5_action_run_id,
            "n5_action_bounded_20260612_after_n3_action_confirmation_metric_until_0931_v1",
        )

    def test_action_metric_excludes_all_bj_asset_identities(self):
        self.assertTrue(chain.is_action_metric_excluded_identity("stock:BJ:920001"))
        self.assertTrue(chain.is_action_metric_excluded_identity("index:BJ:899050"))
        self.assertFalse(chain.is_action_metric_excluded_identity("stock:SH:600000"))

    def test_plan_only_resolves_lineage_without_invoking_children(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmpdir:
            report = chain.run_realtime_chain_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmpdir) / "docs",
                sql_root=Path(tmpdir) / "sql",
                as_of=datetime(2026, 6, 12, 9, 32, tzinfo=ASIA_SHANGHAI),
                lineage_resolver=lambda **_: resolved_20260612_lineage(),
                command_runner=lambda argv: calls.append(argv),
            )

        self.assertEqual(report["result"], "PLAN_ONLY")
        self.assertFalse(report["execute"])
        self.assertEqual(calls, [])
        self.assertEqual(report["lineage"]["for_trade_date"], "20260612")
        self.assertTrue(report["child_command_plan"])
        self.assertFalse(report["forbidden_scope_proof"]["n6_entered"])
        self.assertFalse(report["forbidden_scope_proof"]["real_trade_touched"])

    def test_execute_requires_user_confirmation_before_lineage_or_children(self):
        calls = []
        lineage_calls = []

        def lineage_resolver(**kwargs):
            lineage_calls.append(kwargs)
            return resolved_20260612_lineage()

        with tempfile.TemporaryDirectory() as tmpdir:
            report = chain.run_realtime_chain_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmpdir) / "docs",
                sql_root=Path(tmpdir) / "sql",
                execute=True,
                user_confirmed=False,
                lineage_resolver=lineage_resolver,
                command_runner=lambda argv: calls.append(argv),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "missing --user-confirmed")
        self.assertEqual(calls, [])
        self.assertEqual(lineage_calls, [])

    def test_execute_blocks_before_future_trade_date_check(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmpdir:
            report = chain.run_realtime_chain_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmpdir) / "docs",
                sql_root=Path(tmpdir) / "sql",
                as_of=datetime(2026, 6, 11, 20, 30, tzinfo=ASIA_SHANGHAI),
                execute=True,
                user_confirmed=True,
                lineage_resolver=lambda **_: resolved_20260612_lineage(),
                command_runner=lambda argv: calls.append(argv),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "cross_layer_realtime_chain_execute_removed_use_layer_gates")
        self.assertEqual(calls, [])

    def test_execute_is_removed_and_does_not_run_n3_to_n5_children(self):
        calls = []

        def command_runner(argv):
            calls.append(argv)
            return Completed()

        def stage_status(stage_name, _ids):
            if stage_name == "N4_CONTEXT":
                return {"status": "passed"}
            return {"status": "missing", "reason": f"{stage_name}_missing"}

        with tempfile.TemporaryDirectory() as tmpdir:
            report = chain.run_realtime_chain_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmpdir) / "docs",
                sql_root=Path(tmpdir) / "sql",
                as_of=datetime(2026, 6, 12, 9, 32, tzinfo=ASIA_SHANGHAI),
                execute=True,
                user_confirmed=True,
                allow_overwrite=True,
                python_executable=sys.executable,
                lineage_resolver=lambda **_: resolved_20260612_lineage(),
                n3_report_loader=lambda _path: passed_n3_report(),
                stage_status_provider=stage_status,
                artifact_builder=lambda stage_name, _context: {"stage": stage_name, "status": "written"},
                command_runner=command_runner,
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "cross_layer_realtime_chain_execute_removed_use_layer_gates")
        self.assertEqual(calls, [])
        self.assertEqual(report["executed_steps"], [])
        self.assertIn("N3_market_data B1/C1/B2 execute gate", report["next_required_gates"])
        self.assertFalse(report["forbidden_scope_proof"]["n6_entered"])
        self.assertFalse(report["forbidden_scope_proof"]["voice_mobile_touched"])

    def test_context_missing_blocks_before_n4_and_n5(self):
        calls = []

        def command_runner(argv):
            calls.append(argv)
            return Completed()

        def stage_status(stage_name, _ids):
            if stage_name == "N4_CONTEXT":
                return {"status": "missing", "reason": "n4_context_not_ready"}
            return {"status": "passed"}

        with tempfile.TemporaryDirectory() as tmpdir:
            report = chain.run_realtime_chain_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmpdir) / "docs",
                sql_root=Path(tmpdir) / "sql",
                as_of=datetime(2026, 6, 12, 9, 32, tzinfo=ASIA_SHANGHAI),
                execute=True,
                user_confirmed=True,
                python_executable=sys.executable,
                lineage_resolver=lambda **_: resolved_20260612_lineage(),
                n3_report_loader=lambda _path: passed_n3_report(),
                stage_status_provider=stage_status,
                artifact_builder=lambda stage_name, _context: {"stage": stage_name, "status": "written"},
                command_runner=command_runner,
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "cross_layer_realtime_chain_execute_removed_use_layer_gates")
        self.assertEqual(calls, [])

    def test_auction_snapshot_without_closed_minute_noops_before_standard_outbox(self):
        calls = []
        auction_report = passed_n3_report()
        auction_report["latest_closed_minute"] = None
        auction_report["latest_closed_minute_hhmm"] = None
        auction_report["effective_hhmm"] = "0920"
        auction_report["projection_input_mode"] = "auction_or_snapshot_only"

        def command_runner(argv):
            calls.append(argv)
            return Completed()

        with tempfile.TemporaryDirectory() as tmpdir:
            report = chain.run_realtime_chain_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmpdir) / "docs",
                sql_root=Path(tmpdir) / "sql",
                as_of=datetime(2026, 6, 12, 9, 20, tzinfo=ASIA_SHANGHAI),
                execute=True,
                user_confirmed=True,
                python_executable=sys.executable,
                lineage_resolver=lambda **_: resolved_20260612_lineage(),
                n3_report_loader=lambda _path: auction_report,
                command_runner=command_runner,
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "cross_layer_realtime_chain_execute_removed_use_layer_gates")
        self.assertEqual(report["executed_steps"], [])
        self.assertEqual(calls, [])

    def test_b1_standard_outbox_artifacts_include_dynamic_pull_plans_and_board_policy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts = chain.build_b1_standard_outbox_artifacts(
                docs_root=root / "docs",
                sql_root=root / "sql",
                for_trade_date="20260612",
                source_trade_date="20260611",
                prev_trade_date="20260611",
                source_condition_run_id=resolved_20260612_lineage()["source_condition_run_id"],
                subscription_run_id=resolved_20260612_lineage()["subscription_run_id"],
                snapshot_run_id="realtime_daily_snapshot_20260612_standard_outbox_until_0931__sub",
                hhmm="0931",
                pull_plan_rows=[
                    {"asset_kind": "stock", "source_pull_plan_id": 178, "adapter_name": "StockRealtimeQuoteAdapter", "subscription_count": 1872, "object_count": 1872},
                    {"asset_kind": "index", "source_pull_plan_id": 175, "adapter_name": "IndexRealtimeQuoteAdapter", "subscription_count": 83, "object_count": 83},
                    {"asset_kind": "board", "source_pull_plan_id": 172, "adapter_name": "BoardMarketDataAdapter", "subscription_count": 127, "object_count": 127},
                ],
            )

            contract = json.loads(Path(artifacts["contract_path"]).read_text(encoding="utf-8"))
            self.assertEqual(contract["writes_outbox"], True)
            self.assertEqual(contract["expected_row_count"], 2082)
            plan = {row["asset_kind"]: row for row in contract["source_adapter_plan"]}
            self.assertEqual(plan["stock"]["source_pull_plan_id"], 178)
            self.assertEqual(plan["index"]["source_pull_plan_id"], 175)
            self.assertEqual(plan["board"]["source_pull_plan_id"], 172)
            self.assertEqual(
                contract["source_time_policy"]["board_source_time_label_handling"],
                "NORMALIZE_TO_OBSERVED_AT",
            )
            self.assertEqual(
                contract["board_source_time_semantics_policy"]["event_time_policy"],
                "observed_at_for_board_untrusted_period_label",
            )

    def test_b2_trace_aligned_artifacts_are_runner_compatible(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts = chain.build_b2_trace_aligned_artifacts(
                docs_root=root / "docs",
                sql_root=root / "sql",
                for_trade_date="20260612",
                source_trade_date="20260611",
                prev_trade_date="20260611",
                source_condition_run_id=resolved_20260612_lineage()["source_condition_run_id"],
                subscription_run_id=resolved_20260612_lineage()["subscription_run_id"],
                preload_run_id=resolved_20260612_lineage()["preload_run_id"],
                today_minute_run_id="today_minute_bar_1m_20260612_until_0931__sub",
                snapshot_run_id="realtime_daily_snapshot_20260612_standard_outbox_until_0931__sub",
                projection_run_id="realtime_projection_metric_20260612_trace_aligned_standard_outbox_until_0931__snap",
                latest_closed_minute="2026-06-12T09:31:00+08:00",
                expected_rows_by_asset={"stock": 1872, "index": 83, "board": 127},
                expected_distribution={
                    "ready_rows": 0,
                    "ready_by_asset": {},
                    "not_ready_rows": 2082,
                    "not_ready_by_asset": {"stock": 1872, "index": 83, "board": 127},
                    "trace_status": {"trace_ready": 2082},
                },
            )

            dry_run = json.loads(Path(artifacts["dry_run_path"]).read_text(encoding="utf-8"))
            contract = json.loads(Path(artifacts["contract_path"]).read_text(encoding="utf-8"))
            preflight = json.loads(Path(artifacts["preflight_path"]).read_text(encoding="utf-8"))
            self.assertEqual(dry_run["result"], "DRY_RUN_PASS")
            self.assertEqual(dry_run["projection_run_id_candidate"], contract["projection_run_id"])
            self.assertEqual(contract["stage"], "N3-B2-realtime-projection-execute-contract")
            self.assertEqual(preflight["stage"], "N3-B2-realtime-projection-execute-preflight")
            self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
            expected_dates = {
                "for_trade_date": "20260612",
                "source_trade_date": "20260611",
                "prev_trade_date": "20260611",
            }
            self.assertEqual(dry_run["dates"], expected_dates)
            self.assertEqual(contract["dates"], expected_dates)
            self.assertEqual(preflight["dates"], expected_dates)
            self.assertEqual(contract["projection_time_policy"]["mode"], "standard_outbox_observed_at_to_latest_closed_minute")
            self.assertEqual(
                contract["calculation_config"]["calculation_method"],
                "active_30m_bucket_projection_v1_strict_current_lineage",
            )
            self.assertEqual(
                contract["calculation_config"]["calculation_config_hash"],
                "c0e47d3beec744930c098fae1a083fc1da95f9752bb2efc01dc76b3ed4d92b1d",
            )
            self.assertEqual(contract["calculation_config"]["window_total_seconds"], 1800)
            self.assertEqual(contract["calculation_config"]["completion_ratio_min_ready"], "0.2")
            self.assertEqual(contract["calculation_config"]["amount_projection_expand_threshold"], "1.2")
            self.assertEqual(contract["calculation_config"]["amount_projection_shrink_threshold"], "0.8")
            self.assertEqual(contract["calculation_config"]["price_flat_abs_pct_threshold"], "0.001")
            self.assertFalse(contract["writes_outbox"])

    def test_b2_expected_distribution_materializer_uses_runner_compatible_calculation_config(self):
        captured_contracts = []

        def fake_build_projection_rows(*, dsn, contract):
            captured_contracts.append(contract)
            return []

        with patch.object(chain, "build_projection_rows", side_effect=fake_build_projection_rows):
            distribution = chain.materialize_b2_expected_distribution(
                dsn="postgresql://example",
                for_trade_date="20260612",
                source_trade_date="20260611",
                prev_trade_date="20260611",
                source_condition_run_id=resolved_20260612_lineage()["source_condition_run_id"],
                subscription_run_id=resolved_20260612_lineage()["subscription_run_id"],
                preload_run_id=resolved_20260612_lineage()["preload_run_id"],
                today_minute_run_id="today_minute_bar_1m_20260612_until_0931__sub",
                snapshot_run_id="realtime_daily_snapshot_20260612_standard_outbox_until_0931__sub",
                projection_run_id="realtime_projection_metric_20260612_trace_aligned_standard_outbox_until_0931__snap",
                latest_closed_minute="2026-06-12T09:31:00+08:00",
                expected_rows_by_asset={"stock": 0, "index": 0, "board": 0},
            )

        self.assertEqual(distribution["distribution_status"], "materialized_from_projection_rows")
        self.assertEqual(len(captured_contracts), 1)
        self.assertEqual(
            captured_contracts[0]["dates"],
            {
                "for_trade_date": "20260612",
                "source_trade_date": "20260611",
                "prev_trade_date": "20260611",
            },
        )
        calculation_config = captured_contracts[0]["calculation_config"]
        self.assertEqual(
            calculation_config["calculation_method"],
            "active_30m_bucket_projection_v1_strict_current_lineage",
        )
        self.assertEqual(
            calculation_config["calculation_config_hash"],
            "c0e47d3beec744930c098fae1a083fc1da95f9752bb2efc01dc76b3ed4d92b1d",
        )
        self.assertEqual(calculation_config["window_total_seconds"], 1800)
        self.assertEqual(calculation_config["completion_ratio_min_ready"], "0.2")


if __name__ == "__main__":
    unittest.main()
