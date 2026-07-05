import json
import unittest
from pathlib import Path

from ashare_v3.trigger.v4_corrected_execute_contract import (
    build_corrected_execute_contract,
    build_corrected_execute_preflight,
    build_corrected_execute_rollback_sql,
)


def _dry_run_report() -> dict:
    return {
        "result": "DRY_RUN_PASS",
        "execute_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        "trigger_context_run_id": "trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1",
        "snapshot_run_id": "realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1",
        "projection_run_id": "realtime_projection_metric_20260605_live2_compat__snapshot",
        "candidate_plans_before_strict_guard": 1537,
        "persisted_plans_after_strict_guard": 1240,
        "compliant_count": 1240,
        "blocked_count": 297,
        "blocked_counts_by_reason": {
            "missing trigger_price": 275,
            "missing trigger_kind": 0,
            "missing triggered_periods": 275,
            "missing n5_entry_allowed": 0,
            "future event_time": 0,
            "future trigger_time": 0,
            "FULL semantic blocked": 29,
            "invalid signal_type": 0,
            "invalid N5 entry": 0,
        },
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": []},
        "execute_preflight_could_pass": True,
    }


def _repaired_dry_run_report() -> dict:
    report = _dry_run_report()
    report.update(
        {
            "candidate_plans_before_strict_guard": 896,
            "persisted_plans_after_strict_guard": 605,
            "compliant_count": 605,
            "blocked_count": 291,
            "blocked_counts_by_reason": {
                "missing trigger_price": 275,
                "missing trigger_kind": 0,
                "missing triggered_periods": 275,
                "missing n5_entry_allowed": 0,
                "future event_time": 0,
                "future trigger_time": 0,
                "FULL semantic blocked": 23,
                "invalid signal_type": 0,
                "invalid N5 entry": 0,
            },
            "matcher_proof": {
                "trace_baseline_source_distribution_for_compliant": {"trigger_baseline": 605},
            },
            "n5_entry_eligibility_proof": {"invalid_n5_entry_count": 0},
        }
    )
    return report


class N420260605V4CorrectedExecuteContractTests(unittest.TestCase):
    def test_contract_freezes_corrected_planned_writes_and_blocked_counts(self) -> None:
        contract = build_corrected_execute_contract(_dry_run_report())

        self.assertEqual(contract["result"], "CONTRACT_PASS")
        self.assertEqual(contract["planned_writes"]["common_trigger_run"], 1)
        self.assertEqual(contract["planned_writes"]["common_trigger_state"], 1240)
        self.assertEqual(contract["planned_writes"]["common_trigger_match"], 1240)
        self.assertEqual(contract["planned_writes"]["common_event_outbox"], 1240)
        self.assertEqual(contract["planned_writes"]["TriggerMatched"], 1240)
        self.assertEqual(contract["planned_writes"]["TriggerPendingMarketData"], 0)
        self.assertEqual(contract["blocked_candidates"]["total"], 297)
        self.assertEqual(contract["blocked_candidates"]["by_reason"]["FULL semantic blocked"], 29)
        self.assertIn("trigger_price", contract["p0_guards"])
        self.assertIn("full_semantic_contract_guard", contract["p0_guards"])
        self.assertIn("n5_entry_allowed", contract["n5_entry_contract"]["required_payload_fields"])

    def test_repaired_contract_freezes_605_matched_and_trigger_baseline_guard(self) -> None:
        contract = build_corrected_execute_contract(
            _repaired_dry_run_report(),
            dry_run_path="docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_DRY_RUN.json",
            contract_path="docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_CONTRACT.json",
            preflight_path="docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_PREFLIGHT.json",
            rollback_sql_path="sql/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_ROLLBACK.sql",
        )

        self.assertEqual(contract["result"], "CONTRACT_PASS")
        self.assertEqual(contract["dry_run_artifact_path"], "docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_DRY_RUN.json")
        self.assertEqual(contract["planned_writes"]["common_trigger_state"], 605)
        self.assertEqual(contract["planned_writes"]["common_trigger_match"], 605)
        self.assertEqual(contract["planned_writes"]["common_event_outbox"], 605)
        self.assertEqual(contract["planned_writes"]["TriggerMatched"], 605)
        self.assertEqual(contract["blocked_candidates"]["total"], 291)
        self.assertEqual(contract["blocked_candidates"]["full_semantic_blocked"], 23)
        self.assertIn("baseline_source_trigger_baseline", contract["p0_guards"])
        self.assertEqual(contract["post_review_checks"]["baseline_source_not_trigger_baseline"], 0)

    def test_preflight_blocks_when_corrected_runner_is_missing_even_with_clean_baseline(self) -> None:
        contract = build_corrected_execute_contract(_dry_run_report())
        baseline = {
            "common_trigger_run": 0,
            "common_trigger_quality_item": 0,
            "common_trigger_state": 0,
            "common_trigger_match": 0,
            "common_event_outbox": 0,
            "common_event_inbox": 0,
            "common_event_consumer_checkpoint": 0,
            "n5_refs": 0,
            "n6_refs": 0,
        }

        preflight = build_corrected_execute_preflight(
            contract,
            baseline_refs=baseline,
            runner_exists=False,
        )

        self.assertEqual(preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertFalse(preflight["runner_readiness"]["ready"])
        self.assertEqual(preflight["baseline_refs"], baseline)
        self.assertIn("runner_missing", preflight["blockers"])

    def test_preflight_passes_when_runner_exists_and_baseline_is_clean(self) -> None:
        contract = build_corrected_execute_contract(_dry_run_report())
        baseline = {
            "common_trigger_run": 0,
            "common_trigger_quality_item": 0,
            "common_trigger_state": 0,
            "common_trigger_match": 0,
            "common_event_outbox": 0,
            "common_event_inbox": 0,
            "common_event_consumer_checkpoint": 0,
            "n5_refs": 0,
            "n6_refs": 0,
        }

        preflight = build_corrected_execute_preflight(
            contract,
            baseline_refs=baseline,
            runner_exists=True,
        )

        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertTrue(preflight["runner_readiness"]["ready"])
        self.assertEqual(preflight["planned_writes"]["TriggerMatched"], 1240)

    def test_rollback_sql_hard_fails_before_delete_and_scopes_to_corrected_run(self) -> None:
        sql = build_corrected_execute_rollback_sql("trigger_execute_20260605_condition_layer_20260604_source_20260604_v1")

        self.assertIn("RAISE EXCEPTION", sql)
        self.assertLess(sql.index("RAISE EXCEPTION"), sql.index("DELETE FROM"))
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_trigger_match", sql)
        self.assertIn("common_trigger_state", sql)
        self.assertIn("user_sim_order", sql)
        self.assertIn("user_sim_trade", sql)
        self.assertIn("user_sim_position", sql)
        self.assertIn("sim_run_id = $1", sql)
        self.assertNotIn("source_action_run_id = $1\n         OR source_event_id = $1\n         OR order_payload_json", sql)
        self.assertNotIn("stock_realtime_daily_snapshot", sql)
        self.assertNotIn("condition_pool", sql)

    def test_generated_artifacts_parse_when_present(self) -> None:
        for path in [
            Path("docs/N4_20260605_V4_CORRECTED_DRY_RUN.json"),
            Path("docs/N4_TRIGGER_RULE_V4_ENFORCEMENT_CONTRACT.json"),
        ]:
            self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)


if __name__ == "__main__":
    unittest.main()
