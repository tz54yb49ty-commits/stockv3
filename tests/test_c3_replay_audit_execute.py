import inspect
import unittest

import ashare_v3.trigger.c3_replay_audit_execute as replay_audit_execute
from ashare_v3.trigger.c3_replay_audit_execute import (
    ALLOWED_WRITE_TABLES,
    DEFAULT_REPLAY_RUN_ID,
    EXPECTED_CLASSIFICATION_COUNTS,
    C3ReplayAuditExecuteError,
    assert_execute_confirmed,
    build_audit_rows_from_evaluations,
    build_execute_contract,
    build_preflight_report_from_inputs,
    summarize_audit_rows,
)


class C3ReplayAuditExecuteTests(unittest.TestCase):
    def test_execute_requires_execute_flag(self) -> None:
        with self.assertRaises(C3ReplayAuditExecuteError):
            assert_execute_confirmed(execute=False, user_confirmed=True, replay_run_id=DEFAULT_REPLAY_RUN_ID)

    def test_execute_requires_user_confirmation_flag(self) -> None:
        with self.assertRaises(C3ReplayAuditExecuteError):
            assert_execute_confirmed(execute=True, user_confirmed=False, replay_run_id=DEFAULT_REPLAY_RUN_ID)

    def test_contract_is_audit_only_and_has_no_outbox_or_consumer_writes(self) -> None:
        contract = build_execute_contract()

        self.assertEqual(contract["execution_shape"], "audit_only_run_once")
        self.assertTrue(contract["requires_execute_flag"])
        self.assertTrue(contract["requires_user_confirmed_flag"])
        self.assertEqual(contract["allowed_write_tables"], list(ALLOWED_WRITE_TABLES))
        self.assertFalse(contract["outbox_policy"]["emit_n4_outbox"])
        self.assertEqual(contract["planned_standard_n4_outbox_counts"], {
            "TriggerMatched": 0,
            "TriggerPendingMarketData": 0,
            "TriggerCleared": 0,
        })
        for forbidden in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger_match",
            "common_trigger_state",
        ):
            self.assertIn(forbidden, contract["forbidden_write_tables"])

    def test_builds_replay_audit_rows_from_evaluations(self) -> None:
        rows = build_audit_rows_from_evaluations(
            replay_run_id=DEFAULT_REPLAY_RUN_ID,
            source_c3_run_id="c3_run",
            source_c2b_run_id="c2b_run",
            source_n4_projection_run_id="n4_run",
            source_trigger_context_run_id="context_run",
            source_n5_action_run_id="n5_run",
            evaluations=[
                evaluation(
                    asset_kind="stock",
                    identity_key="stock:SH:600000",
                    classification="would_match",
                    diff_case="projection_not_matched_but_closed_matched",
                    projection_matched=False,
                    closed_signal_status="up_volume_expanding",
                ),
                evaluation(
                    asset_kind="board",
                    identity_key="board:TDX:881001",
                    classification="missing",
                    diff_case="replay_blocked",
                    projection_matched=True,
                    closed_signal_status="missing",
                    signal_type="S_SELL_30M_SHRINK",
                    direction="sell",
                    condition_key="SELL:Y,D",
                ),
            ],
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["target_table"], "stock_trigger_replay_audit")
        self.assertEqual(rows[0]["exchange"], "SH")
        self.assertEqual(rows[0]["code"], "600000")
        self.assertEqual(rows[0]["replay_classification"], "would_match")
        self.assertEqual(rows[0]["original_trigger_status"], "missing")
        self.assertEqual(rows[1]["target_table"], "board_trigger_replay_audit")
        self.assertEqual(rows[1]["exchange"], "TDX")
        self.assertEqual(rows[1]["quality_status"], "missing")
        self.assertNotIn("classification", rows[0]["comparison_key"])

    def test_preflight_blocks_when_baseline_scoped_rows_are_nonzero(self) -> None:
        report = build_preflight_report_from_inputs(
            dry_run_report=dry_run_report(),
            audit_rows=[evaluation_audit_row("would_match")],
            schema_status=present_schema_status(),
            baseline_guard=zero_baseline_guard() | {"common_trigger_run": 1},
            c3_outbox_status={"pending": 17432},
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            rollback_sql_exists=True,
        )

        self.assertEqual(report["result"], "PREFLIGHT_BLOCKED")
        failed = {item["gate_code"] for item in report["quality"]["items"] if item["status"] == "failed"}
        self.assertIn("n4_c3_replay_audit_baseline_zero", failed)
        self.assertFalse(report["next_gate"]["allow_execute_final_gate"])

    def test_preflight_passes_with_zero_baseline_and_counts_matching_dry_run(self) -> None:
        audit_rows = [
            *[evaluation_audit_row("would_match") for _ in range(4734)],
            *[evaluation_audit_row("would_clear") for _ in range(245)],
            *[evaluation_audit_row("would_change") for _ in range(243)],
            *[evaluation_audit_row("unchanged") for _ in range(30730)],
            *[evaluation_audit_row("missing") for _ in range(18)],
        ]
        report = build_preflight_report_from_inputs(
            dry_run_report=dry_run_report(),
            audit_rows=audit_rows,
            schema_status=present_schema_status(),
            baseline_guard=zero_baseline_guard(),
            c3_outbox_status={"pending": 17432},
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            rollback_sql_exists=True,
        )

        self.assertEqual(report["result"], "PREFLIGHT_PASS")
        self.assertEqual(report["audit_plan_summary"]["total"], 35970)
        self.assertEqual(report["audit_plan_summary"]["by_classification"], EXPECTED_CLASSIFICATION_COUNTS)
        self.assertEqual(report["planned_standard_n4_outbox_counts"], {
            "TriggerMatched": 0,
            "TriggerPendingMarketData": 0,
            "TriggerCleared": 0,
        })
        self.assertFalse(report["side_effects"]["writes_performed"])
        self.assertFalse(report["side_effects"]["common_event_outbox_written"])
        self.assertFalse(report["side_effects"]["common_event_inbox_written"])
        self.assertFalse(report["side_effects"]["checkpoint_written"])
        self.assertFalse(report["side_effects"]["trigger_match_written"])
        self.assertFalse(report["side_effects"]["trigger_state_written"])
        self.assertTrue(report["next_gate"]["allow_execute_final_gate"])

    def test_summarize_audit_rows_keeps_classification_counts_visible(self) -> None:
        summary = summarize_audit_rows(
            [
                evaluation_audit_row("would_match", target_table="stock_trigger_replay_audit"),
                evaluation_audit_row("would_match", target_table="stock_trigger_replay_audit"),
                evaluation_audit_row("missing", target_table="board_trigger_replay_audit"),
            ]
        )

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["by_classification"], {"missing": 1, "would_match": 2})
        self.assertEqual(summary["by_target_table"], {"board_trigger_replay_audit": 1, "stock_trigger_replay_audit": 2})

    def test_runner_source_has_no_outbox_inbox_checkpoint_or_trigger_fact_writes(self) -> None:
        module_source = inspect.getsource(replay_audit_execute)

        for forbidden in (
            "INSERT INTO common_event_outbox",
            "INSERT INTO common_event_inbox",
            "INSERT INTO common_event_consumer_checkpoint",
            "UPDATE common_event_consumer_checkpoint",
            "INSERT INTO common_trigger_match",
            "INSERT INTO common_trigger_state",
            "ActionEvent",
            "HintEvent",
            "RiskEvent",
            "PositionEvent",
            "start_worker(",
        ):
            self.assertNotIn(forbidden, module_source)


