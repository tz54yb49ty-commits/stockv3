# N5 Full Metric Union Historical Metadata Repair Post Review

Status: POST_REVIEW_PASS

```text
execute_result=EXECUTED
action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
updated_rows={'common_action_event': 605, 'common_event_outbox': 605}
blocked_reason_distribution=[{'blocked_reason': 'amount_confirmation_failed', 'row_count': 17}, {'blocked_reason': 'price_confirmation_failed', 'row_count': 587}]
n4_outbox=[{'event_type': 'TriggerMatched', 'status': 'pending', 'row_count': 605}]
n5_outbox=[{'event_type': 'ActionBlocked', 'status': 'pending', 'row_count': 604}, {'event_type': 'ActionExecuted', 'status': 'pending', 'row_count': 1}]
downstream_inbox_refs=0
checkpoint_refs=0
delivery_attempt_refs=0
n6_policy_refs=0/0/0
position_refs=0/0
rollback_safe=True
```
