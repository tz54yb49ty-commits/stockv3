import importlib
import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

from scripts.n3_n4_combined_child_contract import run_child_contract


N4_CONTEXT_RUN_ID = "trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1"
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"
MIDDAY_BRIDGE_PROOF_KIND = "index_board_1m_hint_projection_v1_midday_bridge_v1"
LEGACY_HINT_PROOF_KIND = "index_board_1m_hint_projection_v1"


WRAPPERS = [
    ("scripts.run_n3p_current_source_fetch_once", "n3p_current_source_fetch", False),
    ("scripts.run_n3p_trigger_proof_preflight_once", "n3p_trigger_proof_preflight", False),
    ("scripts.run_n3_hint_index_board_1m_source_fetch_once", "n3_hint_source_fetch", True),
    ("scripts.run_n3_hint_index_board_1m_proof_preflight_once", "n3_hint_proof_preflight", True),
    ("scripts.run_n3_hint_index_board_1m_proof_execute_once", "n3_hint_proof_execute", True),
]


def base_argv(*, target_run_id: str = "target_run_placeholder", hint: bool = False) -> list[str]:
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
        "source_run_placeholder",
        "--target-run-id",
        target_run_id,
        "--json",
    ]
    if hint:
        argv.extend(["--hint-proof-kind", MIDDAY_BRIDGE_PROOF_KIND])
    return argv


def run_module(module_name: str, argv: list[str], **kwargs):
    module = importlib.import_module(module_name)
    stdout = StringIO()
    with redirect_stdout(stdout):
        code = module.main(argv, **kwargs)
    return code, json.loads(stdout.getvalue())