def dry_run_report() -> dict:
    return {
        "result": "DRY_RUN_PASS",
        "replay_run_id": DEFAULT_REPLAY_RUN_ID,
        "allowed_c3_run_id": "c3_run",
        "c2b_run_id": "c2b_run",
        "trigger_context_run_id": "context_run",
        "original_n4_projection_execute_run_id": "n4_run",
        "original_n5_action_execute_run_id": "n5_run",
        "source_condition_run_id": "condition_run",
        "classification_summary": {
            "candidate_count": 35970,
            "by_classification": dict(EXPECTED_CLASSIFICATION_COUNTS),
        },
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": []},
        "input_boundary": {
            "accepted_c3_outbox_row_count": 17432,
            "rejected_c3_outbox_row_count": 0,
        },
    }


def present_schema_status() -> dict:
    return {
        "stock_trigger_replay_audit": {"exists": True, "row_count": 0, "index_count": 9},
        "index_trigger_replay_audit": {"exists": True, "row_count": 0, "index_count": 9},
        "board_trigger_replay_audit": {"exists": True, "row_count": 0, "index_count": 9},
    }


def zero_baseline_guard() -> dict:
    return {
        "common_trigger_run": 0,
        "common_trigger_quality_item": 0,
        "stock_trigger_replay_audit": 0,
        "index_trigger_replay_audit": 0,
        "board_trigger_replay_audit": 0,
        "common_event_outbox": 0,
        "common_event_inbox": 0,
        "common_event_consumer_checkpoint": 0,
        "common_trigger_match": 0,
        "common_trigger_state": 0,
    }


def guard_counts() -> dict:
    return {
        "common_event_outbox": {"exists": True, "row_count": 100},
        "common_event_inbox": {"exists": True, "row_count": 20},
        "common_event_consumer_checkpoint": {"exists": True, "row_count": 10},
        "common_trigger_match": {"exists": True, "row_count": 5},
        "common_trigger_state": {"exists": True, "row_count": 5},
    }


def evaluation(
    *,
    asset_kind: str = "stock",
    identity_key: str = "stock:SH:600000",
    classification: str = "would_match",
    diff_case: str = "projection_not_matched_but_closed_matched",
    projection_matched: bool = False,
    closed_signal_status: str = "up_volume_expanding",
    signal_type: str = "B_BUY_30M_VOL",
    direction: str = "buy",
    condition_key: str = "BUY:Y,D",
) -> dict:
    return {
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "trigger_period": "30m",
        "trigger_bucket": "20260525_1400_1430",
        "classification": classification,
        "diff_case": diff_case,
        "projection_matched": projection_matched,
        "projection_output_event_type": "TriggerMatched" if projection_matched else None,
        "closed_signal_status": closed_signal_status,
        "closed_quality_status": "passed" if classification not in {"missing", "not_ready"} else "missing",
        "projection_signal_status": "missing",
        "projection_trigger_match_id": 88 if projection_matched else None,
        "source_c3_event_id": "evt_c3",
        "closed_signal_enrichment_id": 99,
        "source_condition_run_id": "condition_run",
        "value_trace": {"closed_amount_ratio": "1.25"},
        "period_trigger_baseline_trace_present": True,
    }


def evaluation_audit_row(classification: str, *, target_table: str = "stock_trigger_replay_audit") -> dict:
    return {
        "target_table": target_table,
        "replay_classification": classification,
        "replay_diff_type": "replay_blocked" if classification in {"missing", "not_ready"} else "unchanged",
        "comparison_key": f"stock|stock:SH:600000|buy|B_BUY_30M_VOL|BUY:Y,D|30m|bucket|{classification}",
    }


if __name__ == "__main__":
    unittest.main()
