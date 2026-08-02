from copy import deepcopy
import hashlib
import json
import unittest
from pathlib import Path

from ashare_v3.action import live_tracking_poller as poller
from ashare_v3.events.models import (
    EventContractError,
    N5_EVENT_TYPES,
    N5_TRIGGER_STATUS_MESSAGE_TYPES,
    validate_event_envelope,
)
import run_n5_trigger_status_forward_once as status_runner


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "N5_N6_TRIGGER_STATUS_FORWARD_CONTRACT_V1.md"
STATE_FLOW = ROOT / "docs" / "N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md"
ACTION_FLOW = ROOT / "docs" / "N5_CANONICAL_ACTION_FLOW_v0.1.md"
ARCHITECTURE = ROOT / "docs" / "Architecture.md"
TASKS = ROOT / "docs" / "Tasks.md"
GOVERNANCE = ROOT / "docs" / "N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json"
N6_PROJECTION = ROOT / "src" / "ashare_v3" / "user" / "projection_plan.py"
ROLLBACK = ROOT / "sql" / "N5_trigger_status_forward_only_rollback.sql"
TRADE_DATE = "20260731"
SOURCE_TRIGGER_RUN_ID = "trigger_status_forward_n4_20260731_v1"
SOURCE_ELIGIBLE_ACTION_RUN_ID = "n5_live_tracking_20260731__active_set_a__fastlane_v1"
ACTION_RUN_ID = "trigger_status_forward_n5_20260731_v1"
CONSUMER_NAME = "n5_trigger_status_forward_v1"


def action_eligible(
    *,
    event_id: str = "n5-eligible-1",
    entry_event_id: str = "n4-entry-1",
    event_time: str = "2026-07-31T09:31:00+08:00",
    condition_key: str = "BUY:W",
    close: str = "10",
    source_action_run_id: str = "entry_action_run",
    source_trigger_run_id: str = SOURCE_TRIGGER_RUN_ID,
) -> dict:
    signal_type = "B_BUY"
    direction = "buy"
    grain = {
        "trade_date": TRADE_DATE,
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
    }
    state_key = poller.build_action_tracking_state_key(**grain)
    return {
        "event_id": event_id,
        "event_type": "ActionEligible",
        "event_time": event_time,
        "trade_date": TRADE_DATE,
        "asset_kind": "stock",
        "identity_key": grain["identity_key"],
        "source_layer": "N5_action",
        "source_run_id": source_action_run_id,
        "payload_json": {
            **grain,
            "action_state": "eligible",
            "data_quality_status": "passed",
            "projection_message_status": "ready",
            "action_key": state_key,
            "asset_code": "600000",
            "asset_name": "浦发银行",
            "trigger_time": event_time,
            "trigger_price": "10.100000",
            "trigger_pct": "1.000000",
            "source_trigger_event_id": entry_event_id,
            "trace_json": {"tracking_state_key": state_key},
            "action_entry_trigger_matched_ref": {
                "source_trigger_event_id": entry_event_id,
                "source_trigger_event_type": "TriggerMatched",
                "source_trigger_event_time": event_time,
                "source_trigger_run_id": source_trigger_run_id,
                "source_n4_payload": {
                    **grain,
                    "trigger_live": True,
                    "current_status": "matched",
                    "condition_projection_context": {"fields": {"close": close}},
                },
            },
        },
    }


def trigger_state_changed(
    *,
    event_id: str,
    event_time: str,
    trigger_live: bool,
    condition_key: str = "BUY:W",
    trigger_price: str = "10.55555555",
    source_trigger_run_id: str = SOURCE_TRIGGER_RUN_ID,
) -> dict:
    return {
        "event_id": event_id,
        "event_type": "TriggerStateChanged",
        "event_time": event_time,
        "trade_date": TRADE_DATE,
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "source_layer": "N4_trigger",
        "source_run_id": source_trigger_run_id,
        "status": "pending",
        "payload_json": {
            "trade_date": TRADE_DATE,
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "direction": "buy",
            "signal_type": "B_BUY",
            "condition_key": condition_key,
            "trigger_live": trigger_live,
            "current_status": "matched" if trigger_live else "inactive",
            "trigger_price": trigger_price,
            "trigger_period": "30m" if "HINT" in condition_key else "W",
            "triggered_periods": ["30m"] if "HINT" in condition_key else ["W"],
        },
    }


