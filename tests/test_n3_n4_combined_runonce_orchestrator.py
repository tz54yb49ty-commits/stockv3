import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
import importlib


ORDINARY_PREVIOUS_RUN_ID = (
    "trigger_provisional_ordinary_20260630_until_1016__"
    "realtime_action_confirmation_metric_20260630_until_1016__asset_all__"
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
    "atomic_rule_v1_period_rollover_guard_v1"
)

HINT_PREVIOUS_RUN_ID = (
    "trigger_provisional_b2_20260630_until_1300__"
    "realtime_hint_projection_metric_20260630_until_1300__asset_index_board__"
    "index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1"
)

LEGACY_FLAWED_HINT_PREVIOUS_RUN_ID = (
    "trigger_provisional_b2_20260630_until_1300__"
    "realtime_hint_projection_metric_20260630_until_1300__asset_index_board__"
    "index_board_1m_hint_projection_v1__atomic_rule_v1"
)

N4_CONTEXT_RUN_ID = "trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1"
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"


class N3N4CombinedRunonceOrchestratorTest(unittest.TestCase):
    def test_plan_only_builds_isolated_child_sequence_without_forbidden_commands(self) -> None:
        from scripts.run_n3_n4_combined_runonce import build_combined_runonce_plan

        plan = build_combined_runonce_plan(
            for_trade_date="20260630",
            ordinary_previous_trigger_run_id=ORDINARY_PREVIOUS_RUN_ID,
            hint_previous_trigger_run_id=HINT_PREVIOUS_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            execute=False,
            user_confirmed=False,
        )

        self.assertEqual(plan["result"], "PLAN_ONLY_PASS")
        self.assertEqual(plan["terminal_step"], "combined_closeout")
        self.assertEqual(
            [step["step_id"] for step in plan["child_steps"]],
            [
                "n3p_current_source_fetch",
                "n3p_trigger_proof_preflight",
                "n3p_trigger_proof_execute",
                "n3_hint_source_fetch",
                "n3_hint_proof_preflight",
                "n3_hint_proof_execute",
                "n4_ordinary_matcher_preflight",
                "n4_ordinary_matcher_execute",
                "n4_hint_matcher_preflight",
                "n4_hint_matcher_execute",
                "combined_closeout",
            ],
        )
        combined_argv = " ".join(" ".join(step.get("argv") or []) for step in plan["child_steps"]).lower()
        for forbidden in ("n5", "n6", "outbox consume", "checkpoint", "worker", "launchctl", "bootstrap"):
            self.assertNotIn(forbidden, combined_argv)
        self.assertEqual(plan["baseline_policy"]["ordinary_previous_trigger_run_id"], ORDINARY_PREVIOUS_RUN_ID)
        self.assertEqual(plan["baseline_policy"]["hint_previous_trigger_run_id"], HINT_PREVIOUS_RUN_ID)
        self.assertTrue(plan["n5_freeze_policy"]["n5_frozen"])
        self.assertTrue(plan["target_absence_required_before_each_execute"])
        execute_steps = [step for step in plan["child_steps"] if step["step_id"].endswith("_execute")]
        self.assertTrue(execute_steps)
        self.assertTrue(all(step["target_absence_check_required"] for step in execute_steps))

    def test_execute_without_user_confirmation_blocks_before_child_commands(self) -> None:
        from scripts.run_n3_n4_combined_runonce import CombinedRunonceBlocked, build_combined_runonce_plan

        with self.assertRaises(CombinedRunonceBlocked) as ctx:
            build_combined_runonce_plan(
                for_trade_date="20260630",
                ordinary_previous_trigger_run_id=ORDINARY_PREVIOUS_RUN_ID,
                hint_previous_trigger_run_id=HINT_PREVIOUS_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                execute=True,
                user_confirmed=False,
            )
        self.assertIn("missing --user-confirmed", str(ctx.exception))

    def test_baselines_must_be_exact_current_lineage_variants(self) -> None:
        from scripts.run_n3_n4_combined_runonce import CombinedRunonceBlocked, build_combined_runonce_plan

        with self.assertRaises(CombinedRunonceBlocked):
            build_combined_runonce_plan(
                for_trade_date="20260630",
                ordinary_previous_trigger_run_id=ORDINARY_PREVIOUS_RUN_ID.replace(
                    "period_rollover_guard_v1", "atomic_rule_v1"
                ),
                hint_previous_trigger_run_id=HINT_PREVIOUS_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                execute=False,
                user_confirmed=False,
            )
        with self.assertRaises(CombinedRunonceBlocked):
            build_combined_runonce_plan(
                for_trade_date="20260630",
                ordinary_previous_trigger_run_id=ORDINARY_PREVIOUS_RUN_ID,
                hint_previous_trigger_run_id=HINT_PREVIOUS_RUN_ID.replace("asset_index_board", "asset_all"),
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                execute=False,
                user_confirmed=False,
            )

    def test_flawed_legacy_hint_baseline_fails_closed_after_midday_bridge_correction(self) -> None:
        from scripts.run_n3_n4_combined_runonce import CombinedRunonceBlocked, build_combined_runonce_plan

        with self.assertRaises(CombinedRunonceBlocked) as ctx:
            build_combined_runonce_plan(
                for_trade_date="20260630",
                ordinary_previous_trigger_run_id=ORDINARY_PREVIOUS_RUN_ID,
                hint_previous_trigger_run_id=LEGACY_FLAWED_HINT_PREVIOUS_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                execute=False,
                user_confirmed=False,
            )
        self.assertIn("midday_bridge_v1", str(ctx.exception))

    def test_hint_midday_bridge_v2_fails_closed(self) -> None:
        from scripts.run_n3_n4_combined_runonce import CombinedRunonceBlocked, build_combined_runonce_plan

        with self.assertRaises(CombinedRunonceBlocked):
            build_combined_runonce_plan(
                for_trade_date="20260630",
                ordinary_previous_trigger_run_id=ORDINARY_PREVIOUS_RUN_ID,
                hint_previous_trigger_run_id=HINT_PREVIOUS_RUN_ID.replace("midday_bridge_v1", "midday_bridge_v2"),
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                execute=False,
                user_confirmed=False,
            )

    def test_all_child_runners_are_explicit_without_improvised_db_writes(self) -> None:
        from scripts.run_n3_n4_combined_runonce import build_combined_runonce_plan

        plan = build_combined_runonce_plan(
            for_trade_date="20260630",
            ordinary_previous_trigger_run_id=ORDINARY_PREVIOUS_RUN_ID,
            hint_previous_trigger_run_id=HINT_PREVIOUS_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            execute=False,
            user_confirmed=False,
        )

        missing_runner_steps = {
            item["step_id"] for item in plan["child_runner_audit"] if item["status"] == "missing_child_runner"
        }
        self.assertEqual(missing_runner_steps, set())
        runner_paths = {item["step_id"]: item["runner_path"] for item in plan["child_runner_audit"]}
        self.assertEqual(runner_paths["n3p_current_source_fetch"], "scripts/run_n3p_current_source_fetch_once.py")
        self.assertEqual(runner_paths["n3p_trigger_proof_preflight"], "scripts/run_n3p_trigger_proof_preflight_once.py")
        self.assertEqual(runner_paths["n3_hint_source_fetch"], "scripts/run_n3_hint_index_board_1m_source_fetch_once.py")
        self.assertEqual(runner_paths["n3_hint_proof_preflight"], "scripts/run_n3_hint_index_board_1m_proof_preflight_once.py")
        self.assertEqual(runner_paths["n3_hint_proof_execute"], "scripts/run_n3_hint_index_board_1m_proof_execute_once.py")
        self.assertFalse(plan["orchestrator_contract"]["implements_business_logic"])
        self.assertFalse(plan["orchestrator_contract"]["writes_business_tables"])

    def test_child_wrappers_default_to_plan_only_and_require_execute_confirmation(self) -> None:
        wrapper_modules = [
            "scripts.run_n3p_current_source_fetch_once",
            "scripts.run_n3p_trigger_proof_preflight_once",
            "scripts.run_n3_hint_index_board_1m_source_fetch_once",
            "scripts.run_n3_hint_index_board_1m_proof_preflight_once",
            "scripts.run_n3_hint_index_board_1m_proof_execute_once",
        ]
        for module_name in wrapper_modules:
            module = importlib.import_module(module_name)

            def wrapper_argv(*, execute: bool = False, user_confirmed: bool = False) -> list[str]:
                argv = [
                    "--for-trade-date",
                    "20260630",
                    "--n4-context-run-id",
                    N4_CONTEXT_RUN_ID,
                    "--subscription-run-id",
                    SUBSCRIPTION_RUN_ID,
                    "--source-run-id",
                    "source_run_placeholder",
                    "--target-run-id",
                    "target_run_placeholder",
                    "--json",
                ]
                if "n3_hint" in module_name:
                    argv.extend(["--hint-proof-kind", "index_board_1m_hint_projection_v1_midday_bridge_v1"])
                if execute:
                    argv.append("--execute")
                if user_confirmed:
                    argv.append("--user-confirmed")
                return argv

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = module.main(wrapper_argv())
            self.assertEqual(code, 0, module_name)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["result"], "PLAN_ONLY_PASS", module_name)
            self.assertFalse(payload["side_effects"]["database_written"])
            self.assertFalse(payload["side_effects"]["market_data_pulled"])
            self.assertFalse(payload["side_effects"]["runtime_executed"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                blocked_code = module.main(wrapper_argv(execute=True))
            self.assertEqual(blocked_code, 2, module_name)
            blocked = json.loads(stdout.getvalue())
            self.assertEqual(blocked["result"], "BLOCKED", module_name)
            self.assertIn("missing --user-confirmed", blocked["reason"])

            stdout = StringIO()
            with redirect_stdout(stdout):
                execute_blocked_code = module.main(wrapper_argv(execute=True, user_confirmed=True))
            self.assertEqual(execute_blocked_code, 2, module_name)
            execute_blocked = json.loads(stdout.getvalue())
            self.assertEqual(execute_blocked["result"], "BLOCKED_MISSING_N3_PRODUCTION_ENTRYPOINT", module_name)
            self.assertFalse(execute_blocked["execute_contract_ready"])
            self.assertTrue(execute_blocked["layer_runner_called"])
            self.assertTrue(execute_blocked["real_runner_wired"])
            self.assertTrue(execute_blocked["real_io_operation_wired"])
            self.assertTrue(execute_blocked["production_adapter_wired"])
            self.assertTrue(execute_blocked["target_absence_check_required"])
            self.assertTrue(execute_blocked["target_absence_checked"])
            self.assertEqual(execute_blocked["target_absence_check_status"], "dry_run_contract_only")
            self.assertFalse(execute_blocked["writes_outbox"])
            self.assertFalse(execute_blocked["consumes_outbox"])
            self.assertFalse(execute_blocked["updates_inbox_or_checkpoint"])
            self.assertFalse(execute_blocked["starts_worker"])
            self.assertFalse(execute_blocked["touches_n5_n6"])
            self.assertFalse(execute_blocked["touches_n4_n5_n6"])

    def test_cli_outputs_json_plan_only_report(self) -> None:
        from scripts.run_n3_n4_combined_runonce import main

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = main(
                [
                    "--for-trade-date",
                    "20260630",
                    "--ordinary-previous-trigger-run-id",
                    ORDINARY_PREVIOUS_RUN_ID,
                    "--hint-previous-trigger-run-id",
                    HINT_PREVIOUS_RUN_ID,
                    "--n4-context-run-id",
                    N4_CONTEXT_RUN_ID,
                    "--subscription-run-id",
                    SUBSCRIPTION_RUN_ID,
                    "--json",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["result"], "PLAN_ONLY_PASS")
        self.assertEqual(payload["mode"], "plan_only")


if __name__ == "__main__":
    unittest.main()
