# N5 Market Action Confirmation Spec v1 Refresh Gate Report

- result: `REFRESH_PASS_FINAL_GATE_BLOCKED`
- source_trigger_run_id: `trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`
- action_run_id: `action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`
- N4 outbox: `{'pending': 863}`
- metric_join_coverage: `863/863`
- output_event_plan: `{'ActionEligible': 0, 'ActionBlocked': 863, 'ActionExecuted': 0, 'ActionSkipped': 0}`
- blocked_reason_distribution: `{'amount_confirmation_failed': 25, 'price_confirmation_failed': 838}`
- current_scoped_n5_rows: `{'common_action_run': 1, 'common_action_quality_item': 0, 'stock_action_fact': 680, 'index_action_fact': 34, 'board_action_fact': 149, 'common_action_event': 863, 'common_event_outbox': 863, 'common_event_inbox': 863, 'common_event_consumer_checkpoint': 822}`
- execute_final_gate_result: `BLOCKED`
- blockers: `['n5_v1_action_run_scoped_rows_already_exist']`
- rollback_sql: `sql/N5_market_action_confirmation_spec_v1_20260603_execute_rollback.sql`
- rollback_hard_fail_before_delete: `True`

Boundary proof: no execute, no outbox consumption/status update, no N6, no worker, no delivery/notification/push/voice/mobile/sim/position/real trade.
