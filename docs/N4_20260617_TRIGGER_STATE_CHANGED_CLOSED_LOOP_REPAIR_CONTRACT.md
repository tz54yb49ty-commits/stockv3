# N4 Action-Confirmation Metric Business Execute Contract

- result: CONTRACT_PASS
- execute_run_id: trigger_action_confirmation_metric_execute_20260617_full_day_state_changed_closed_loop_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- projection_run_id: action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- trigger_context_run_id: trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- source_condition_run_id: condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- for_trade_date: 20260617
- TriggerMatched: 550
- TriggerPendingMarketData: 3776
- common_trigger_state: 4326
- common_trigger_match: 550
- common_event_outbox: 8652
- allowed_write_tables: ['common_trigger_run', 'common_trigger_quality_item', 'common_trigger_state', 'common_trigger_match', 'common_event_outbox']
- forbidden_write_tables: ['common_event_inbox', 'common_event_consumer_checkpoint', 'N2 condition tables', 'N3 action-confirmation metric/snapshot/minute/subscription facts', 'N5/N6/action/user/voice/mobile/sim/position/real-trade tables', 'worker state']
- consumes_n3_outbox: False
- writes_inbox: False
- writes_checkpoint: False
- rollback_sql_path: sql/N4_20260617_trigger_state_changed_closed_loop_repair_rollback.sql
- business_execute_runner_ready: True
- runner_blocker: 

This contract does not execute N4 business writes. A separate business execute runner and explicit final confirmation are still required.
