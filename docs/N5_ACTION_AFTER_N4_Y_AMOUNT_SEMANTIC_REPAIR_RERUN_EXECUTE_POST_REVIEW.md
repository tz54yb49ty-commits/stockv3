# N5 Action After N4 Y Amount Semantic Repair Rerun Execute Post Review

Result: `PASS`

```text
action_run_id=action_consumer_execute_20260617_until_1352_after_n4_y_amount_semantic_repair_rerun__trigger_action_confirmation_metric_execute_20260617_until_1352_y_amount_semantic_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352_y_amount_semantic_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
source_metric_run_id=action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
inserted_counts={'common_action_run': 1, 'common_action_quality_item': 0, 'stock_action_fact': 662, 'index_action_fact': 39, 'board_action_fact': 63, 'common_action_event': 764, 'common_event_outbox': 764, 'common_event_inbox': 764, 'common_event_consumer_checkpoint': 757}
action_state_distribution=[{'action_state': 'blocked', 'confirmation_status': 'failed', 'rows': 727}, {'action_state': 'executed', 'confirmation_status': 'passed', 'rows': 37}]
action_event_distribution=[{'event_type': 'ActionBlocked', 'rows': 727}, {'event_type': 'ActionExecuted', 'rows': 37}]
n5_outbox_distribution=[{'event_type': 'ActionBlocked', 'status': 'pending', 'rows': 727}, {'event_type': 'ActionExecuted', 'status': 'pending', 'rows': 37}]
final_action_mark_distribution=[{'action_mark': '30m_shrink', 'rows': 7}, {'action_mark': '30m_volume', 'rows': 21}, {'action_mark': 'normal', 'rows': 9}, {'action_mark': 'null', 'rows': 727}]
executed_final_action_mark_distribution=[{'action_mark': '30m_shrink', 'rows': 7}, {'action_mark': '30m_volume', 'rows': 21}, {'action_mark': 'normal', 'rows': 9}]
runtime_signal_type_distribution=[{'signal_type': 'B_BUY', 'rows': 358}, {'signal_type': 'S_SELL', 'rows': 406}]
source_trigger_event_type_distribution=[{'source_trigger_event_type': 'TriggerMatched', 'rows': 764}]
n4_outbox_after=[{'event_type': 'TriggerMatched', 'status': 'pending', 'rows': 764}, {'event_type': 'TriggerPendingMarketData', 'status': 'pending', 'rows': 3562}]
n5_outbox_downstream_refs=[{'table_name': 'common_event_checkpoint_from_n5_outbox', 'rows': 0}, {'table_name': 'common_event_inbox_from_n5_outbox', 'rows': 0}]
rollback_sql_path=sql/N5_action_after_n4_y_amount_semantic_repair_rerun_rollback.sql
blockers=[]
N6_deferred=true
forbidden_scope_touched=false
```
