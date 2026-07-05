import unittest

from ashare_v3.action.metadata_repair import (
    ALLOWED_METADATA_REPAIR_KEYS,
    build_full_metric_union_metadata_repair_command,
    merge_metadata_repair_payload,
    run_full_metric_union_metadata_repair_from_artifacts,
    validate_metadata_repair_payload_artifact,
)


class ActionMetadataRepairRunnerTest(unittest.TestCase):
    def test_missing_execute_or_user_confirmation_blocks_before_writes(self) -> None:
        report = run_full_metric_union_metadata_repair_from_artifacts(
            execute=False,
            user_confirmed=True,
            contract=sample_contract(),
            preflight=sample_preflight(),
            dry_run=sample_dry_run(),
            payload=sample_payload_artifact(),
            rollback_sql_path="sql/N5_full_metric_union_historical_metadata_repair_20260605_rollback.sql",
            dsn="postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3",
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertFalse(report["allow_execute"])
        self.assertIn("n5_metadata_repair_double_confirmation", report["blockers"])
        self.assertFalse(report["side_effects"]["writes_performed"])
        self.assertFalse(report["side_effects"]["common_action_event_updated"])
        self.assertFalse(report["side_effects"]["common_event_outbox_updated"])

    def test_payload_merge_allows_only_metadata_keys_and_preserves_status_fields(self) -> None:
        current_payload = {
            "blocked_reason": "metric_missing",
            "event_type": "ActionBlocked",
            "action_state": "blocked",
            "event_id": "evt_existing",
        }
        metadata_patch = {
            "blocked_reason": "price_confirmation_failed",
            "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
            "metric_coverage_status": "full",
            "metric_missing_resolved": True,
            "event_type": "ActionExecuted",
            "action_state": "executed",
            "event_id": "evt_changed",
        }

        merged = merge_metadata_repair_payload(current_payload, metadata_patch)

        self.assertEqual(merged["blocked_reason"], "price_confirmation_failed")
        self.assertEqual(merged["metric_union_policy_version"], "n5.full_metric_union_historical_metadata_repair.v1")
        self.assertEqual(merged["metric_coverage_status"], "full")
        self.assertIs(merged["metric_missing_resolved"], True)
        self.assertEqual(merged["event_type"], "ActionBlocked")
        self.assertEqual(merged["action_state"], "blocked")
        self.assertEqual(merged["event_id"], "evt_existing")
        self.assertNotIn("event_type", ALLOWED_METADATA_REPAIR_KEYS)

    def test_payload_artifact_validator_rejects_forbidden_metadata_patch_keys(self) -> None:
        payload = sample_payload_artifact()
        payload["rows"][0]["metadata_patch"]["event_type"] = "ActionExecuted"

        with self.assertRaises(ValueError):
            validate_metadata_repair_payload_artifact(payload)

    def test_execute_command_contract_requires_artifact_paths_and_double_confirmation(self) -> None:
        command = build_full_metric_union_metadata_repair_command(
            dsn="postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3",
            contract_path="docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_CONTRACT.json",
            preflight_path="docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_PREFLIGHT.json",
            dry_run_path="docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_DRY_RUN.json",
            payload_path="docs/N5_full_metric_union_historical_metadata_repair_payload.json",
            rollback_sql_path="sql/N5_full_metric_union_historical_metadata_repair_20260605_rollback.sql",
            json_report_path="docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_REPORT.json",
            markdown_report_path="docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_REPORT.md",
        )

        joined = " ".join(command)
        self.assertEqual(command[:3], ["PYTHONPATH=src:scripts", "python3", "scripts/run_n5_full_metric_union_metadata_repair.py"])
        self.assertIn("--contract-path docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_CONTRACT.json", joined)
        self.assertIn("--preflight-path docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_PREFLIGHT.json", joined)
        self.assertIn("--dry-run-path docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_DRY_RUN.json", joined)
        self.assertIn("--payload-path docs/N5_full_metric_union_historical_metadata_repair_payload.json", joined)
        self.assertIn("--rollback-sql-path sql/N5_full_metric_union_historical_metadata_repair_20260605_rollback.sql", joined)
        self.assertEqual(command[-2:], ["--execute", "--user-confirmed"])


def sample_contract() -> dict:
    return {
        "result": "CONTRACT_PASS",
        "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "expected_old_new_comparison": {
            "scoped_n5_action_rows": 1,
            "unchanged_action_status": 1,
            "ActionExecuted_before_after": [1, 1],
            "ActionBlocked_before_after": [0, 0],
        },
    }


def sample_preflight() -> dict:
    return {
        "preflight_result": "PREFLIGHT_PASS",
        "action_run_id": sample_contract()["action_run_id"],
        "source_trigger_run_id": sample_contract()["source_trigger_run_id"],
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
    }


def sample_dry_run() -> dict:
    return {
        "result": "CONTRACT_PASS",
        "action_run_id": sample_contract()["action_run_id"],
        "source_trigger_run_id": sample_contract()["source_trigger_run_id"],
        "payload_repair_plan": {"planned_payload_update_rows": 1, "does_not_change_status": True},
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
    }


def sample_payload_artifact() -> dict:
    return {
        "result": "CONTRACT_PASS",
        "action_run_id": sample_contract()["action_run_id"],
        "source_trigger_run_id": sample_contract()["source_trigger_run_id"],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "payload_scope": {
            "rows": 1,
            "allowed_metadata_keys": list(ALLOWED_METADATA_REPAIR_KEYS),
        },
        "rows": [
            {
                "source_trigger_event_id": "evt_source",
                "common_action_event": {
                    "action_event_row_id": 1,
                    "event_id": "evt_action",
                    "current_event_type": "ActionBlocked",
                    "planned_event_type": "ActionBlocked",
                    "current_action_state": "blocked",
                    "planned_action_state": "blocked",
                    "current_confirmation_status": "failed",
                    "planned_confirmation_status": "failed",
                    "current_action_mark": None,
                    "planned_action_mark": None,
                    "current_blocked_reason": "metric_missing",
                    "planned_blocked_reason": "price_confirmation_failed",
                },
                "n5_common_event_outbox": {
                    "outbox_id": 10,
                    "event_id": "evt_action",
                    "status": "pending",
                    "current_blocked_reason": "metric_missing",
                    "planned_blocked_reason": "price_confirmation_failed",
                },
                "metadata_patch": {
                    "blocked_reason": "price_confirmation_failed",
                    "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
                    "metric_union_source_runs": ["metric_a", "metric_b"],
                    "action_confirmation_metric_run_refs": [],
                    "metric_coverage_status": "full",
                    "metric_missing_resolved": True,
                    "repair_trace": {"previous_blocked_reason": "metric_missing"},
                },
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
