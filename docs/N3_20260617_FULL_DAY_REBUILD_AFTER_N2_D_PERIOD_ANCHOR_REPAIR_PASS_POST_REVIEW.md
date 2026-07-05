# N3 20260617 Full-Day Rebuild After N2 D-Anchor Repair Post-Review

- result: `BLOCKED`
- source_condition_run_id: `condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- new_subscription_run_id: `market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- new_today_minute_run_id: `today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- new_full_day_metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`

## Blocking Findings
- `new_d_anchor_subscription_not_executed` (P0): execute new D-anchor market_data_subscription control rows under new_subscription_run_id
- `new_d_anchor_full_day_c1_not_executed` (P0): execute or prove full-day C1 rows with source_condition_run_id aligned to D-anchor run
- `new_d_anchor_metric_source_coverage_not_proven` (P0): {'target_metric_baseline': {'stock': 0, 'index': 0, 'board': 0, 'run_rows': 0, 'quality_rows': 0}, 'reason': 'metric target is clean, but source C1 coverage is zero for the new D-anchor run'}

## Canonical Distribution
- distribution: `{"BUY": 1941, "BUY:FULL": 110, "BUY_HINT": 59, "SELL": 2023, "SELL:FULL": 28, "SELL_HINT": 165}`
- covers BUY, SELL, BUY:FULL, SELL:FULL, BUY_HINT, SELL_HINT: `true`
- hint_only: `false`

## BJ Blockers
- `index:BJ:899050`: current minute rows for 20260617 = `0`; preserve quality-visible blocker if source remains unavailable.
- `index:BJ:899601`: current minute rows for 20260617 = `0`; preserve quality-visible blocker if source remains unavailable.

## Old-Lineage Exclusion
- forbidden old lineage: `condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- existing B2/C1 artifacts are bound to forbidden old lineage and contain `until_1352`; not accepted as full-day proof.

## Rollback
- rollback SQL: `sql/N3_20260617_full_day_rebuild_after_n2_d_anchor_repair_rollback.sql`
- default hard-fail before row removal: `true`
- scope: new D-anchor subscription/A1/C1/metric run ids only

## Boundary
- N4/N5/N6 entered: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- worker/scheduler started: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
- old system touched: `false`

## Decision
- allowed next N4 prompt: `null`
- recommended next gate: `N3_20260617_D_ANCHOR_REPAIR_SUBSCRIPTION_AND_FULL_DAY_C1_EXECUTE_FINAL_GATE_REVIEW`
