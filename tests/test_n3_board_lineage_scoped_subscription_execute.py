import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ashare_v3.market.action_confirmation_metric_board_lineage_repair_plan import (
    BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
    build_board_lineage_repair_artifacts,
    build_board_lineage_subscription_rollback_sql,
    build_subscription_execute_artifacts,
    build_subscription_execute_dry_run_report,
    run_board_lineage_scoped_subscription_execute,
)


def sample_board_rows(count: int = 28) -> list[dict[str, object]]:
    return [
        {
            "identity_key": f"board:TDX:{880200 + index:06d}",
            "code": f"{880200 + index:06d}",
            "name": f"board {index}",
            "trigger_match_id": 1000 + index,
            "source_minute_target_scope_id": 10000 + index,
            "source_condition_pool_id": 2000 + index,
            "source_condition_basis_id": 3000 + index,
            "direction": "sell",
            "signal_type": "S_SELL",
            "condition_key": "SELL:Y",
            "projection_status": "not_ready",
            "projection_quality_status": "blocked",
            "trace_status": "blocked",
            "excluded_reason": "lineage_missing",
            "missing_reasons": ["missing_today_minute_elapsed"],
        }
        for index in range(1, count + 1)
    ]


def sample_artifacts() -> dict[str, object]:
    base = build_board_lineage_repair_artifacts(
        missing_board_rows=sample_board_rows(),
        baseline={"total": 0},
        source_status={"n4_trigger_execute": "passed"},
    )
    return build_subscription_execute_artifacts(
        repair_payload=base["payload"],
        repair_preflight=base["preflight"],
    )