class N3CombinedChildRunnerBodyTest(unittest.TestCase):
    def test_each_wrapper_plan_only_reports_wired_layer_runner_and_safety_flags(self) -> None:
        for module_name, step_id, is_hint in WRAPPERS:
            with self.subTest(module=module_name):
                code, payload = run_module(module_name, base_argv(hint=is_hint))

                self.assertEqual(code, 0)
                self.assertEqual(payload["result"], "PLAN_ONLY_PASS")
                self.assertEqual(payload["step_id"], step_id)
                self.assertTrue(payload["execute_contract_ready"])
                self.assertTrue(payload["target_absence_check_required"])
                self.assertFalse(payload["writes_outbox"])
                self.assertFalse(payload["consumes_outbox"])
                self.assertFalse(payload["updates_inbox_or_checkpoint"])
                self.assertFalse(payload["starts_worker"])
                self.assertFalse(payload["touches_n5_n6"])
                self.assertFalse(payload["touches_n4_n5_n6"])
                self.assertFalse(payload["side_effects"]["database_written"])
                self.assertFalse(payload["side_effects"]["market_data_pulled"])
                self.assertFalse(payload["side_effects"]["runtime_executed"])
                if is_hint:
                    self.assertEqual(payload["hint_proof_kind"], MIDDAY_BRIDGE_PROOF_KIND)

    def test_execute_without_user_confirmation_blocks_before_layer_runner(self) -> None:
        for module_name, _step_id, is_hint in WRAPPERS:
            with self.subTest(module=module_name):
                calls: list[str] = []

                def runner(**_kwargs):
                    calls.append("runner")
                    return {"result": "EXECUTE_READY_REAL_IO_CONTRACT"}

                code, payload = run_module(
                    module_name,
                    [*base_argv(hint=is_hint), "--execute"],
                    layer_runner=runner,
                )

                self.assertEqual(code, 2)
                self.assertEqual(payload["result"], "BLOCKED")
                self.assertIn("missing --user-confirmed", payload["reason"])
                self.assertEqual(calls, [])

    def test_confirmed_execute_calls_target_absence_before_mocked_layer_runner(self) -> None:
        for module_name, step_id, is_hint in WRAPPERS:
            with self.subTest(module=module_name):
                calls: list[str] = []

                def target_absence_checker(*, args, report):
                    calls.append("absence")
                    self.assertEqual(report["step_id"], step_id)
                    self.assertTrue(report["target_absence_check_required"])
                    return {"status": "passed", "target_run_id": args.target_run_id}

                def runner(*, args, report):
                    calls.append("runner")
                    self.assertEqual(report["target_absence_check_status"], "passed")
                    self.assertTrue(report["target_absence_checked"])
                    return {
                        "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                        "layer_runner_called": True,
                        "real_runner_wired": True,
                        "execute_contract_ready": True,
                        "target_absence_checked": True,
                        "received_target_run_id": args.target_run_id,
                    }

                code, payload = run_module(
                    module_name,
                    [*base_argv(hint=is_hint), "--execute", "--user-confirmed"],
                    layer_runner=runner,
                    target_absence_checker=target_absence_checker,
                )

                self.assertEqual(code, 0)
                self.assertEqual(calls, ["absence", "runner"])
                self.assertEqual(payload["result"], "EXECUTE_READY_REAL_IO_CONTRACT")
                self.assertTrue(payload["execute_contract_ready"])
                self.assertTrue(payload["layer_runner_called"])
                self.assertTrue(payload["real_runner_wired"])
                self.assertTrue(payload["target_absence_checked"])
                self.assertEqual(payload["target_absence_check_status"], "passed")
                self.assertFalse(payload["touches_n4_n5_n6"])
                self.assertFalse(payload["side_effects"]["database_written"])
                self.assertFalse(payload["side_effects"]["market_data_pulled"])

    def test_target_absence_failure_blocks_before_real_runner(self) -> None:
        for module_name, step_id, is_hint in WRAPPERS:
            with self.subTest(module=module_name):
                calls: list[str] = []

                def target_absence_checker(*, args, report):
                    calls.append("absence")
                    self.assertEqual(report["step_id"], step_id)
                    return {
                        "result": "BLOCKED_TARGET_DIRTY",
                        "reason": "target already exists",
                        "status": "dirty",
                        "target_run_id": args.target_run_id,
                    }

                def runner(**_kwargs):
                    calls.append("runner")
                    return {"result": "EXECUTE_READY_REAL_IO_CONTRACT"}

                code, payload = run_module(
                    module_name,
                    [*base_argv(hint=is_hint), "--execute", "--user-confirmed"],
                    layer_runner=runner,
                    target_absence_checker=target_absence_checker,
                )

                self.assertEqual(code, 2)
                self.assertEqual(calls, ["absence"])
                self.assertEqual(payload["result"], "BLOCKED_TARGET_DIRTY")
                self.assertTrue(payload["target_absence_checked"])
                self.assertEqual(payload["target_absence_check_status"], "dirty")

    def test_missing_audited_layer_runner_fails_closed_with_step_id(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = run_child_contract(
                argv=[*base_argv(), "--execute", "--user-confirmed", "--json"],
                step_id="missing_step",
                layer_role="N3_market_data",
                description="missing runner probe",
                layer_runner=None,
            )

        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["result"], "BLOCKED_MISSING_N3_REAL_RUNNER")
        self.assertEqual(payload["reason"], "BLOCKED_MISSING_N3_REAL_RUNNER:missing_step")

    def test_hint_wrappers_reject_non_midday_bridge_proof_kind(self) -> None:
        for module_name, _step_id, is_hint in WRAPPERS:
            if not is_hint:
                continue
            with self.subTest(module=module_name):
                argv = base_argv(hint=False)
                argv.extend(["--hint-proof-kind", LEGACY_HINT_PROOF_KIND])
                code, payload = run_module(module_name, argv)

                self.assertEqual(code, 2)
                self.assertEqual(payload["result"], "BLOCKED_HINT_PROOF_KIND")
                self.assertIn(MIDDAY_BRIDGE_PROOF_KIND, payload["reason"])


if __name__ == "__main__":
    unittest.main()
