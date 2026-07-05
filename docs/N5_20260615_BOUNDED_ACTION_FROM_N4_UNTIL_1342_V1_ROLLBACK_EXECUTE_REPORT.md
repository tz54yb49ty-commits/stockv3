# N5 20260615 until_1342 v1 rollback execute report

- result: `ROLLBACK_PASS`
- action_run_id: `n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1342_v1`
- source_trigger_run_id: `n4_production_semantic_replay_20260615_market_snapshot_updated_until_1342`
- consumer_name: `n5_action_bounded_consumer_20260615_after_n3_metric_until_1342_v1`

## Deleted Counts
- common_event_delivery_attempt: `0`
- common_event_consumer_checkpoint: `862`
- common_event_inbox: `871`
- common_event_outbox: `871`
- common_event_ledger: `0`
- common_action_event: `871`
- board_action_fact: `1`
- index_action_fact: `1`
- stock_action_fact: `869`
- common_action_quality_item: `0`
- common_action_run: `1`

## After Counts
- common_action_run: `0`
- common_action_quality_item: `0`
- stock_action_fact: `0`
- index_action_fact: `0`
- board_action_fact: `0`
- common_action_event: `0`
- common_event_outbox_n5: `0`
- scoped_consumer_inbox: `0`
- scoped_consumer_checkpoint: `0`
