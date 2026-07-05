# N5 Action Pipeline Execute Preflight

## Summary

- result: `PREFLIGHT_PASS`
- stage: `N5_ACTION_PIPELINE_EXECUTE_CONTRACT_GATE`
- source_trigger_run_id: `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- action_run_id: `action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- P0/P1/P2: `0/0/0`

## Reconciliation

- reconciliation_result: `RECONCILED`
- findings: `N1N5-P0-001, N1N5-P1-002`
- baseline_kind: `N5_action_pipeline_execute_contract`
- baseline/current read_event_count: `605` / `605`
- baseline explainable: `True`
- explanation: N5 action pipeline read_event_count and distributions match the reviewed execute contract; previous baseline_read_event_count=0 was caused by treating the execute contract as an N5-1 baseline.

## Planned / Persisted Scope

- common_action_run: `1`
- common_action_quality_item: `0`
- stock_action_fact: `572`
- index_action_fact: `0`
- board_action_fact: `33`
- common_action_event: `605`
- common_event_outbox: `605`
- common_event_inbox: `605`
- accepted_event_count: `605`
- checkpoint_plan_entry_count: `605`
- checkpoint_physical_watermark_rows: `73`
- common_event_consumer_checkpoint: `73`
- common_position_state: `0`
- common_position_event: `0`

## Checkpoint Semantics

- accepted_event_count: `605`
- common_event_inbox_rows: `605`
- checkpoint_plan_entry_count: `605`
- checkpoint_physical_watermark_rows: `73`
- live_checkpoint_ref_rows: `73`
- checkpoint_key: `consumer_name + partition_key + source_layer`
- meaning: 605 accepted N4 events were inserted into inbox; checkpoint stores/upserts partition watermark rows and live scoped refs are 73.

## Event Mapping

- output_event_plan: `{'input_universe': 605, 'metric_supported': 316, 'metric_missing': 289, 'expected_ActionExecuted': 1, 'expected_ActionBlocked': 604, 'expected_ActionSkipped': 0, 'expected_ActionEligible': 0, 'blocked_reason_distribution': {'None': 1, 'amount_confirmation_failed': 10, 'metric_missing': 289, 'price_confirmation_failed': 305}, 'confirmation_status_distribution': {'failed': 604, 'passed': 1}, 'action_state_distribution': {'blocked': 604, 'executed': 1}, 'action_mark_distribution': {'None': 604, 'normal': 1}, 'signal_type_distribution': {'B_BUY': 573, 'S_SELL': 32}, 'asset_kind_distribution': {'board': 33, 'stock': 572}}`
- ActionBlocked means market action not confirmed / 市场动作未确认; it is not a user trade failure.
- N5 outbox remains pending and is not consumed by this reconciliation gate.

## Boundary

- This reconciliation gate did not execute N5, write the database, consume/update outbox, start workers, enter N6, execute rollback, proposal/order/trade, position/PnL, or real trade.
