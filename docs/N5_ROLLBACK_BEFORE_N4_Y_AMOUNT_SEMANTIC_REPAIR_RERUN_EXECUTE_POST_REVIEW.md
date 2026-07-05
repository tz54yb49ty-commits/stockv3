# N5 Rollback Before N4 Y Amount Semantic Repair Rerun Execute Post Review

Result: `PASS`

```text
action_run_id=action_consumer_execute_20260617_until_1352_after_repaired_n2_n3_n4_full_scope_pass__trigger_action_confirmation_metric_execute_20260617_until_1352__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
rollback_sql_path=sql/N5_action_after_repaired_n2_n3_n4_full_scope_pass_checkpoint_scoped_superseding_rollback.sql
rollback_executed=True
blockers=[]
before_common_action_run=1
after_common_action_run=0
before_n5_outbox=970
after_n5_outbox=0
before_scoped_inbox=970
after_scoped_inbox=0
n4_outbox_after=[{'event_type': 'TriggerMatched', 'status': 'pending', 'rows': 970}, {'event_type': 'TriggerPendingMarketData', 'status': 'pending', 'rows': 3356}]
entered_n4=false
entered_n6=false
worker_started=false
```
