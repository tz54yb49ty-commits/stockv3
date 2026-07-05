# N5 Action After Repaired N2/N3/N4 Full Scope Pass Preflight

Result: `PASS`

```text
action_run_id=action_consumer_execute_20260617_until_1352_after_repaired_n2_n3_n4_full_scope_pass__trigger_action_confirmation_metric_execute_20260617_until_1352__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
source_metric_run_id=action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
consumed_trigger_matched_count=970
ignored_trigger_pending_market_data=3356
ignored_trigger_state_changed=0
action_state_distribution={'blocked': 923, 'executed': 47}
action_event_distribution={'ActionBlocked': 923, 'ActionEligible': 0, 'ActionExecuted': 47, 'ActionSkipped': 0}
final_action_mark_distribution={'30m_shrink': 11, '30m_volume': 25, 'normal': 11, 'null': 923}
runtime_signal_type_distribution={'B_BUY': 399, 'S_SELL': 571}
rollback_sql_path=sql/N5_action_after_repaired_n2_n3_n4_full_scope_pass_rollback.sql
post_review_artifact=docs/N5_ACTION_AFTER_REPAIRED_N2_N3_N4_FULL_SCOPE_PASS_PREFLIGHT.json
blockers=[]
N6_deferred=true
forbidden_scope_touched=false
```
