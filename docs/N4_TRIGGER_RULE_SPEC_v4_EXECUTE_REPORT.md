# N4 Trigger Rule Spec v4 Execute Report

Result: `REFRESH_PASS`

- execute_run_id: `trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`
- status: `passed`
- run/quality/state/match/outbox rows: `1/4/863/863/863`
- TriggerMatched: `863`
- outbox pending/delivered/delivering: `863/0/0`
- invalid N5 entry count: `0`
- BJ TriggerMatched rows: `0`
- FULL TriggerMatched rows: `0`
- rollback_safe: `true`

Boundary: report refresh only; no N4 execute, no outbox consumption, no inbox/checkpoint writes, no N5/N6, no worker, no delivery/notification/push/voice/mobile/sim/position/real trade.

```json
{
  "actual_outcomes": {
    "n5_entry_allowed": 0
  },
  "actual_writes": {
    "TriggerMatched": 863,
    "TriggerPendingMarketData": 0,
    "TriggerStateChanged": 0,
    "common_event_outbox": 863,
    "common_trigger_match": 863,
    "common_trigger_quality_item": 4,
    "common_trigger_run": 1,
    "common_trigger_state": 863
  },
  "bj_quality_visible_proof": {
    "dry_run_quality_blocked_rows": 4,
    "passed": true,
    "recognized_bj_identity_keys": [
      "index:BJ:899050",
      "index:BJ:899601"
    ],
    "trigger_matched_rows": 0
  },
  "boundary_proof": {
    "checkpoint_refs": 0,
    "database_business_writes_performed_by_refresh": false,
    "delivery_notification_push_voice_mobile_sim_position_real_trade": false,
    "inbox_checkpoint_written": false,
    "inbox_refs": 0,
    "n5_n6_entered": false,
    "n5_refs": {
      "common_action_event": 0,
      "common_action_run": 0
    },
    "n6_refs": {
      "user_notification_queue": 0,
      "user_projection_run": 0,
      "user_signal_card": 0,
      "user_signal_projection": 0
    },
    "outbox_consumed": false,
    "report_artifacts_refreshed": true,
    "worker_started": false
  },
  "contract_path": "docs/N4_TRIGGER_RULE_SPEC_v4_execute_contract_draft.json",
  "dry_run_report_path": "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_dry_run_report.json",
  "event_distribution": [
    {
      "event_type": "TriggerMatched",
      "row_count": 863,
      "status": "pending"
    }
  ],
  "execute_run_id": "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1",
  "full_blocked_proof": {
    "dry_run_blocked_rows": 92,
    "passed": true,
    "trigger_matched_rows": 0
  },
  "layer_role": "N4_trigger",
  "n5_entry_guard": {
    "invalid_n5_entry_count": 0,
    "passed": true,
    "rule": "TriggerMatched + B_BUY/S_SELL + matched + trigger_live=true + n5_entry_allowed=true"
  },
  "next_gate": {
    "allow_n5_v1_dry_run_gate_confirmation": true,
    "allow_runtime_control_post_review_registration": true,
    "execute_authorized": false,
    "n5_n6_still_not_entered": true
  },
  "outbox_status": {
    "delivered": 0,
    "delivering": 0,
    "pending": 863
  },
  "preflight_path": "docs/N4_TRIGGER_RULE_SPEC_v4_execute_preflight_draft.json",
  "quality_distribution": [
    {
      "gate_code": "n4_v4_bj_quality_blocked_visible",
      "row_count": 1,
      "severity": "P0",
      "status": "passed"
    },
    {
      "gate_code": "n4_v4_full_blocked_visible",
      "row_count": 1,
      "severity": "P0",
      "status": "passed"
    },
    {
      "gate_code": "n4_v4_invalid_n5_entry_zero",
      "row_count": 1,
      "severity": "P0",
      "status": "passed"
    },
    {
      "gate_code": "n4_v4_matched_only_persistence_selected",
      "row_count": 1,
      "severity": "P0",
      "status": "passed"
    }
  ],
  "refreshed_at": "2026-06-04T03:56:36.204457+00:00",
  "result": "REFRESH_PASS",
  "rollback_safe": true,
  "rollback_sql_path": "sql/N4_TRIGGER_RULE_SPEC_v4_execute_rollback_draft.sql",
  "rows": {
    "common_event_outbox": 863,
    "common_trigger_match": 863,
    "common_trigger_quality_item": 4,
    "common_trigger_run": 1,
    "common_trigger_state": 863
  },
  "run": {
    "action_layer_touched": false,
    "context_snapshot_row_count": 0,
    "created_at": "2026-06-04 11:45:41.414279+08:00",
    "finished_at": "2026-06-04 11:45:41.414279+08:00",
    "for_trade_date": "20260603",
    "generated_by": "trigger_rule_v4_execute",
    "market_data_pulled": false,
    "mode": "execute",
    "p0_count": 0,
    "p1_count": 0,
    "p2_count": 0,
    "prev_trade_date": "20260602",
    "raw_json": {
      "consumes_n3_outbox": false,
      "input_plan_count": 5222,
      "outcome_persistence_strategy": "matched_only",
      "persisted_plan_count": 863,
      "snapshot_run_id": "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
      "trigger_context_run_id": "trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1",
      "trigger_rule_policy_hash": "3d4b046ea6a02ad8",
      "trigger_rule_spec_version": "N4_TRIGGER_RULE_SPEC_v4",
      "writes_outbox": true
    },
    "real_trade_touched": false,
    "run_id": "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1",
    "sim_touched": false,
    "source_condition_row_count": 5222,
    "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
    "source_market_data_run_id": "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
    "source_trade_date": "20260602",
    "started_at": "2026-06-04 11:45:41.414279+08:00",
    "status": "passed",
    "trigger_event_outbox_count": 863,
    "trigger_match_row_count": 863,
    "trigger_state_row_count": 863,
    "updated_at": "2026-06-04 11:45:41.414279+08:00",
    "user_layer_touched": false,
    "voice_touched": false,
    "worker_started": false
  },
  "run_status": "passed",
  "stage": "N4_V4_EXECUTE_REPORT_ARTIFACT_REFRESH_GATE",
  "status": "passed",
  "trigger_rule_policy_hash": "3d4b046ea6a02ad8",
  "trigger_rule_spec_version": "N4_TRIGGER_RULE_SPEC_v4"
}
```
