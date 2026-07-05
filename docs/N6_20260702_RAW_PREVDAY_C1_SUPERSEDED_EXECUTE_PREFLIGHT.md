# N6 Raw-Prevday-C1 Superseded Execute Preflight

## Summary

- status: PREFLIGHT_PASS
- source_action_run_id: n5_live_tracking_20260702__trigger_provisional_ordinary_20260702_until_0944__realtime_action_confirmation_metric_20260702_until_0944__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__atomic_rule_v1_period_rollover_guard_v1__raw_prevday_c1_amount_v1
- user_projection_run_id: n6_user_projection_20260702_0944__n5_live_tracking_raw_prevday_c1_amount_v1
- dry_run_report_path: docs/N6_20260702_raw_prevday_c1_superseded_plan_only_preflight.json
- blockers: []
- warnings: ['board_context_missing', 'current_price_missing', 'display_basis_missing', 'expected_return_pct_missing', 'target_price_missing']

## Event Summary

- ActionEligible: 60
- ActionExecuted: 4
- input_event_count: 64

## Planned Rows

- user_projection_run: 1
- user_signal_projection: 64
- user_signal_card: 64
- user_notification_queue: 64
- user_signal_decision: 0
- user_sim_rows: 0
- n5_outbox_status_updates: 0

## Affected Identity

- ActionEligible: stock:SZ:002493 action_state=eligible action_mark=None
- ActionExecuted: stock:SZ:002493 action_state=executed action_mark=30m_volume

## Boundary

- database_written: false
- n5_outbox_unchanged: true
- voice_mobile_actual_delivery: false
- sim_real_trade: false
- n3_n4_n5_modified: false

## Baseline Guard

- scoped_counts_all_zero: true
- linked_counts_all_zero: true
- user_projection_run: 0
- user_signal_projection: 0
- user_signal_card: 0
- user_notification_queue: 0

## Final Verdict

N6_ACTION_EVENT_RAW_PREVDAY_C1_SUPERSEDED_PLAN_ONLY_PREFLIGHT_RERUN_PASS_READY_FOR_EXECUTE_GATE
