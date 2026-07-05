import json
import unittest

from ashare_v3.market.action_confirmation_metric_board_lineage_repair_plan import (
    BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
    EXPECTED_BOARD_OBJECTS,
    TODAY_BARS_PER_OBJECT_UNTIL_1127,
    build_board_lineage_repair_artifacts,
    build_board_lineage_repair_rollback_sql,
)


def sample_board_rows(count: int = EXPECTED_BOARD_OBJECTS) -> list[dict[str, object]]:
    return [
        {
            "identity_key": f"board:TDX:{880200 + index:06d}",
            "code": f"{880200 + index:06d}",
            "name": f"board {index}",
            "trigger_match_id": index,
            "source_minute_target_scope_id": 10000 + index,
            "source_condition_pool_id": 20000 + index,
            "projection_status": "not_ready",
            "projection_quality_status": "blocked",
            "trace_status": "blocked",
            "excluded_reason": "lineage_missing",
            "missing_reasons": [
                "missing_today_minute_elapsed",
                "missing_current_lineage_previous_day_elapsed",
            ],
        }
        for index in range(1, count + 1)
    ]


class N3ActionConfirmationMetricBoardLineageRepairPlanTest(unittest.TestCase):
    def test_board_lineage_plan_counts_are_scoped_to_28_boards(self) -> None:
        artifacts = build_board_lineage_repair_artifacts(
            missing_board_rows=sample_board_rows(),
            baseline={"total": 0},
            source_status={"n4_trigger_execute": "passed"},
        )

        dry_run = artifacts["dry_run"]
        contract = artifacts["contract"]
        payload = artifacts["payload"]

        self.assertEqual(dry_run["result"], "DRY_RUN_PASS")
        self.assertEqual(dry_run["missing_board_objects"], 28)
        self.assertEqual(dry_run["subscription_plan"]["candidate_rows"], 56)
        self.assertEqual(dry_run["subscription_plan"]["subscription_rows"], 56)
        self.assertEqual(dry_run["subscription_plan"]["pull_plan_rows"], 2)
        self.assertEqual(dry_run["minute_plan"]["previous_day_minute_rows"], 28 * 240)
        self.assertEqual(dry_run["minute_plan"]["today_minute_rows"], 28 * TODAY_BARS_PER_OBJECT_UNTIL_1127)
        self.assertEqual(dry_run["metric_repair_plan"]["additive_metric_rows_max"], 28)
        candidate_sample = payload["market_data_subscription_candidate"]["rows"][0]
        self.assertEqual(candidate_sample["source_scope_table"], "board_minute_target_scope")
        self.assertGreater(candidate_sample["source_scope_id"], 0)
        self.assertEqual(candidate_sample["source_scope_required_flags"]["source_trigger_match_ref"], "common_trigger_match:1")
        self.assertEqual(contract["future_write_scope"]["metric_v2"], [
            "common_market_data_run",
            "common_market_data_quality_item",
            "board_action_confirmation_projection_metric",
        ])
        self.assertEqual(len(payload["missing_board_objects"]), 28)

    def test_wrong_scope_is_blocked(self) -> None:
        rows = sample_board_rows(27)
        artifacts = build_board_lineage_repair_artifacts(
            missing_board_rows=rows,
            baseline={"total": 0},
            source_status={"n4_trigger_execute": "passed"},
        )

        self.assertEqual(artifacts["preflight"]["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("n3_board_lineage_repair_missing_board_count", artifacts["preflight"]["blockers"])

    def test_rollback_is_metric_only_and_hard_fails_before_delete(self) -> None:
        sql = build_board_lineage_repair_rollback_sql()
        first_raise = sql.upper().find("RAISE EXCEPTION")
        first_delete = sql.upper().find("DELETE FROM")

        self.assertNotEqual(first_raise, -1)
        self.assertLess(first_raise, first_delete)
        self.assertIn(BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605, sql)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("common_trigger_match", sql)
        self.assertIn("common_action_event", sql)
        self.assertIn("user_signal_projection", sql)
        self.assertIn("n6_virtual_position", sql)
        self.assertIn("DELETE FROM board_action_confirmation_projection_metric", sql)
        self.assertNotIn("DELETE FROM stock_action_confirmation_projection_metric", sql)
        self.assertNotIn("DELETE FROM index_action_confirmation_projection_metric", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertNotIn("DELETE FROM common_event_inbox", sql)
        self.assertNotIn("DELETE FROM common_event_consumer_checkpoint", sql)
        self.assertNotIn("CASCADE", sql.upper())
        self.assertNotIn("DROP ", sql.upper())
        self.assertNotIn("TRUNCATE", sql.upper())

    def test_artifacts_are_json_serializable_and_forbid_downstream_scope(self) -> None:
        artifacts = build_board_lineage_repair_artifacts(
            missing_board_rows=sample_board_rows(),
            baseline={"total": 0},
            source_status={"n4_trigger_execute": "passed"},
        )
        for key in ("contract", "preflight", "dry_run", "payload"):
            json.dumps(artifacts[key], sort_keys=True)
        forbidden = set(artifacts["contract"]["forbidden_scope"])
        self.assertIn("N5/N6 action/outbox", forbidden)
        self.assertIn("worker", forbidden)
        self.assertIn("delivery/push/voice/mobile", forbidden)
        self.assertIn("sim/position/pnl/real trade", forbidden)


if __name__ == "__main__":
    unittest.main()
