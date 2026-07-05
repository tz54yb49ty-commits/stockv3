import unittest
from pathlib import Path

from run_n4_trigger_rule_v4_execute_once import build_arg_parser

from ashare_v3.trigger.rule_v4_execute import (
    ALLOWED_V4_EXECUTE_WRITE_TABLES,
    V4OutcomePersistenceStrategy,
    V4TriggerExecuteBlocked,
    assert_v4_execute_confirmed,
    build_v4_execute_write_plan,
    build_v4_rollback_sql,
)


def _plan(
    outcome,
    *,
    condition_key="BUY:D",
    signal_type="B_BUY",
    n5_entry_allowed=False,
    trigger_live=False,
    asset_kind="stock",
    identity_key="stock:SZ:000001",
):
    event_type = "TriggerMatched" if outcome == "matched" else (
        "TriggerPendingMarketData" if outcome == "pending_market_data" else None
    )
    return {
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "trade_date": "20260603",
        "direction": "buy" if signal_type == "B_BUY" else "sell",
        "signal_type": signal_type,
        "condition_key": condition_key,
        "original_condition_key": condition_key,
        "trigger_kind": "hint" if condition_key in {"BUY_HINT", "SELL_HINT"} else "trigger",
        "outcome_classification": outcome,
        "output_event_type": event_type,
        "trigger_live": trigger_live,
        "current_status": outcome,
        "n5_entry_allowed": n5_entry_allowed,
        "trigger_mark_candidate": "normal",
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "triggered_periods": ["D"] if outcome == "matched" and condition_key != "BUY_HINT" else [],
        "all_trigger_periods": ["D"] if outcome == "matched" and condition_key != "BUY_HINT" else [],
        "primary_trigger_period": "D" if outcome == "matched" and condition_key != "BUY_HINT" else None,
        "projection_period": "30m" if condition_key == "BUY_HINT" else None,
        "source_event_id": "snapshot_1",
        "source_event_type": "MarketSnapshotUpdated",
        "source_market_data_run_id": "snapshot_run",
        "source_condition_run_id": "condition_run",
        "data_quality_status": "passed",
        "match_basis": "v4_context_projection_enrichment",
    }


