from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import unittest

from ashare_v3.trigger.standard_trigger_execute import (
    DEFAULT_20260528_EXECUTE_RUN_ID,
    DEFAULT_20260528_TRIGGER_CONTEXT_RUN_ID,
    StandardTriggerExecuteError,
    assert_execute_confirmed,
    build_execute_state_changed_event_envelope,
    build_execute_contract_from_dry_run,
    build_execute_preflight,
    build_standard_trigger_execute_rollback_sql,
    insert_execute_quality_items,
    insert_execute_match,
    upsert_execute_state,
    json_safe,
)


def sample_dry_run_report() -> dict:
    return {
        "stage": "N4-20260528-local-trigger-dry-run",
        "result": "DRY_RUN_PASS",
        "layer_role": "N4_trigger",
        "trigger_context_run_id": DEFAULT_20260528_TRIGGER_CONTEXT_RUN_ID,
        "snapshot_run_id": "snapshot_run",
        "source_condition_run_id": "condition_run",
        "source_market_data_run_id": "snapshot_run",
        "for_trade_date": "20260528",
        "context_candidate_count": 4602,
        "candidate_count": 8887,
        "matched_plan_count": 4285,
        "pending_plan_count": 4602,
            "summary": {
                "candidate_count": 8887,
                "matched_plan_count": 4285,
                "pending_plan_count": 4602,
                "state_change_plan_count": 8887,
                "matched_by_signal_type": {"B_BUY": 2145, "S_SELL": 2140},
                "pending_by_signal_type": {"B_BUY": 2431, "S_SELL": 2171},
                "matched_by_trigger_mark_candidate": {"normal": 4285},
                "pending_by_trigger_mark_candidate": {"30m_volume": 2145, "30m_shrink": 2140, "normal": 317},
                "pending_by_legacy_signal_type": {
                    "B_BUY_30M_VOL": 2145,
                    "S_SELL_30M_SHRINK": 2140,
                "BUY_HINT": 286,
                "SELL_HINT": 31,
            },
                "planned_output_event_types": {
                    "TriggerMatched": 4285,
                    "TriggerPendingMarketData": 4602,
                    "TriggerStateChanged": 8887,
                },
                "canonical_payload_invalid_count": 0,
            },
        "quality": {
            "p0_count": 0,
            "p1_count": 2,
            "p2_count": 0,
            "p1_gate_codes": ["n4_20260528_b1_p1_carried", "n4_20260528_projection_candidates_pending"],
        },
        "scoped_event_refs": {
            "common_event_outbox": 0,
            "common_event_inbox": 0,
            "common_event_consumer_checkpoint": 0,
            "common_trigger_match": 0,
            "common_trigger_state": 0,
        },
        "sample_plans": [
            {
                "output_event_type": "TriggerMatched",
                "signal_type": "B_BUY",
                "trigger_mark_candidate": "normal",
                "condition_key": "B_BUY",
                "original_condition_key": "B_BUY",
                "legacy_signal_type": "B_BUY",
                "trigger_live": True,
                "previous_trigger_live": False,
                "current_status": "matched",
                "previous_status": "inactive",
                "primary_trigger_period": "D",
                "previous_primary_trigger_period": None,
                "all_trigger_periods": ["D"],
                "previous_all_trigger_periods": [],
                "state_change_reason": "activated",
            },
            {
                "output_event_type": "TriggerPendingMarketData",
                "signal_type": "B_BUY",
                "trigger_mark_candidate": "30m_volume",
                "condition_key": "B_BUY_30M_VOL",
                "original_condition_key": "B_BUY_30M_VOL",
                "legacy_signal_type": "B_BUY_30M_VOL",
                "trigger_live": False,
                "previous_trigger_live": False,
                "current_status": "pending_market_data",
                "previous_status": "inactive",
                "primary_trigger_period": "30m",
                "previous_primary_trigger_period": None,
                "all_trigger_periods": ["30m"],
                "previous_all_trigger_periods": [],
                "state_change_reason": "status_changed",
            },
        ],
    }