def status_plan(n4_rows, eligible_rows, **kwargs):
    source_trigger_run_id = kwargs.pop("source_trigger_run_id", SOURCE_TRIGGER_RUN_ID)
    source_eligible_action_run_id = kwargs.pop("source_eligible_action_run_id", "")
    return poller.build_trigger_status_forward_plan(
        n4_event_rows=n4_rows,
        action_eligible_event_rows=eligible_rows,
        action_run_id=kwargs.pop("action_run_id", ACTION_RUN_ID),
        source_trigger_run_id=source_trigger_run_id,
        source_eligible_action_run_id=source_eligible_action_run_id,
        scope_mode=kwargs.pop("scope_mode", ""),
        consumer_name=CONSUMER_NAME,
        for_trade_date=TRADE_DATE,
        **kwargs,
    )


def aggregate_status_plan(n4_rows, eligible_rows, **kwargs):
    return status_plan(
        n4_rows,
        eligible_rows,
        source_trigger_run_id="",
        source_eligible_action_run_id=SOURCE_ELIGIBLE_ACTION_RUN_ID,
        scope_mode="aggregate_day_action_run",
        **kwargs,
    )


class TriggerStatusForwardContractTests(unittest.TestCase):
    def test_trigger_status_contract_is_l2_without_one_off_policy(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        governance = GOVERNANCE.read_text(encoding="utf-8")

        self.assertIn("contract_version = N5-N6-trigger-status-forward-v1", text)
        self.assertIn("delivery_lane = n6_btrack_delivery_l2_n6_business_v1", text)
        self.assertIn("It does not create a one-off runtime policy", text)
        self.assertIn('"policy_id": "n6_btrack_delivery_l2_n6_business_v1"', governance)
        self.assertNotIn("n6_trigger_status_current_projection_bounded_run_once_v1", text)

    def test_status_messages_are_non_action_and_keep_action_outcomes_closed(self) -> None:
        contract = CONTRACT.read_text(encoding="utf-8")
        state_flow = STATE_FLOW.read_text(encoding="utf-8")
        action_flow = ACTION_FLOW.read_text(encoding="utf-8")

        for event_type in ("TriggerStatusUpdated", "TriggerStatusInvalidated"):
            self.assertIn(event_type, contract)
            self.assertIn(event_type, state_flow)
            self.assertIn(event_type, action_flow)

        for event_type in (
            "ActionEligible",
            "ActionBlocked",
            "ActionExecuted",
            "ActionSkipped",
        ):
            self.assertIn(event_type, contract)
            self.assertIn(event_type, action_flow)

        for marker in (
            "source_layer = N5_action",
            "message_role = n6_trigger_status_projection_only",
            "action_eligible_entry_allowed = false",
            "They must not write\n`common_action_event`",
            "enter the existing N6 signal/message/card projection consumer",
        ):
            self.assertIn(marker, contract)

    def test_status_payload_and_lifecycle_are_decision_complete(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        for field in (
            "contract_version",
            "operation",
            "trade_date",
            "tracking_state_key",
            "entry_trigger_event_id",
            "action_eligible_event_id",
            "source_trigger_event_id",
            "asset_kind",
            "identity_key",
            "asset_code",
            "asset_name",
            "direction",
            "signal_type",
            "condition_key",
            "trigger_time",
            "trigger_price",
            "trigger_pct",
            "trigger_period",
            "triggered_periods",
            "trigger_live",
            "current_status",
        ):
            self.assertIn(field, text)

        for rule in (
            "ActionEligible -> idempotent insert",
            "TriggerStatusUpdated -> update trigger_pct, trigger_price, trigger_period,",
            "TriggerStatusInvalidated -> delete the exact episode; missing delete is idempotent",
            "missing update target -> fail closed; do not advance inbox/checkpoint",
            "ActionExecuted -> no current-trigger-status mutation",
            "asset_kind + identity_key + direction",
        ):
            self.assertIn(rule, text)

    def test_architecture_and_tasks_register_the_isolated_status_branch(self) -> None:
        architecture = ARCHITECTURE.read_text(encoding="utf-8")
        tasks = TASKS.read_text(encoding="utf-8")

        self.assertIn(
            "n6_trigger_status_current (isolated L2 current-state read model)",
            architecture,
        )
        self.assertIn("T0.N5-N6-TRIGGER-STATUS", tasks)
        self.assertIn("N5_action 独立实现/离线测试", tasks)
        self.assertIn("N6_user 独立实现/PG16 测试", tasks)
        self.assertIn("首版禁止 scheduler、LaunchAgent、SSE、worker", tasks)

    def test_true_state_change_builds_current_update_from_frozen_entry_close(self) -> None:
        eligible = action_eligible()
        row = trigger_state_changed(
            event_id="n4-tsc-true",
            event_time="2026-07-31T09:35:00+08:00",
            trigger_live=True,
        )

        plan = status_plan([row], [eligible])

        self.assertEqual([event["event_type"] for event in plan["status_events"]], ["TriggerStatusUpdated"])
        payload = plan["status_events"][0]["payload_json"]
        self.assertEqual(payload["operation"], "update")
        self.assertEqual(payload["trigger_pct"], "5.555556")
        self.assertEqual(payload["entry_trigger_event_id"], "n4-entry-1")
        self.assertEqual(payload["trigger_time"], "2026-07-31T09:31:00+08:00")
        self.assertEqual(payload["source_trigger_event_time"], "2026-07-31T09:35:00+08:00")
        self.assertFalse(payload["action_eligible_entry_allowed"])

    def test_false_state_change_invalidates_eligible_and_executed_tracking(self) -> None:
        row = trigger_state_changed(
            event_id="n4-tsc-false",
            event_time="2026-07-31T09:40:00+08:00",
            trigger_live=False,
        )
        for later_tracking_status in ("eligible", "executed"):
            with self.subTest(later_tracking_status=later_tracking_status):
                eligible = action_eligible()
                action_history = [eligible]
                if later_tracking_status == "executed":
                    executed = deepcopy(eligible)
                    executed["event_id"] = "n5-executed-1"
                    executed["event_type"] = "ActionExecuted"
                    executed["payload_json"]["action_state"] = "executed"
                    action_history.append(executed)
                plan = status_plan([row], action_history)
                self.assertEqual(
                    [event["event_type"] for event in plan["status_events"]],
                    ["TriggerStatusInvalidated"],
                )
                self.assertEqual(plan["status_events"][0]["payload_json"]["operation"], "invalidate")

    def test_aggregate_day_replay_chains_mixed_n4_source_runs_and_reports_census(self) -> None:
        eligible = action_eligible(source_action_run_id=SOURCE_ELIGIBLE_ACTION_RUN_ID)
        rows = [
            trigger_state_changed(
                event_id="n4-mixed-true",
                event_time="2026-07-31T09:35:00+08:00",
                trigger_live=True,
                source_trigger_run_id="n4-minute-run-0935",
            ),
            trigger_state_changed(
                event_id="n4-mixed-false",
                event_time="2026-07-31T09:40:00+08:00",
                trigger_live=False,
                source_trigger_run_id="n4-minute-run-0940",
            ),
        ]

        plan = aggregate_status_plan(rows, [eligible])

        self.assertEqual(
            [event["event_type"] for event in plan["status_events"]],
            ["TriggerStatusUpdated", "TriggerStatusInvalidated"],
        )
        self.assertEqual(
            [event["payload_json"]["source_trigger_run_id"] for event in plan["status_events"]],
            ["n4-minute-run-0935", "n4-minute-run-0940"],
        )
        self.assertEqual(plan["scope_mode"], "aggregate_day_action_run")
        self.assertEqual(plan["source_eligible_action_run_id"], SOURCE_ELIGIBLE_ACTION_RUN_ID)
        self.assertEqual(plan["source_trigger_run_count"], 2)
        self.assertEqual(plan["source_trigger_run_ids"], ["n4-minute-run-0935", "n4-minute-run-0940"])
        expected_hash = hashlib.sha256(
            json.dumps(plan["source_trigger_run_ids"], separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(plan["source_trigger_run_ids_hash"], expected_hash)
        self.assertEqual(plan["summary"]["action_eligible_count"], 1)

    def test_aggregate_false_then_new_verified_episode_does_not_revive_old_episode(self) -> None:
        old = action_eligible(source_action_run_id=SOURCE_ELIGIBLE_ACTION_RUN_ID)
        new = action_eligible(
            event_id="n5-eligible-new",
            entry_event_id="n4-entry-new",
            event_time="2026-07-31T10:00:00+08:00",
            source_action_run_id=SOURCE_ELIGIBLE_ACTION_RUN_ID,
            source_trigger_run_id="n4-match-run-1000",
        )
        rows = [
            trigger_state_changed(
                event_id="n4-old-false-mixed",
                event_time="2026-07-31T09:45:00+08:00",
                trigger_live=False,
                source_trigger_run_id="n4-minute-run-0945",
            ),
            trigger_state_changed(
                event_id="n4-old-true-after-false-mixed",
                event_time="2026-07-31T09:50:00+08:00",
                trigger_live=True,
                source_trigger_run_id="n4-minute-run-0950",
            ),
            trigger_state_changed(
                event_id="n4-new-true-mixed",
                event_time="2026-07-31T10:05:00+08:00",
                trigger_live=True,
                source_trigger_run_id="n4-minute-run-1005",
            ),
        ]

        plan = aggregate_status_plan(rows, [old, new])

        self.assertEqual(
            [event["event_type"] for event in plan["status_events"]],
            ["TriggerStatusInvalidated", "TriggerStatusUpdated"],
        )
        self.assertEqual(plan["status_events"][1]["payload_json"]["entry_trigger_event_id"], "n4-entry-new")
        self.assertEqual(plan["summary"]["missing_verified_entry_count"], 1)

    def test_aggregate_exact_source_action_run_excludes_other_eligible_run(self) -> None:
        exact = action_eligible(source_action_run_id=SOURCE_ELIGIBLE_ACTION_RUN_ID)
        other = action_eligible(
            event_id="n5-other-run-eligible",
            entry_event_id="n4-other-run-entry",
            event_time="2026-07-31T10:00:00+08:00",
            source_action_run_id="other-n5-action-run",
        )
        rows = [
            trigger_state_changed(
                event_id="n4-exact-false",
                event_time="2026-07-31T09:45:00+08:00",
                trigger_live=False,
                source_trigger_run_id="n4-minute-run-0945",
            ),
            trigger_state_changed(
                event_id="n4-other-true",
                event_time="2026-07-31T10:05:00+08:00",
                trigger_live=True,
                source_trigger_run_id="n4-minute-run-1005",
            ),
        ]

        plan = aggregate_status_plan(rows, [exact, other])

        self.assertEqual(
            [event["event_type"] for event in plan["status_events"]],
            ["TriggerStatusInvalidated"],
        )
        self.assertEqual(plan["summary"]["action_eligible_count"], 1)
        self.assertEqual(plan["summary"]["rejected_action_eligible_count"], 1)
        self.assertEqual(plan["summary"]["missing_verified_entry_count"], 1)

    def test_missing_verified_trigger_matched_entry_does_not_forward(self) -> None:
        eligible = action_eligible()
        eligible["payload_json"].pop("action_entry_trigger_matched_ref")
        row = trigger_state_changed(
            event_id="n4-tsc-no-entry",
            event_time="2026-07-31T09:35:00+08:00",
            trigger_live=True,
        )

        plan = status_plan([row], [eligible])

        self.assertEqual(plan["status_events"], [])
        self.assertEqual(plan["summary"]["rejected_action_eligible_count"], 1)
        self.assertEqual(plan["summary"]["missing_verified_entry_count"], 1)

    def test_replay_is_idempotent_and_event_id_depends_on_required_tuple(self) -> None:
        eligible = action_eligible()
        row = trigger_state_changed(
            event_id="n4-tsc-replay",
            event_time="2026-07-31T09:35:00+08:00",
            trigger_live=True,
        )
        first = status_plan([row], [eligible])
        different_run = status_plan([row], [eligible], action_run_id="different-status-forward-run")
        replay = status_plan(
            [row],
            [eligible],
            existing_status_event_keys={first["status_events"][0]["event_key"]},
        )

        self.assertEqual(first["status_events"][0]["event_id"], different_run["status_events"][0]["event_id"])
        self.assertEqual(replay["status_events"], [])
        self.assertEqual(replay["summary"]["replay_skipped_count"], 1)

    def test_aggregate_replay_is_idempotent_across_status_forward_run_ids(self) -> None:
        eligible = action_eligible(source_action_run_id=SOURCE_ELIGIBLE_ACTION_RUN_ID)
        row = trigger_state_changed(
            event_id="n4-aggregate-replay",
            event_time="2026-07-31T09:35:00+08:00",
            trigger_live=True,
            source_trigger_run_id="n4-minute-run-0935",
        )
        first = aggregate_status_plan([row], [eligible])
        replay = aggregate_status_plan(
            [row],
            [eligible],
            action_run_id="different-status-forward-run",
            existing_status_event_keys={first["status_events"][0]["event_key"]},
        )

        self.assertEqual(replay["status_events"], [])
        self.assertEqual(replay["summary"]["replay_skipped_count"], 1)

    def test_false_closes_only_old_episode_and_new_entry_can_forward(self) -> None:
        old = action_eligible()
        new = action_eligible(
            event_id="n5-eligible-2",
            entry_event_id="n4-entry-2",
            event_time="2026-07-31T10:00:00+08:00",
        )
        rows = [
            trigger_state_changed(
                event_id="n4-old-false",
                event_time="2026-07-31T09:45:00+08:00",
                trigger_live=False,
            ),
            trigger_state_changed(
                event_id="n4-old-after-false",
                event_time="2026-07-31T09:50:00+08:00",
                trigger_live=True,
            ),
            trigger_state_changed(
                event_id="n4-new-true",
                event_time="2026-07-31T10:05:00+08:00",
                trigger_live=True,
            ),
        ]

        plan = status_plan(rows, [old, new])

        self.assertEqual(
            [event["event_type"] for event in plan["status_events"]],
            ["TriggerStatusInvalidated", "TriggerStatusUpdated"],
        )
        self.assertEqual(plan["status_events"][1]["payload_json"]["entry_trigger_event_id"], "n4-entry-2")

    def test_status_update_does_not_mutate_immutable_action_snapshot(self) -> None:
        eligible = action_eligible()
        row = trigger_state_changed(
            event_id="n4-tsc-immutable",
            event_time="2026-07-31T09:35:00+08:00",
            trigger_live=True,
            trigger_price="12",
        )
        frozen_eligible = deepcopy(eligible)
        frozen_row = deepcopy(row)

        plan = status_plan([row], [eligible])

        self.assertEqual(eligible, frozen_eligible)
        self.assertEqual(row, frozen_row)
        self.assertEqual(eligible["payload_json"]["trigger_pct"], "1.000000")
        self.assertEqual(plan["status_events"][0]["payload_json"]["trigger_pct"], "20.000000")

    def test_hint_public_period_does_not_leak_internal_30m_list(self) -> None:
        eligible = action_eligible(condition_key="BUY_HINT")
        row = trigger_state_changed(
            event_id="n4-hint-true",
            event_time="2026-07-31T09:35:00+08:00",
            trigger_live=True,
            condition_key="BUY_HINT",
        )

        payload = status_plan([row], [eligible])["status_events"][0]["payload_json"]

        self.assertEqual(payload["trigger_period"], "30m")
        self.assertEqual(payload["triggered_periods"], [])

    def test_status_only_plan_keeps_action_contract_and_persistence_closed(self) -> None:
        row = trigger_state_changed(
            event_id="n4-tsc-only",
            event_time="2026-07-31T09:35:00+08:00",
            trigger_live=True,
        )
        plan = status_plan([row], [action_eligible()])
        n6_projection = N6_PROJECTION.read_text(encoding="utf-8")

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(
            plan["summary"]["canonical_action_outcome_event_types"],
            ["ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"],
        )
        self.assertEqual(plan["persistence"]["allowed_targets"], ["common_event_outbox"])
        self.assertFalse(plan["persistence"]["common_action_event_write_allowed"])
        self.assertIn(
            'CANONICAL_EVENT_TYPES = ("ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped")',
            n6_projection,
        )

    def test_rollback_draft_is_exact_status_outbox_only(self) -> None:
        text = ROLLBACK.read_text(encoding="utf-8")
        for marker in (
            "TriggerStatusUpdated",
            "TriggerStatusInvalidated",
            "N5-N6-trigger-status-forward-v1",
            "n6_trigger_status_projection_only",
            "n5.rollback_action_run_id",
            "n5.rollback_source_trigger_run_id",
            "n5.rollback_consumer_name",
            "DELETE FROM common_event_outbox",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("DELETE FROM common_action_event", text)
        self.assertNotIn("UPDATE common_event_outbox", text)

    def test_event_envelope_accepts_only_valid_non_action_status_messages(self) -> None:
        rows = [
            trigger_state_changed(
                event_id="n4-model-true",
                event_time="2026-07-31T09:35:00+08:00",
                trigger_live=True,
            ),
            trigger_state_changed(
                event_id="n4-model-false",
                event_time="2026-07-31T09:40:00+08:00",
                trigger_live=False,
            ),
        ]
        events = status_plan(rows, [action_eligible()])["status_events"]

        self.assertEqual(
            N5_EVENT_TYPES,
            ("ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"),
        )
        self.assertEqual(
            N5_TRIGGER_STATUS_MESSAGE_TYPES,
            ("TriggerStatusUpdated", "TriggerStatusInvalidated"),
        )
        for event in events:
            validate_event_envelope(status_runner._event_envelope(event))

    def test_event_envelope_rejects_action_fields_and_operation_mismatch(self) -> None:
        row = trigger_state_changed(
            event_id="n4-model-invalid",
            event_time="2026-07-31T09:35:00+08:00",
            trigger_live=True,
        )
        event = status_plan([row], [action_eligible()])["status_events"][0]

        action_pollution = deepcopy(event)
        action_pollution["payload_json"]["action_state"] = "eligible"
        with self.assertRaisesRegex(EventContractError, "must not include action fields"):
            validate_event_envelope(status_runner._event_envelope(action_pollution))

        operation_mismatch = deepcopy(event)
        operation_mismatch["payload_json"]["operation"] = "invalidate"
        with self.assertRaisesRegex(EventContractError, "operation mismatch"):
            validate_event_envelope(status_runner._event_envelope(operation_mismatch))

    def test_runner_plan_only_is_zero_write(self) -> None:
        plan = status_plan(
            [
                trigger_state_changed(
                    event_id="n4-runner-plan",
                    event_time="2026-07-31T09:35:00+08:00",
                    trigger_live=True,
                )
            ],
            [action_eligible()],
        )
        writer_calls = []

        result = status_runner.run_n5_trigger_status_forward_once(
            self._runner_args(),
            plan_provider=lambda _args: plan,
            writer=lambda _args, events: writer_calls.append(events),
        )

        self.assertEqual(result["verdict"], "N5_TRIGGER_STATUS_FORWARD_PLAN_ONLY")
        self.assertEqual(result["scope_mode"], "single_source_trigger_run")
        self.assertEqual(result["source_trigger_run_id"], SOURCE_TRIGGER_RUN_ID)
        self.assertEqual(result["source_eligible_action_run_id"], "")
        self.assertEqual(result["write_result"]["common_event_outbox"], 0)
        self.assertEqual(result["write_result"]["common_action_event"], 0)
        self.assertEqual(writer_calls, [])

    def test_runner_aggregate_plan_reports_authority_census_and_zero_effects(self) -> None:
        plan = aggregate_status_plan(
            [
                trigger_state_changed(
                    event_id="n4-runner-aggregate",
                    event_time="2026-07-31T09:35:00+08:00",
                    trigger_live=True,
                    source_trigger_run_id="n4-minute-run-0935",
                )
            ],
            [action_eligible(source_action_run_id=SOURCE_ELIGIBLE_ACTION_RUN_ID)],
        )

        result = status_runner.run_n5_trigger_status_forward_once(
            self._aggregate_runner_args(),
            plan_provider=lambda _args: plan,
        )

        self.assertEqual(result["verdict"], "N5_TRIGGER_STATUS_FORWARD_PLAN_ONLY")
        self.assertEqual(result["scope_mode"], "aggregate_day_action_run")
        self.assertEqual(result["source_eligible_action_run_id"], SOURCE_ELIGIBLE_ACTION_RUN_ID)
        self.assertEqual(result["source_trigger_run_count"], 1)
        self.assertEqual(result["action_eligible_count"], 1)
        self.assertEqual(result["write_result"]["common_action_event"], 0)
        self.assertEqual(result["write_result"]["common_action_tracking_state"], 0)
        self.assertEqual(result["write_result"]["common_event_inbox"], 0)
        self.assertEqual(result["write_result"]["common_event_consumer_checkpoint"], 0)

    def test_runner_source_authorities_are_xor_and_missing_authority_fails_closed(self) -> None:
        provider_calls = []
        missing = status_runner.run_n5_trigger_status_forward_once(
            [
                "--for-trade-date",
                TRADE_DATE,
                "--action-run-id",
                ACTION_RUN_ID,
                "--consumer-name",
                CONSUMER_NAME,
            ],
            plan_provider=lambda _args: provider_calls.append("missing"),
        )
        both = status_runner.run_n5_trigger_status_forward_once(
            [*self._aggregate_runner_args(), "--source-trigger-run-id", SOURCE_TRIGGER_RUN_ID],
            plan_provider=lambda _args: provider_calls.append("both"),
        )

        self.assertEqual(missing["blocked_reason"], "exactly_one_source_authority_required")
        self.assertEqual(both["blocked_reason"], "exactly_one_source_authority_required")
        self.assertEqual(provider_calls, [])

    def test_runner_aggregate_rejects_nonexistent_action_eligible_authority(self) -> None:
        empty_plan = aggregate_status_plan([], [])

        result = status_runner.run_n5_trigger_status_forward_once(
            self._aggregate_runner_args(),
            plan_provider=lambda _args: empty_plan,
        )

        self.assertEqual(result["verdict"], "BLOCKED_N5_TRIGGER_STATUS_FORWARD")
        self.assertEqual(
            result["blocked_reason"],
            "source_eligible_action_run_has_no_action_eligible",
        )

    def test_aggregate_sql_scope_reads_day_n4_exact_action_run_and_day_dedup(self) -> None:
        class RecordingCursor:
            def __init__(self):
                self.calls = []

            def execute(self, query, params):
                self.calls.append((" ".join(query.split()), params))

            def fetchall(self):
                return []

        args = status_runner.build_arg_parser().parse_args(self._aggregate_runner_args())
        cursor = RecordingCursor()

        status_runner._fetch_n4_lifecycle_rows(cursor, args, limit=101)
        status_runner._fetch_action_eligible_rows(cursor, args, limit=101)
        status_runner._fetch_existing_status_event_keys(cursor, args, limit=101)

        n4_query, n4_params = cursor.calls[0]
        eligible_query, eligible_params = cursor.calls[1]
        dedup_query, dedup_params = cursor.calls[2]
        self.assertNotIn("AND source_run_id = %s", n4_query)
        self.assertEqual(n4_params, (TRADE_DATE, 101))
        self.assertIn("AND source_run_id = %s", eligible_query)
        self.assertEqual(eligible_params, (TRADE_DATE, SOURCE_ELIGIBLE_ACTION_RUN_ID, 101))
        self.assertNotIn("payload_json ->> 'source_trigger_run_id'", dedup_query)
        self.assertIn("event_type = ANY(%s)", dedup_query)
        self.assertEqual(dedup_params, (TRADE_DATE, list(N5_TRIGGER_STATUS_MESSAGE_TYPES), 101))

    def test_runner_execute_without_confirmation_is_blocked_before_provider_or_writer(self) -> None:
        calls = []
        result = status_runner.run_n5_trigger_status_forward_once(
            self._runner_args("--execute"),
            plan_provider=lambda _args: calls.append("provider"),
            writer=lambda _args, _events: calls.append("writer"),
        )

        self.assertEqual(result["verdict"], "BLOCKED_N5_TRIGGER_STATUS_FORWARD")
        self.assertEqual(result["blocked_reason"], "execute_requires_user_confirmed")
        self.assertEqual(calls, [])

    def test_runner_fake_writer_receives_only_two_status_message_types(self) -> None:
        plan = status_plan(
            [
                trigger_state_changed(
                    event_id="n4-runner-true",
                    event_time="2026-07-31T09:35:00+08:00",
                    trigger_live=True,
                ),
                trigger_state_changed(
                    event_id="n4-runner-false",
                    event_time="2026-07-31T09:40:00+08:00",
                    trigger_live=False,
                ),
            ],
            [action_eligible()],
        )
        captured = []

        def fake_writer(_args, events):
            captured.extend(deepcopy(list(events)))
            return {
                **status_runner._zero_write_result(),
                "executed": True,
                "common_event_outbox": len(events),
            }

        result = status_runner.run_n5_trigger_status_forward_once(
            self._runner_args("--execute", "--user-confirmed"),
            plan_provider=lambda _args: plan,
            writer=fake_writer,
        )

        self.assertEqual(result["verdict"], "N5_TRIGGER_STATUS_FORWARD_EXECUTE_PASS")
        self.assertEqual(
            [event["event_type"] for event in captured],
            ["TriggerStatusUpdated", "TriggerStatusInvalidated"],
        )
        self.assertFalse(any(event["event_type"].startswith("Action") for event in captured))
        self.assertEqual(result["write_result"]["common_action_event"], 0)

    def test_runner_runtime_bound_fails_closed_before_write(self) -> None:
        row = trigger_state_changed(
            event_id="n4-runner-timeout",
            event_time="2026-07-31T09:35:00+08:00",
            trigger_live=True,
        )
        calls = []
        ticks = iter((0.0, 11.0))
        result = status_runner.run_n5_trigger_status_forward_once(
            self._runner_args("--max-runtime-seconds", "10"),
            plan_provider=lambda _args: status_plan([row], [action_eligible()]),
            writer=lambda _args, _events: calls.append("writer"),
            now_monotonic=lambda: next(ticks),
        )

        self.assertEqual(result["blocked_reason"], "max_runtime_seconds_exceeded")
        self.assertEqual(calls, [])

    @staticmethod
    def _runner_args(*extra: str) -> list[str]:
        return [
            "--for-trade-date",
            TRADE_DATE,
            "--source-trigger-run-id",
            SOURCE_TRIGGER_RUN_ID,
            "--action-run-id",
            ACTION_RUN_ID,
            "--consumer-name",
            CONSUMER_NAME,
            *extra,
        ]

    @staticmethod
    def _aggregate_runner_args(*extra: str) -> list[str]:
        return [
            "--for-trade-date",
            TRADE_DATE,
            "--source-eligible-action-run-id",
            SOURCE_ELIGIBLE_ACTION_RUN_ID,
            "--action-run-id",
            ACTION_RUN_ID,
            "--consumer-name",
            CONSUMER_NAME,
            *extra,
        ]


if __name__ == "__main__":
    unittest.main()