class N4TriggerRuleV4ExecuteTests(unittest.TestCase):
    def test_missing_execute_flag_blocks_before_write(self):
        with self.assertRaises(V4TriggerExecuteBlocked) as ctx:
            assert_v4_execute_confirmed(execute=False, user_confirmed=True)

        self.assertIn("--execute", str(ctx.exception))

    def test_missing_user_confirmed_flag_blocks_before_write(self):
        with self.assertRaises(V4TriggerExecuteBlocked) as ctx:
            assert_v4_execute_confirmed(execute=True, user_confirmed=False)

        self.assertIn("--user-confirmed", str(ctx.exception))

    def test_matched_only_strategy_writes_only_valid_n5_entry_outbox(self):
        plans = [
            _plan("matched", n5_entry_allowed=True, trigger_live=True),
            _plan("no_op"),
            _plan("quality_blocked", condition_key="BUY:FULL"),
            _plan("quality_blocked", identity_key="stock:BJ:920001"),
        ]
        write_plan = build_v4_execute_write_plan(
            plans,
            execute_run_id="trigger_rule_v4_execute_test",
            trigger_context_run_id="trigger_context_test",
            snapshot_run_id="snapshot_test",
        )

        self.assertEqual(write_plan["outcome_persistence_strategy"], V4OutcomePersistenceStrategy.MATCHED_ONLY)
        self.assertEqual(write_plan["write_counts"]["TriggerMatched"], 1)
        self.assertEqual(write_plan["write_counts"]["common_trigger_match"], 1)
        self.assertEqual(write_plan["write_counts"]["common_trigger_state"], 1)
        self.assertEqual(write_plan["write_counts"]["common_event_outbox"], 1)
        self.assertEqual(write_plan["suppressed_counts"]["no_op"], 1)
        self.assertEqual(write_plan["suppressed_counts"]["quality_blocked"], 2)
        self.assertEqual(write_plan["invalid_n5_entry_count"], 0)

    def test_full_matched_plan_is_persisted_when_it_is_valid_n5_entry(self):
        plans = [
            _plan("matched", condition_key="BUY:FULL", n5_entry_allowed=True, trigger_live=True),
        ]
        write_plan = build_v4_execute_write_plan(
            plans,
            execute_run_id="trigger_rule_v4_execute_test",
            trigger_context_run_id="trigger_context_test",
            snapshot_run_id="snapshot_test",
        )

        self.assertEqual(write_plan["write_counts"]["TriggerMatched"], 1)
        self.assertEqual(write_plan["write_counts"]["common_trigger_match"], 1)
        self.assertEqual(write_plan["full_blocked_count"], 0)
        self.assertEqual(write_plan["matched_write_plans"][0]["condition_key"], "BUY:FULL")

    def test_no_op_quality_blocked_full_and_bj_do_not_write_trigger_matched(self):
        plans = [
            _plan("no_op"),
            _plan("quality_blocked", condition_key="BUY:FULL"),
            _plan("quality_blocked", identity_key="index:BJ:899050", asset_kind="index"),
        ]
        write_plan = build_v4_execute_write_plan(
            plans,
            execute_run_id="trigger_rule_v4_execute_test",
            trigger_context_run_id="trigger_context_test",
            snapshot_run_id="snapshot_test",
        )

        self.assertEqual(write_plan["write_counts"]["TriggerMatched"], 0)
        self.assertEqual(write_plan["full_blocked_count"], 1)
        self.assertEqual(write_plan["bj_quality_blocked_count"], 1)
        self.assertEqual(write_plan["invalid_n5_entry_count"], 0)

    def test_bj_quality_blocked_count_includes_index_899050_and_899601(self):
        plans = [
            _plan("quality_blocked", identity_key="index:BJ:899050", asset_kind="index"),
            _plan("quality_blocked", identity_key="index:BJ:899050", asset_kind="index", condition_key="SELL:D", signal_type="S_SELL"),
            _plan("quality_blocked", identity_key="index:BJ:899601", asset_kind="index"),
            _plan("quality_blocked", identity_key="index:BJ:899601", asset_kind="index", condition_key="SELL:D", signal_type="S_SELL"),
            _plan("quality_blocked", identity_key="stock:SZ:000001"),
        ]
        write_plan = build_v4_execute_write_plan(
            plans,
            execute_run_id="trigger_rule_v4_execute_test",
            trigger_context_run_id="trigger_context_test",
            snapshot_run_id="snapshot_test",
        )

        self.assertEqual(write_plan["bj_quality_blocked_count"], 4)
        self.assertTrue(write_plan["bj_quality_blocked_visible"])

    def test_invalid_n5_entry_is_visible_and_not_written(self):
        plans = [
            _plan("matched", signal_type="BUY_HINT", n5_entry_allowed=True, trigger_live=True),
        ]

        write_plan = build_v4_execute_write_plan(
            plans,
            execute_run_id="trigger_rule_v4_execute_test",
            trigger_context_run_id="trigger_context_test",
            snapshot_run_id="snapshot_test",
        )

        self.assertEqual(write_plan["write_counts"]["TriggerMatched"], 0)
        self.assertEqual(write_plan["invalid_n5_entry_count"], 1)

    def test_allowed_write_scope_is_fixed(self):
        self.assertEqual(
            ALLOWED_V4_EXECUTE_WRITE_TABLES,
            (
                "common_trigger_run",
                "common_trigger_quality_item",
                "common_trigger_state",
                "common_trigger_match",
                "common_event_outbox",
            ),
        )

    def test_rollback_sql_hard_fails_before_delete(self):
        sql = build_v4_rollback_sql("trigger_rule_v4_execute_test")
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertLess(sql.index("RAISE EXCEPTION"), sql.index("DELETE FROM"))
        self.assertIn("common_trigger_match", sql)
        self.assertIn("common_event_outbox", sql)

    def test_runner_source_does_not_use_forbidden_inputs(self):
        source = Path("src/ashare_v3/trigger/rule_v4_execute.py").read_text()
        forbidden_terms = [
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "previous_day_minute",
            "mootdx",
            "tushare",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)

    def test_runner_accepts_dry_run_json_and_preflight_aliases(self):
        parser = build_arg_parser()
        args = parser.parse_args(
            [
                "--dry-run-json-path",
                "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_dry_run_report.json",
                "--preflight-path",
                "docs/N4_TRIGGER_RULE_SPEC_v4_execute_preflight_draft.json",
            ]
        )

        self.assertEqual(
            args.dry_run_report_path,
            "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_dry_run_report.json",
        )
        self.assertEqual(
            args.readiness_path,
            "docs/N4_TRIGGER_RULE_SPEC_v4_execute_preflight_draft.json",
        )

    def test_contract_and_preflight_use_requested_execute_command(self):
        expected = (
            "PYTHONPATH=src:scripts python3 scripts/run_n4_trigger_rule_v4_execute_once.py \\\n"
            "  --execute-run-id trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1 \\\n"
            "  --dry-run-json-path docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_dry_run_report.json \\\n"
            "  --contract-path docs/N4_TRIGGER_RULE_SPEC_v4_execute_contract_draft.json \\\n"
            "  --preflight-path docs/N4_TRIGGER_RULE_SPEC_v4_execute_preflight_draft.json \\\n"
            "  --rollback-sql-path sql/N4_TRIGGER_RULE_SPEC_v4_execute_rollback_draft.sql \\\n"
            "  --execute \\\n"
            "  --user-confirmed"
        )
        for path in (
            Path("docs/N4_TRIGGER_RULE_SPEC_v4_execute_contract_draft.json"),
            Path("docs/N4_TRIGGER_RULE_SPEC_v4_execute_preflight_draft.json"),
        ):
            data = __import__("json").loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["execute_command_candidate"], expected)


if __name__ == "__main__":
    unittest.main()
