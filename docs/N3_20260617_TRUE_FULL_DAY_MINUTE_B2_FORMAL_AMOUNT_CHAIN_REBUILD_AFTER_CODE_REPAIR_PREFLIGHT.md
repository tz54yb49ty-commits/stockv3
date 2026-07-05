# N3 true full-day B2 formal amount chain rebuild preflight

- result: `BLOCKED`
- blocked_stage: `rollback_safety_preflight`
- blocked_reason: `source_metric_run_id_has_downstream_n4_trigger_and_pending_outbox_refs`
- source_metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`

## Evidence

- Source C1 and previous-day same-window coverage are complete for the included scope:
  - stock `1841 * 240 = 441840`
  - index `81 * 240 = 19440`
  - board `127 * 240 = 30480`
  - labels `09:31-15:00`
- Current B2 target is true full-day minute grain with `491760` rows and `0` duplicate identity-minute groups.
- Current rows require rebuild after code repair: `raw_json.formal_period_amount_proof.amount_chain_metrics` and `trace_json.formal_period_amount_proof.amount_chain_metrics` are present in `0/491760` rows, while repaired code writes those nested proof fields.
- Rollback safety is not satisfied:
  - `common_trigger_run` refs: `2`
  - N4 context run: `trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
  - N4 execute run: `trigger_action_confirmation_metric_execute_20260617_true_full_day_lifecycle_replay_mark_change_suppressed__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
  - pending outbox refs: `3907`

## Boundary

No B2 rebuild was executed. No rollback SQL was executed. N4/N5/N6 were not entered. Outbox/inbox/checkpoint were not consumed or updated. No worker/scheduler, voice/mobile/sim/position/order/real trade, old system, or N2 change was touched.

## Allowed Next Prompt

```text
layer_role=N4_trigger.
Enter N4_20260617_CLEANUP_TRUE_FULL_DAY_MINUTE_CONTEXT_AND_OUTBOX_BEFORE_N3_FORMAL_AMOUNT_CHAIN_REBUILD.
Use:
- source_market_data_run_id=action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- n3_blocked_preflight_artifact=docs/N3_20260617_TRUE_FULL_DAY_MINUTE_B2_FORMAL_AMOUNT_CHAIN_REBUILD_AFTER_CODE_REPAIR_PREFLIGHT.json
Goal: cleanup/supersede only N4 context/trigger/outbox refs to this N3 metric so N3 can rollback-safe rebuild formal_amount_chain_metrics. Do not enter N5/N6; do not consume/update outbox/inbox/checkpoint; do not start worker/scheduler; do not touch voice/mobile/sim/position/order/real trade or old system.
```
