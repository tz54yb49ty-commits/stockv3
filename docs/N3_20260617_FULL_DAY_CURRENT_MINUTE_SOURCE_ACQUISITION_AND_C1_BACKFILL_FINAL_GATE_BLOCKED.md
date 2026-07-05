# N3 20260617 Full-Day Current Minute Source Acquisition And C1 Backfill Final Gate

- result: `BLOCKED`
- blocked_stage: `source_acquisition_before_db_write`
- blocked_reason: `required scoped BJ index minute source returned 0 rows; full 15:00 source coverage is not complete`
- planned_today_minute_run_id: `today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- C1 backfill executed: `false`
- B2 metric executed: `false`

## Source Probe
- index:BJ:899050: rows `0`, max_hhmm `None`, status `missing_or_partial`
- index:BJ:899601: rows `0`, max_hhmm `None`, status `missing_or_partial`
- index:SH:000001: rows `240`, max_hhmm `15:00`, status `passed`
- stock:SH:600004: rows `240`, max_hhmm `15:00`, status `passed`
- board:TDX:881002: rows `240`, max_hhmm `15:00`, status `passed`

## Per-Asset Current Coverage Before Acquisition
- stock: scoped `1841`, full_1500 `0`, missing `0`, partial `1841`, rows `172/172`, max_hhmm `13:52`
- index: scoped `83`, full_1500 `0`, missing `2`, partial `81`, rows `0/172`, max_hhmm `13:52`
- board: scoped `127`, full_1500 `0`, missing `0`, partial `127`, rows `172/172`, max_hhmm `13:52`

## Rollback
- rollback_required: `false`
- rollback_sql_path: `null`
- reason: no DB/runtime state changed

## Allowed Next Prompt

```text
layer_role=N3_market_data.

进入 N3_20260617_FULL_DAY_CURRENT_MINUTE_MISSING_BJ_INDEX_POLICY_OR_ALTERNATE_SOURCE_GATE.

目标：处理 20260617 repaired-lineage full-day current minute source acquisition blocker。不得执行 B2，不进入 N4/N5/N6。

Use:
- trade_date=20260617
- source_condition_run_id=condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_subscription_run_id=market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- blocked_source_acquisition_artifact=docs/N3_20260617_FULL_DAY_CURRENT_MINUTE_SOURCE_ACQUISITION_AND_C1_BACKFILL_FINAL_GATE_BLOCKED.json
- missing_required_identities=index:BJ:899050,index:BJ:899601

必须二选一并给证据：
1. 提供 N3 内允许的 alternate source，使 BJ index current minute_bar_1m 可证明 240 rows through 15:00；或
2. 明确登记这些 required identities 为 quality-visible blockers，并决定是否允许 excluding-blocker scoped C1 backfill。

禁止：B2 metric execute、N4/N5/N6、old-v1 active proof、until_1352 metric full-day proof、outbox/inbox/checkpoint mutation、worker、voice/mobile/sim/position/order/real trade。
```
