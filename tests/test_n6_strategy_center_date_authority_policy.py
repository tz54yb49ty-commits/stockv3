from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "docs" / "EXECUTION_KERNEL.md"


def load(policy_id: str) -> dict:
    text = KERNEL.read_text(encoding="utf-8")
    begin = f"<!-- policy:{policy_id}:begin -->"
    end = f"<!-- policy:{policy_id}:end -->"
    block = text[text.index(begin) + len(begin) : text.index(end)]
    match = re.search(r"```json\s*(\{.*?\})\s*```", block, re.DOTALL)
    if not match:
        raise AssertionError(f"missing JSON policy block: {policy_id}")
    return json.loads(match.group(1))


class N6DateAuthorityPolicyTest(unittest.TestCase):
    def test_084_is_single_fail_closed_forward(self) -> None:
        policy = load("n6_strategy_center_reviewed_view_date_authority_084_v1")
        self.assertEqual(policy["migration_id"], "084")
        self.assertEqual(policy["attempts"], 1)
        self.assertEqual(policy["retries"], 0)
        self.assertEqual(policy["function_calls"], 0)
        self.assertEqual(len(policy["required_authority_views"]), 3)
        self.assertEqual(policy["authority_rule"], "latest_complete_single_batch_for_trade_date_consensus")
        self.assertNotIn("common_trade_calendar", policy["required_authority_views"])
        self.assertIn("common_trade_calendar", policy["forbidden_objects"])
        self.assertEqual(policy["default_runtime_execution_decision"], "REJECT")

    def test_write_restore_requires_canary_and_quiescence(self) -> None:
        policy = load("n6_strategy_center_post_canary_web_write_restore_v1")
        self.assertEqual(policy["launch_agent_label"], "com.ashare-v3.n6.user-web")
        self.assertEqual(policy["required_flag_before"], "0")
        self.assertEqual(policy["required_flag_after"], "1")
        self.assertEqual(policy["required_evaluator_ticks"], 12)
        self.assertTrue(policy["evaluator_must_remain_quiesced"])
        self.assertEqual(policy["max_bootout_attempts"], 1)
        self.assertEqual(policy["max_bootstrap_attempts"], 1)
        self.assertEqual(policy["max_retries"], 0)
        self.assertEqual(policy["default_runtime_execution_decision"], "REJECT")

    def test_governance_text_forbids_calendar_authority(self) -> None:
        compiler = (ROOT / "docs" / "EXECUTION_COMPILER.md").read_text(encoding="utf-8")
        trace = (ROOT / "docs" / "EXECUTION_TRACE_SYSTEM.md").read_text(encoding="utf-8")
        self.assertIn("latest complete singleton batches", compiler)
        self.assertIn("common_trade_calendar` and all", compiler)
        self.assertIn("membership as-of provenance", trace)

    def test_general_runtime_and_database_write_remain_rejected(self) -> None:
        kernel = KERNEL.read_text(encoding="utf-8")
        self.assertIn('"default_runtime_execution_decision": "REJECT"', kernel)
        sandbox = (ROOT / "docs" / "EXECUTION_SANDBOX.md").read_text(encoding="utf-8")
        self.assertIn("all other", sandbox)
        self.assertIn("simulated `STOP`", sandbox)


if __name__ == "__main__":
    unittest.main()
