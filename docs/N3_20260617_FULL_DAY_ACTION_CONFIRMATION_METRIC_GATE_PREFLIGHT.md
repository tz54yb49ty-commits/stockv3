# N3 20260617 Full-Day Action-Confirmation Metric Gate Preflight

- result: `PREFLIGHT_BLOCKED`
- blocked_stage: `full_day_minute_coverage_preflight`
- blocked_reason: `current minute_bar_1m under repaired lineage stops at 13:52, not 15:00`
- planned_metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- planned_metric_exists: `false`
- execute_prompt_emitted: `false`

## Lineage

- source_condition_run_id: `condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1` (`passed_active`)
- source_subscription_run_id: `market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- repaired N2/N3 post-review artifacts: `docs/N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_EXECUTE_POST_REVIEW.json`, `docs/V3_20260617_N3_REBUILD_AFTER_N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_POST_REVIEW.json`

## Full-Day Minute Coverage

- stock max current minute: `13:52`
- index max current minute: `13:52`
- board max current minute: `13:52`
- required: `15:00`

## Canonical Distribution

- BUY: `1941`
- SELL: `2023`
- BUY:FULL: `110`
- SELL:FULL: `28`
- BUY_HINT: `59`
- SELL_HINT: `165`
- not HINT-only: `true`

## Stale Metric Proof

- until_1352 metric: `action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- rows stock/index/board/total: `1841/81/127/2049`
- max metric_minute_label: `13:52`
- full-day reuse allowed: `false`

## Forbidden Scope Proof

- DB written: `false`
- metric executed: `false`
- N4/N5/N6 entered: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- worker/scheduler started: `false`
- old system read/modified: `false`
- voice/mobile/sim/position/order/real trade touched: `false`

## Next

No N3 full-day B2 execute prompt is emitted. Stay in `N3_market_data` and first prepare current 20260617 minute coverage to 15:00 under the repaired lineage.
