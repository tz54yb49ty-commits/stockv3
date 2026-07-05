# N3 20260617 Full-Day Current Minute Coverage Backfill Gate Preflight

- result: `BLOCKED`
- blockers: `['repaired_lineage_current_minute_scope_not_covered_to_1500', 'no_lineage_compatible_20260617_current_minute_source_to_1500_found_in_n3_runtime']`
- planned_today_minute_run_id: `today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- planned_full_day_metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- C1 backfill executed: `false`
- B2 metric executed: `false`

## Per-Asset 15:00 Coverage
- stock: scoped `1841`, full_1500 `0`, missing `0`, partial `1841`, min/max rows `172/172`, max_hhmm `13:52`
- index: scoped `83`, full_1500 `0`, missing `2`, partial `81`, min/max rows `0/172`, max_hhmm `13:52`
- board: scoped `127`, full_1500 `0`, missing `0`, partial `127`, min/max rows `172/172`, max_hhmm `13:52`

## Source Compatibility
- lineage-compatible 15:00 source candidates: `0`
- any N3 current source at 15:00 or later: `0`
- planned C1 target clean: rows stock/index/board `0/0/0`, outbox/inbox/checkpoint `0/0/0`

## Exclusions
- old-v1 as active proof: `excluded`
- until_1352 metric as full-day proof: `excluded`
- B2 full-day metric execute prompt: `not emitted`

## Quality-Visible Blockers
- stock: all `1841` scoped identities are partial current minute rows ending `13:52`
- index: `2` missing current minute identities and `81` partial identities ending `13:52`
- board: all `127` scoped identities are partial current minute rows ending `13:52`

## Rollback
- rollback_required: `false`
- rollback_sql_path: `null`
- reason: preflight artifact only; no DB/runtime state changed

## Allowed Next Prompt

```text
layer_role=N3_market_data.

进入 N3_20260617_FULL_DAY_CURRENT_MINUTE_SOURCE_ACQUISITION_AND_C1_BACKFILL_FINAL_GATE.

目标：基于 repaired lineage 获取/补齐 20260617 current minute_bar_1m 到 15:00，然后仅在 source coverage 可证明完整时执行 bounded C1 full-day minute backfill。不得执行 B2 metric，不进入 N4/N5/N6。

Use:
- trade_date=20260617
- source_condition_run_id=condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_subscription_run_id=market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- planned_today_minute_run_id=today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- prior_blocked_artifact=docs/N3_20260617_FULL_DAY_CURRENT_MINUTE_COVERAGE_BACKFILL_GATE_PREFLIGHT.json

必须证明：stock/index/board scoped identities 15:00 coverage；old-v1 不作为 active proof；until_1352 metric 不作为 full-day proof；quality blockers visible；不写 outbox/inbox/checkpoint；不启动 worker；不触碰 voice/mobile/sim/position/order/real trade。

若 source acquisition 或 C1 coverage 任一步 BLOCK，立即停止，不进入 B2/N4/N5/N6。
```
