# N5 Action Rerun After N4 Formal Transition Gate Repair PASS Preflight

Result: `PASS`

```text
trade_date=20260617
source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
source_metric_run_id=action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
planned_action_run_id=action_consumer_execute_20260617_until_1352_after_n4_formal_transition_gate_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
consumer_name=n5_action_consumer_v1
source_event_type=TriggerMatched
```

## Proof Summary

- N4 post-review: `PASS`; execute report: `EXECUTED`.
- N4 outbox scope: TriggerMatched pending=302; TriggerPendingMarketData pending=4024 ignored; TriggerStateChanged=0 ignored.
- N4 delivered/delivering rows for source trigger: 0.
- Existing planned N5 rows for action_run_id: {'common_action_run': 0, 'common_action_quality_item': 0, 'stock_action_fact': 0, 'index_action_fact': 0, 'board_action_fact': 0, 'common_action_event': 0, 'common_event_outbox_n5_source_run': 0, 'common_event_ledger_n5_source_run': 0, 'common_event_inbox_downstream_n5_source_run': 0, 'common_event_inbox_n5_consumer_source_trigger': 0, 'checkpoint_payload_refs_planned_action_or_source_trigger': 0}.
- Full in-memory N5 plan: action_state={'blocked': 290, 'executed': 12}; action_event={'ActionBlocked': 290, 'ActionExecuted': 12}; final_action_mark={'<null>': 290, '30m_shrink': 4, '30m_volume': 5, 'normal': 3}.
- Metric join coverage: 302/302 from `action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`.
- Target exclusions: `stock:SZ:300687 BUY:Y,M,D` TriggerMatched=0; `stock:SZ:300684 BUY:M,D` TriggerMatched=0; target N5 entry count=0.
- Runtime signal types: {'S_SELL': 242, 'B_BUY': 60}; deprecated runtime signal types=0; BUY_HINT trace=7; SELL_HINT trace=22.

## Boundaries

No N5 execute, rollback SQL execution, N5 outbox consumption, N4 outbox status update, scheduler/worker, N6, voice/mobile/sim/position/order/real trade, or old-system access was performed.

## Artifacts

- Preflight JSON: `docs/N5_ACTION_RERUN_AFTER_N4_FORMAL_TRANSITION_GATE_REPAIR_PASS_PREFLIGHT.json`
- Baseline JSON: `docs/N5_ACTION_RERUN_AFTER_N4_FORMAL_TRANSITION_GATE_REPAIR_PASS_BASELINE.json`
- Rollback SQL: `sql/N5_action_rerun_after_n4_formal_transition_gate_repair_rollback.sql`

## Allowed Next Prompt

```text
layer_role=N5_action.
Enter N5_ACTION_RERUN_AFTER_N4_FORMAL_TRANSITION_GATE_REPAIR_PASS_EXECUTE.

Use:
- trade_date=20260617
- action_run_id=action_consumer_execute_20260617_until_1352_after_n4_formal_transition_gate_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_metric_run_id=action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_condition_run_id=condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- consumer_name=n5_action_consumer_v1
- source_event_type=TriggerMatched
- expected_read_event_count=302
- n5_preflight_artifact=docs/N5_ACTION_RERUN_AFTER_N4_FORMAL_TRANSITION_GATE_REPAIR_PASS_PREFLIGHT.json
- n5_baseline_artifact=docs/N5_ACTION_RERUN_AFTER_N4_FORMAL_TRANSITION_GATE_REPAIR_PASS_BASELINE.json
- rollback_sql_path=sql/N5_action_rerun_after_n4_formal_transition_gate_repair_rollback.sql

Execute N5 action run-once only.
Do not enter N6.
Do not consume N5 outbox.
Do not update N4 outbox status.
Do not start scheduler/worker.
Do not touch N1/N2/N3/N4 writes.
Do not touch voice/mobile/sim/position/order/real trade.
Do not read or modify old system.
```
