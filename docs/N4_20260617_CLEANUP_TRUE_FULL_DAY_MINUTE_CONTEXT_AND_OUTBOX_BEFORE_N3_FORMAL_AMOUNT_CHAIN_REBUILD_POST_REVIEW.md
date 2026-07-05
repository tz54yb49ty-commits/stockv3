# N4 20260617 Cleanup True Full-Day Minute Context/Outbox Before N3 Formal Amount Chain Rebuild

- result: `N4_CLEANUP_PASS`
- source_market_data_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- context_run_id_cleaned: `trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- execute_run_id_cleaned: `trigger_action_confirmation_metric_execute_20260617_true_full_day_lifecycle_replay_mark_change_suppressed__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`

## Rollback SQL Executed

- `sql/N4_20260617_true_full_day_lifecycle_replay_mark_change_suppressed_rollback.sql`
- `sql/N4_cleanup_stale_context_ref_to_final_1500_b2_before_true_full_day_minute_b2_rebuild_rollback.sql`

## Post Cleanup Proof

- common_trigger_run by metric: `0`
- common_trigger_state execute refs: `0`
- common_trigger_match execute refs: `0`
- common_event_outbox execute refs: `0`
- context snapshot rows stock/index/board: `0/0/0`
- event refs inbox/checkpoint/ledger/delivery: `0/0/0/0`
- N3 metric rows preserved total: `491760`

## Forbidden Scope

No N4 regeneration, no N5/N6 entry, no outbox consumption, no inbox/checkpoint update, no market pull, no N2/N3 fact mutation, no worker/scheduler, no voice/mobile/sim/position/order/real trade, no old system access.

## Allowed Next Prompt

```text
layer_role=N3_market_data. Enter N3_20260617_TRUE_FULL_DAY_MINUTE_B2_FORMAL_AMOUNT_CHAIN_REBUILD_EXECUTE_AFTER_N4_CLEANUP_PASS. Use source_condition_run_id=condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1 and source_subscription_run_id=market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1 and source_today_minute_run_id=today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1 and source_metric_run_id=action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1 and n4_cleanup_post_review=docs/N4_20260617_CLEANUP_TRUE_FULL_DAY_MINUTE_CONTEXT_AND_OUTBOX_BEFORE_N3_FORMAL_AMOUNT_CHAIN_REBUILD_POST_REVIEW.json. Goal: rollback/rebuild N3 true full-day B2 with repaired formal_amount_chain_metrics only. Do not enter N4/N5/N6.
```
