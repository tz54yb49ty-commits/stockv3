# N5 Canonical Action Execute Contract

## Summary

- stage: V3_20260612_N5_REPLAY_AFTER_N4_TRIGGER_PERIOD_BASELINE_FIX_CONTRACT
- layer_role: N5_action
- runner_mode: run_once
- source_trigger_run_id: v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1
- action_run_id: v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1
- consumer_name: v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_consumer_v1
- execute: True
- user_confirmed: True
- P0/P1/P2: 0/0/0
- allow_execute: True

## Guards

- source_run_guard: {'configured': True, 'allowed_source_run_ids': ['v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1'], 'denied_source_run_ids': ['v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3', 'v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1'], 'trigger_run_id': 'v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1', 'trigger_run_denied': False, 'trigger_run_not_allowed': False, 'observed_source_run_ids': {'v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1': 1187}, 'denied_observed_source_run_ids': [], 'outside_allowlist_source_run_ids': [], 'passed': True}
- pending_only_guard: {'allowed_statuses': ['pending'], 'by_status': {'pending': 1187}, 'total_row_count': 1187, 'pending_count': 1187, 'non_pending_count': 0, 'non_pending_sample': [], 'passed': True}
- blockers: []

## Planned Write Scope

- common_action_run: 1
- common_action_quality_item: 0
- stock_action_fact: 965
- index_action_fact: 154
- board_action_fact: 68
- common_action_event: 1187
- common_event_outbox: 1187
- common_event_inbox: 1187
- common_event_consumer_checkpoint: 235
- common_position_state: 0
- common_position_event: 0

## Event Mapping

- output_event_plan: {'ActionEligible': 0, 'ActionBlocked': 911, 'ActionExecuted': 276, 'ActionSkipped': 0}
- BUY_HINT / SELL_HINT remain condition trace only; they do not emit HintEvent.
- B_BUY / S_SELL are the only runtime signal_type values accepted by canonical N5 planning.
- final action_mark is normal / 30m_volume / 30m_shrink only after N5 confirmation passes.
- ActionBlocked means market action not confirmed / 市场动作未确认; it is not a user trade failure.
- TriggerPendingMarketData writes quality only.
- Execute is still gated by --execute, --user-confirmed, and a separate final gate.

## Boundary

- side_effects: {'will_execute_sql': False, 'writes_performed': False, 'common_event_inbox_updated': False, 'consumer_checkpoint_updated': False, 'action_run_written': False, 'action_quality_written': False, 'action_fact_written': False, 'action_event_written': False, 'common_event_outbox_written': False, 'n5_outbox_written': False, 'n4_outbox_status_updated': False, 'n4_outbox_consumed': False, 'position_state_written': False, 'position_event_written': False, 'market_data_pulled': False, 'n1_n2_n3_n4_modified': False, 'n6_user_layer_touched': False, 'user_layer_touched': False, 'voice_touched': False, 'sim_touched': False, 'mobile_touched': False, 'real_trade_touched': False, 'worker_started': False, 'old_system_touched': False}

## Formal Period Passthrough Audit

```json
{
  "planned_action_fact_count": 1187,
  "ordinary_formal_action_fact_count": 0,
  "hint_action_fact_count": 1187,
  "fabricated_formal_period_count": 0,
  "fabricated_formal_period_sample": [],
  "hint_30m_rows": 1187,
  "ordinary_missing_proof_blocked_count": 0
}
```
