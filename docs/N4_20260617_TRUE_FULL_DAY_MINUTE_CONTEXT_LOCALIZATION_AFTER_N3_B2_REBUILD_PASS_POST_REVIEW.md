# N4 True Full-Day Minute Context Localization Post Review

Result: BLOCKED

Context localization result: N4_CONTEXT_LOCALIZATION_PASS
Trigger context run: `trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
Source metric run: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`

Context rows: stock=3882, index=173, board=271, total=4326.
N3 true-minute B2 rows: stock=441840, index=19440, board=30480, total=491760; labels 09:31-15:00; per identity min/max=240/240; metric_ready=491760, not_ready=0.

Blocker: active N4 dry-run/execute entrypoints still call `build_action_confirmation_metric_plans`, which uses `latest_metric_by_identity`; true full-day replay must use `build_action_confirmation_metric_full_day_replay_plans`.

Rollback SQL: `sql/N4_20260617_true_full_day_minute_context_localization_after_n3_b2_rebuild_pass_rollback.sql`

No N4 trigger replay execute, no N5/N6 entry, no outbox/inbox/checkpoint consumption, no market pull, no N2/N3 fact mutation, no worker/scheduler, and no voice/mobile/sim/position/order/real-trade/old-system path were touched.

Allowed next prompt:

```text
layer_role=N4_trigger.
Enter N4_TRUE_FULL_DAY_MINUTE_REPLAY_PLANNER_WIRING_REPAIR_PREFLIGHT.
Use trigger_context_run_id=trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1 and source_metric_run_id=action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1 and n4_context_post_review=docs/N4_20260617_TRUE_FULL_DAY_MINUTE_CONTEXT_LOCALIZATION_AFTER_N3_B2_REBUILD_PASS_POST_REVIEW.json.
Goal: repair N4 dry-run/preflight/execute planner routing so true full-day minute-series B2 uses build_action_confirmation_metric_full_day_replay_plans, add focused tests, run dry-run/preflight only, and do not execute N4 replay or enter N5/N6.
```