class N3BoardLineageScopedSubscriptionExecuteTest(unittest.TestCase):
    def test_subscription_execute_artifacts_have_expected_scope(self) -> None:
        artifacts = sample_artifacts()
        contract = artifacts["contract"]
        preflight = artifacts["preflight"]
        dry_run = artifacts["execute_dry_run_report"]

        self.assertEqual(contract["contract_result"], "CONTRACT_PASS")
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(contract["execute_target"], "subscription_control_only")
        self.assertFalse(contract["metric_v2_execute"])
        self.assertEqual(contract["board_objects"], 28)
        self.assertEqual(contract["subscription_candidate_rows"], 56)
        self.assertEqual(contract["subscription_rows"], 56)
        self.assertEqual(contract["pull_plan_rows"], 2)
        self.assertEqual(dry_run["mode"], "dry_run")
        self.assertEqual(dry_run["stage"], "N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_SCOPE")
        self.assertEqual(dry_run["market_data_run_id"], BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605)
        self.assertEqual(dry_run["candidate_row_count"], 56)
        self.assertEqual(dry_run["subscription_row_count"], 56)
        self.assertEqual(dry_run["market_data_pull_plan_row_count"], 2)
        candidate_sample = dry_run["market_data_subscription_candidate"]["rows"][0]
        subscription_sample = dry_run["market_data_subscription_dedup"]["rows"][0]
        self.assertEqual(candidate_sample["source_scope_table"], "board_minute_target_scope")
        self.assertEqual(subscription_sample["source_scope_tables"], ["board_minute_target_scope"])
        self.assertEqual(candidate_sample["source_scope_required_flags"]["source_trigger_match_ref"], "common_trigger_match:1001")

    def test_rollback_deletes_only_scoped_subscription_control_rows_after_hard_fail(self) -> None:
        sql = build_board_lineage_subscription_rollback_sql()
        upper = sql.upper()
        first_raise = upper.find("RAISE EXCEPTION")
        first_delete = upper.find("DELETE FROM")

        self.assertNotEqual(first_raise, -1)
        self.assertLess(first_raise, first_delete)
        self.assertIn("DELETE FROM common_market_data_subscription_candidate", sql)
        self.assertIn("DELETE FROM common_market_data_subscription", sql)
        self.assertIn("DELETE FROM common_market_data_pull_plan", sql)
        self.assertIn("DELETE FROM common_market_data_quality_item", sql)
        self.assertIn("DELETE FROM common_market_data_run", sql)
        self.assertNotIn("DELETE FROM board_action_confirmation_projection_metric", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertNotIn("CASCADE", upper)
        self.assertNotIn("DROP ", upper)
        self.assertNotIn("TRUNCATE", upper)
        self.assertIn("board_minute_bar_1m", sql)
        self.assertIn("board_action_confirmation_projection_metric", sql)
        self.assertIn("common_trigger_match", sql)
        self.assertIn("common_action_event", sql)
        self.assertIn("n6_virtual_position", sql)

    def test_runner_blocks_before_db_without_execute_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            contract_path = Path(tmpdir) / "missing_contract.json"
            preflight_path = Path(tmpdir) / "missing_preflight.json"
            payload_path = Path(tmpdir) / "missing_payload.json"

            result = run_board_lineage_scoped_subscription_execute(
                dsn="postgresql://unused",
                contract_path=contract_path,
                preflight_path=preflight_path,
                payload_path=payload_path,
                execute=False,
                user_confirmed=True,
            )
            self.assertEqual(result["result"], "BLOCKED")
            self.assertIn("missing_execute_flag", result["blocked_reasons"])
            self.assertTrue(result["blocked_before_database_write"])

            result = run_board_lineage_scoped_subscription_execute(
                dsn="postgresql://unused",
                contract_path=contract_path,
                preflight_path=preflight_path,
                payload_path=payload_path,
                execute=True,
                user_confirmed=False,
            )
            self.assertEqual(result["result"], "BLOCKED")
            self.assertIn("missing_user_confirmed_flag", result["blocked_reasons"])
            self.assertTrue(result["blocked_before_database_write"])

    def test_runner_validates_contract_before_persisting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = sample_artifacts()
            contract = dict(artifacts["contract"])
            contract["metric_v2_execute"] = True
            contract_path = Path(tmpdir) / "contract.json"
            preflight_path = Path(tmpdir) / "preflight.json"
            payload_path = Path(tmpdir) / "payload.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            preflight_path.write_text(json.dumps(artifacts["preflight"]), encoding="utf-8")
            payload_path.write_text(json.dumps(artifacts["payload"]), encoding="utf-8")

            result = run_board_lineage_scoped_subscription_execute(
                dsn="postgresql://unused",
                contract_path=contract_path,
                preflight_path=preflight_path,
                payload_path=payload_path,
                execute=True,
                user_confirmed=True,
            )

            self.assertEqual(result["result"], "BLOCKED")
            self.assertIn("metric_v2_execute_must_be_false", result["blocked_reasons"])
            self.assertTrue(result["blocked_before_database_write"])

    def test_runner_persists_only_subscription_control_rows_when_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = sample_artifacts()
            contract_path = Path(tmpdir) / "contract.json"
            preflight_path = Path(tmpdir) / "preflight.json"
            payload_path = Path(tmpdir) / "payload.json"
            report_path = Path(tmpdir) / "report.json"
            markdown_path = Path(tmpdir) / "report.md"
            contract_path.write_text(json.dumps(artifacts["contract"]), encoding="utf-8")
            preflight_path.write_text(json.dumps(artifacts["preflight"]), encoding="utf-8")
            payload_path.write_text(json.dumps(artifacts["payload"]), encoding="utf-8")

            before = {
                "target_run_exists": False,
                "n3_fact_and_event_row_counts": {"common_event_outbox": 10},
                "target_run_row_counts": {},
            }
            after = {
                "target_run_exists": True,
                "n3_fact_and_event_row_counts": {"common_event_outbox": 10},
                "target_run_row_counts": {
                    "common_market_data_run": 1,
                    "common_market_data_quality_item": 7,
                    "common_market_data_subscription_candidate": 56,
                    "common_market_data_subscription": 56,
                    "common_market_data_pull_plan": 2,
                },
                "market_data_run_row": {"status": "passed"},
            }
            with patch(
                "ashare_v3.market.action_confirmation_metric_board_lineage_repair_plan.capture_subscription_execution_backup",
                side_effect=[before, after],
            ), patch(
                "ashare_v3.market.action_confirmation_metric_board_lineage_repair_plan.persist_subscription_plan",
                return_value={
                    "market_data_run_rows_written": 1,
                    "quality_item_rows_written": 7,
                    "candidate_rows_written": 56,
                    "subscription_rows_written": 56,
                    "pull_plan_rows_written": 2,
                    "market_data_fact_rows_written": 0,
                    "event_outbox_rows_written": 0,
                },
            ):
                result = run_board_lineage_scoped_subscription_execute(
                    dsn="postgresql://unused",
                    contract_path=contract_path,
                    preflight_path=preflight_path,
                    payload_path=payload_path,
                    json_report_path=report_path,
                    markdown_report_path=markdown_path,
                    execute=True,
                    user_confirmed=True,
                )

            self.assertEqual(result["result"], "EXECUTE_PASS")
            self.assertEqual(result["write_result"]["candidate_rows_written"], 56)
            self.assertEqual(result["write_result"]["subscription_rows_written"], 56)
            self.assertEqual(result["write_result"]["pull_plan_rows_written"], 2)
            self.assertEqual(result["write_result"]["market_data_fact_rows_written"], 0)
            self.assertEqual(result["write_result"]["event_outbox_rows_written"], 0)
            self.assertFalse(result["side_effects"]["writes_market_data_facts"])
            self.assertFalse(result["side_effects"]["writes_outbox"])


if __name__ == "__main__":
    unittest.main()
