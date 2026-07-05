# N3 20260617 True Full-Day Minute B2 Rebuild Preflight

Result: `PREFLIGHT_BLOCKED`

- stale_metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- stale current rows total: `2049`
- expected true minute-series rows: `491760`
- row grain: `identity_key + metric_minute_label`
- cleanup required before execute: `True`
- N4 rollback artifact: `docs/N4_ROLLBACK_LATEST_FINAL_1500_REPLAY_BEFORE_TRUE_FULL_DAY_MINUTE_REPLAY_POST_REVIEW.json` result `N4_ROLLBACK_PASS`
- rollback SQL draft: `sql/N3_20260617_true_full_day_minute_b2_rebuild_rollback.sql`

C1 coverage stock/index/board rows: `441840/19440/30480`

Previous-day same-window coverage stock/index/board rows: `441840/19440/30480`

Canonical distribution: `{"BUY": {"rows": 1939, "identities": 1939}, "SELL": {"rows": 2021, "identities": 2021}, "BUY:FULL": {"rows": 110, "identities": 110}, "SELL:FULL": {"rows": 28, "identities": 28}, "BUY_HINT": {"rows": 59, "identities": 59}, "SELL_HINT": {"rows": 165, "identities": 165}}`

No DB business rows were written in this gate. No N4/N5/N6, outbox/inbox/checkpoint consumption/update, worker/scheduler, old-system, voice/mobile/sim/position/order/real trade scope was touched.

## Downstream ref detail

P0 blocker detail: `common_trigger_run` still contains `trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1` with `source_market_data_run_id=action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`, `status=passed`, and zero state/match/outbox rows. This is a stale N4 context snapshot reference and must be rolled back or superseded in N4 before N3 can clean/rebuild the B2 metric target.

