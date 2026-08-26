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
    match = re.fullmatch(r"\s*```json\s*(\{.*\})\s*```\s*", block, re.DOTALL)
    if match is None:
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
        self.assertEqual(
            policy["authority_rule"],
            "latest_complete_single_batch_for_trade_date_consensus",
        )
        self.assertIn("common_trade_calendar", policy["forbidden_objects"])
        self.assertIn("n1_n5_raw_tables", policy["forbidden_objects"])
        self.assertEqual(
            policy["membership_rule"],
            "max_trade_date_lte_source_trade_date",
        )
        self.assertEqual(policy["default_runtime_execution_decision"], "REJECT")

    def test_write_restore_requires_current_canary_and_stable_evaluator(self) -> None:
        policy = load("n6_strategy_center_post_canary_web_write_restore_v1")
        self.assertEqual(policy["launch_agent_label"], "com.ashare-v3.n6.user-web")
        self.assertEqual(policy["required_flag_before"], "0")
        self.assertEqual(policy["required_flag_after"], "1")
        self.assertEqual(policy["required_evaluator_ticks"], 12)
        self.assertEqual(
            policy["required_evaluator_state"],
            "loaded_stable_exact_release",
        )
        self.assertEqual(policy["required_pending_count"], 0)
        self.assertEqual(policy["max_bootout_attempts"], 1)
        self.assertEqual(policy["max_bootstrap_attempts"], 1)
        self.assertEqual(policy["max_retries"], 0)

    def test_governance_text_forbids_calendar_authority(self) -> None:
        compiler = (ROOT / "docs" / "EXECUTION_COMPILER.md").read_text(
            encoding="utf-8"
        )
        trace = (ROOT / "docs" / "EXECUTION_TRACE_SYSTEM.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("latest complete singleton", compiler)
        self.assertIn("common_trade_calendar", compiler)
        self.assertIn("membership as-of provenance", trace)

    def test_general_runtime_and_database_write_remain_rejected(self) -> None:
        for policy_id in (
            "n6_strategy_center_reviewed_view_date_authority_084_v1",
            "n6_strategy_center_post_canary_web_write_restore_v1",
        ):
            self.assertEqual(
                load(policy_id)["default_runtime_execution_decision"],
                "REJECT",
            )


if __name__ == "__main__":
    unittest.main()