def clean_baseline() -> dict[str, int]:
    return {
        "execute_run_common_trigger_run": 0,
        "execute_run_quality": 0,
        "execute_run_match": 0,
        "execute_run_state": 0,
        "execute_run_outbox": 0,
        "execute_run_inbox": 0,
        "execute_run_checkpoint_refs": 0,
        "execute_run_outbox_delivered_or_delivering": 0,
        "downstream_inbox_for_execute_run": 0,
        "downstream_checkpoint_refs": 0,
        "snapshot_run_outbox": 0,
        "snapshot_run_outbox_allowed": 0,
        "snapshot_run_outbox_disallowed": 0,
        "snapshot_run_inbox": 0,
        "snapshot_run_checkpoint_refs": 0,
        "n5_action_run_refs": 0,
    }


class StandardTriggerExecuteTests(unittest.TestCase):
    def test_contract_uses_trigger_mark_candidate_and_marks_runner_ready_after_024(self) -> None:
        contract = build_execute_contract_from_dry_run(
            sample_dry_run_report(),
            execute_run_id=DEFAULT_20260528_EXECUTE_RUN_ID,
            market_subscription_run_id="market_data_subscription_20260528_test",
            dry_run_json_path="docs/test_dry_run.json",
        )

        self.assertEqual(contract["result"], "CONTRACT_PASS")
        self.assertTrue(contract["runner_readiness"]["ready"])
        self.assertEqual(contract["market_subscription_run_id"], "market_data_subscription_20260528_test")
        self.assertEqual(contract["runner_readiness"]["dry_run_alignment_source"], "docs/test_dry_run.json")
        self.assertEqual(contract["expected_writes"]["TriggerMatched"], 4285)
        self.assertEqual(contract["expected_writes"]["TriggerPendingMarketData"], 4602)
        self.assertEqual(contract["expected_writes"]["TriggerStateChanged"], 8887)
        self.assertEqual(contract["expected_writes"]["common_trigger_match"], 8887)
        self.assertEqual(contract["expected_writes"]["common_event_outbox"], 17774)
        self.assertEqual(contract["pending_by_signal_type"], {"B_BUY": 2431, "S_SELL": 2171})
        self.assertEqual(contract["pending_by_trigger_mark_candidate"]["30m_volume"], 2145)
        self.assertNotIn("B_BUY_30M_VOL", contract["pending_by_signal_type"])
        self.assertNotIn("S_SELL_30M_SHRINK", contract["pending_by_signal_type"])
        self.assertNotIn("BUY_HINT", contract["pending_by_signal_type"])
        self.assertNotIn("SELL_HINT", contract["pending_by_signal_type"])
        self.assertIn("original_condition_key", contract["canonical_payload_contract"]["required_trace_fields"])
        self.assertIn("trigger_mark_candidate", contract["canonical_payload_contract"]["required_runtime_fields"])
        self.assertFalse(contract["schema_compatibility"]["execute_blocked_until_schema_review"])

    def test_contract_does_not_inject_20260528_subscription_when_omitted(self) -> None:
        dry_run = sample_dry_run_report()
        dry_run["for_trade_date"] = "20260529"
        contract = build_execute_contract_from_dry_run(
            dry_run,
            execute_run_id="trigger_execute_20260529_test",
            trigger_context_run_id="trigger_context_snapshot_20260529_test",
            snapshot_run_id="realtime_snapshot_20260529_test",
            dry_run_json_path="docs/N4_20260529_LOCAL_TRIGGER_DRY_RUN_REPORT.json",
        )

        self.assertEqual(contract["for_trade_date"], "20260529")
        self.assertEqual(contract["market_subscription_run_id"], "")
        self.assertNotIn("20260528", contract["market_subscription_run_id"])
        self.assertEqual(
            contract["runner_readiness"]["dry_run_alignment_source"],
            "docs/N4_20260529_LOCAL_TRIGGER_DRY_RUN_REPORT.json",
        )

    def test_preflight_passes_after_schema_compatibility_and_keeps_execute_authorized_false(self) -> None:
        dry_run = sample_dry_run_report()
        contract = build_execute_contract_from_dry_run(dry_run)
        preflight = build_execute_preflight(
            dry_run_report=dry_run,
            contract=contract,
            baseline_summary=clean_baseline(),
            dry_run_json_path="docs/test_dry_run.json",
        )

        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["dry_run_basis"]["report_path"], "docs/test_dry_run.json")
        self.assertEqual(preflight["quality"]["p0_count"], 0)
        self.assertTrue(preflight["next_gate"]["allow_enter_n4_v2_execute_final_gate"])
        self.assertFalse(preflight["next_gate"]["execute_authorized"])
        self.assertTrue(preflight["next_gate"]["n5_remains_blocked"])
        self.assertFalse(preflight["side_effects"]["writes_performed"])
        self.assertFalse(preflight["side_effects"]["event_outbox_written"])
        self.assertNotIn("n4_v2_schema_compatibility_review_required", {item["gate_code"] for item in preflight["blockers"]})

    def test_preflight_allows_allowlisted_n3_input_outbox_for_live2(self) -> None:
        baseline = clean_baseline()
        baseline["snapshot_run_outbox"] = 2157
        baseline["snapshot_run_outbox_allowed"] = 2157
        dry_run = sample_dry_run_report()
        contract = build_execute_contract_from_dry_run(dry_run)
        preflight = build_execute_preflight(
            dry_run_report=dry_run,
            contract=contract,
            baseline_summary=baseline,
        )

        self.assertEqual(preflight["result"], "PREFLIGHT_PASS", preflight["quality_items"])
        self.assertEqual(preflight["upstream_input_refs"]["snapshot_run_outbox_allowed"], 2157)
        self.assertTrue(preflight["idempotency_gate"]["clean_target_execute_run"])

    def test_preflight_blocks_consumed_or_non_allowlisted_n3_input(self) -> None:
        baseline = clean_baseline()
        baseline["snapshot_run_outbox"] = 2157
        baseline["snapshot_run_outbox_allowed"] = 2156
        baseline["snapshot_run_outbox_disallowed"] = 1
        dry_run = sample_dry_run_report()
        contract = build_execute_contract_from_dry_run(dry_run)
        preflight = build_execute_preflight(
            dry_run_report=dry_run,
            contract=contract,
            baseline_summary=baseline,
        )

        self.assertEqual(preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertIn(
            "n4_v2_execute_upstream_input_refs_compatible",
            {item["gate_code"] for item in preflight["quality_items"] if item["status"] == "failed"},
        )

    def test_preflight_blocks_deprecated_runtime_signal_type(self) -> None:
        dry_run = sample_dry_run_report()
        dry_run["sample_plans"][0]["signal_type"] = "B_BUY_30M_VOL"
        contract = build_execute_contract_from_dry_run(dry_run)
        preflight = build_execute_preflight(
            dry_run_report=dry_run,
            contract=contract,
            baseline_summary=clean_baseline(),
        )

        self.assertEqual(preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertGreater(preflight["quality"]["p0_count"], 0)
        self.assertIn("n4_v2_deprecated_runtime_signal_type", {item["gate_code"] for item in preflight["quality_items"]})

    def test_preflight_blocks_nonzero_target_baseline(self) -> None:
        baseline = clean_baseline()
        baseline["execute_run_outbox"] = 1
        dry_run = sample_dry_run_report()
        contract = build_execute_contract_from_dry_run(dry_run)
        preflight = build_execute_preflight(
            dry_run_report=dry_run,
            contract=contract,
            baseline_summary=baseline,
        )

        self.assertEqual(preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertFalse(preflight["idempotency_gate"]["clean_target_execute_run"])

    def test_json_safe_converts_datetime_in_plan_trace(self) -> None:
        value = {"snapshot_trace": {"snapshot_time": datetime(2026, 5, 28, 9, 15, tzinfo=timezone.utc)}}
        converted = json_safe(value)

        json.dumps(converted)
        self.assertEqual(converted["snapshot_trace"]["snapshot_time"], "2026-05-28 09:15:00+00:00")

    def test_missing_execute_confirmation_blocks_before_writes(self) -> None:
        with self.assertRaises(StandardTriggerExecuteError):
            assert_execute_confirmed(execute=False, user_confirmed=True)
        with self.assertRaises(StandardTriggerExecuteError):
            assert_execute_confirmed(execute=True, user_confirmed=False)

    def test_quality_insert_uses_explicit_lineage_dates(self) -> None:
        cur = RecordingCursor({})
        inserted = insert_execute_quality_items(
            cur,
            execute_run_id="trigger_execute_20260529_test",
            source_condition_run_id="condition_layer_20260528_source_20260528_v1",
            for_trade_date="20260529",
            source_trade_date="20260528",
            items=[
                {
                    "gate_code": "gate",
                    "gate_name": "gate name",
                    "severity": "P0",
                    "status": "passed",
                }
            ],
        )

        self.assertEqual(inserted, 1)
        self.assertEqual(cur.last_many_params[0][2], "20260529")
        self.assertEqual(cur.last_many_params[0][3], "20260528")

    def test_rollback_sql_scopes_to_execute_run_id(self) -> None:
        rollback = build_standard_trigger_execute_rollback_sql("trigger_execute_20260529_test")
        executable = "\n".join(
            line for line in rollback.splitlines() if not line.lstrip().startswith("--")
        ).lower()

        self.assertIn("trigger_execute_20260529_test", rollback)
        self.assertIn("common_event_outbox", rollback)
        self.assertIn("common_trigger_match", rollback)
        self.assertIn("common_trigger_state", rollback)
        self.assertIn("common_action_run", rollback)
        self.assertIn("common_action_event", rollback)
        for table in (
            "user_projection_run",
            "user_signal_projection",
            "user_signal_card",
            "user_notification_queue",
        ):
            with self.subTest(table=table):
                self.assertIn(f"to_regclass('public.{table}')", rollback)
                self.assertIn(table, rollback)
                self.assertNotIn(f"delete from {table}", executable)
        self.assertLess(executable.index("raise exception"), executable.index("delete from"))

    def test_state_write_params_include_024_canonical_columns(self) -> None:
        cur = RecordingCursor({"trigger_state_id": 101})
        upsert_execute_state(
            cur,
            execute_run_id=DEFAULT_20260528_EXECUTE_RUN_ID,
            trigger_context_run=trigger_context_run(),
            plan=outcome_plan(),
        )

        sql = cur.last_sql
        params = cur.last_params
        for column in (
            "trigger_live",
            "trigger_mark_candidate",
            "primary_trigger_period",
            "all_trigger_periods",
            "projection_30m_flag",
            "projection_30m_type",
        ):
            self.assertIn(column, sql)
            self.assertIn(column, params)
        self.assertTrue(params["trigger_live"])
        self.assertEqual(params["trigger_mark_candidate"], "normal")

    def test_match_write_params_include_trigger_mark_candidate_and_only_outcome(self) -> None:
        cur = RecordingCursor({"trigger_match_id": 202})
        insert_execute_match(
            cur,
            execute_run_id=DEFAULT_20260528_EXECUTE_RUN_ID,
            trigger_context_run=trigger_context_run(),
            plan=outcome_plan(),
            trigger_state_id=101,
            dedup_key="dedup-outcome",
            output_event_id="evt_outcome",
        )

        self.assertIn("trigger_mark_candidate", cur.last_sql)
        self.assertEqual(cur.last_params["trigger_mark_candidate"], "normal")
        self.assertIn(cur.last_params["output_event_type"], {"TriggerMatched", "TriggerPendingMarketData"})

    def test_match_raw_json_mirrors_v4_required_fields_at_top_level(self) -> None:
        cur = RecordingCursor({"trigger_match_id": 202})
        plan = {
            **outcome_plan(),
            "trigger_kind": "trigger",
            "triggered_periods": ["D"],
            "n5_entry_allowed": True,
            "match_basis": "realtime_snapshot",
        }

        insert_execute_match(
            cur,
            execute_run_id=DEFAULT_20260528_EXECUTE_RUN_ID,
            trigger_context_run=trigger_context_run(),
            plan=plan,
            trigger_state_id=101,
            dedup_key="dedup-outcome",
            output_event_id="evt_outcome",
        )

        raw_json = cur.last_params["raw_json"].obj
        for key in (
            "trigger_kind",
            "triggered_periods",
            "all_trigger_periods",
            "primary_trigger_period",
            "trigger_live",
            "current_status",
            "n5_entry_allowed",
            "match_basis",
        ):
            with self.subTest(key=key):
                self.assertIn(key, raw_json)
        self.assertEqual(raw_json["trigger_kind"], "trigger")
        self.assertEqual(raw_json["triggered_periods"], ["D"])
        self.assertEqual(raw_json["all_trigger_periods"], ["D"])
        self.assertEqual(raw_json["primary_trigger_period"], "D")
        self.assertTrue(raw_json["trigger_live"])
        self.assertEqual(raw_json["current_status"], "matched")
        self.assertTrue(raw_json["n5_entry_allowed"])
        self.assertEqual(raw_json["match_basis"], "realtime_snapshot")

    def test_build_trigger_state_changed_execute_envelope_contains_required_payload(self) -> None:
        envelope = build_execute_state_changed_event_envelope(
            execute_run_id=DEFAULT_20260528_EXECUTE_RUN_ID,
            trigger_context_run=trigger_context_run(),
            plan=state_change_plan(),
            source_outcome_event_id="evt_outcome",
        )

        self.assertEqual(envelope.event_type, "TriggerStateChanged")
        self.assertEqual(envelope.payload_json["source_event_id"], "evt_outcome")
        self.assertEqual(envelope.payload_json["source_outcome_event_id"], "evt_outcome")
        self.assertFalse(envelope.payload_json["previous_trigger_live"])
        self.assertTrue(envelope.payload_json["trigger_live"])
        self.assertEqual(envelope.payload_json["current_status"], "matched")


if __name__ == "__main__":
    unittest.main()


class RecordingCursor:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.last_sql = ""
        self.last_params: dict[str, object] = {}
        self.last_many_params: list[tuple[object, ...]] = []

    def execute(self, sql: str, params: dict[str, object] | tuple[object, ...]) -> None:
        self.last_sql = sql
        self.last_params = params if isinstance(params, dict) else {}

    def executemany(self, sql: str, params: list[tuple[object, ...]]) -> None:
        self.last_sql = sql
        self.last_many_params = params

    def fetchone(self) -> dict[str, object]:
        return self.row


def trigger_context_run() -> dict[str, object]:
    return {
        "run_id": DEFAULT_20260528_TRIGGER_CONTEXT_RUN_ID,
        "source_condition_run_id": "condition_layer_20260527_source_20260527_v2",
        "for_trade_date": "20260528",
        "source_trade_date": "20260527",
        "prev_trade_date": "20260527",
    }


def outcome_plan() -> dict[str, object]:
    return {
        "plan_id": "plan-matched-1",
        "output_event_type": "TriggerMatched",
        "source_event_id": "evt_b1_snapshot",
        "source_event_type": "MarketSnapshotUpdated",
        "source_snapshot_run_id": "snapshot_run",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": "BUY_HINT",
        "original_condition_key": "BUY_HINT",
        "legacy_signal_type": "BUY_HINT",
        "trigger_mark_candidate": "normal",
        "match_basis": "realtime_snapshot",
        "trigger_period": "D",
        "trigger_bucket": "trading_day",
        "trigger_live": True,
        "current_status": "matched",
        "primary_trigger_period": "D",
        "all_trigger_periods": ["D"],
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "data_quality_status": "passed",
        "context_hash": "context-hash",
        "snapshot_trace": {"snapshot_time": "2026-05-28T09:30:00+08:00"},
    }


def state_change_plan() -> dict[str, object]:
    return {
        **outcome_plan(),
        "output_event_type": "TriggerStateChanged",
        "previous_trigger_live": False,
        "previous_status": "inactive",
        "previous_primary_trigger_period": None,
        "previous_all_trigger_periods": [],
        "previous_projection_30m_flag": False,
        "previous_projection_30m_type": "none",
        "previous_trigger_mark_candidate": None,
        "state_change_reason": "activated",
        "source_outcome_event_type": "TriggerMatched",
        "source_outcome_event_id": None,
    }
