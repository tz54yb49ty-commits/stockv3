# V3 20260615 N5 Metric Missing Root Cause Registration

Result: `REGISTRATION_PASS`

Registered at: `2026-06-15T11:11:29+08:00`

Layer role: `runtime_control`

## Summary

20260615 N3 -> N5 has not actually opened because N5 has no N3 action-confirmation metric to consume.

N3 B1/C1/B2 and N4 are not the immediate blocker: N4 produced `TriggerMatched=836`, and N5 consumed those matched triggers. N5 then correctly emitted `ActionBlocked(metric_missing)` for all 836 events because the current rules require N3 `*_action_confirmation_projection_metric`, and all three 20260615 action-confirmation metric tables are empty.

This registration does not change N4/N5 business rules and does not execute N3/N5.

## Lineage

- Source N4 run: `n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- Current N5 metric-missing run: `n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- Source B2 realtime projection run: `realtime_projection_metric_20260615_trace_aligned_standard_outbox_until_1000__realtime_daily_snapshot_20260615_standard_outbox_until_1000__market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1`
- Planned N3 metric run: `action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1`
- Planned N5 replay run: `n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1`

## Proof

N4 proof:

- `common_trigger_match=836`
- N4 outbox:
  - `TriggerMatched:pending=836`
  - `TriggerPendingMarketData:pending=415`

N5 proof:

- `common_action_run.status=passed`
- N5 outbox: `ActionBlocked:pending=836`
- N5 action event distribution: `ActionBlocked / blocked / failed / action_mark=<null> = 836`
- Blocked reason distribution: `metric_missing=836`
- `ActionEligible=0`, `ActionExecuted=0`, `ActionSkipped=0`

N3 projection proof:

- B2 realtime projection rows for the source run: stock/index/board/total = `1894/83/127/2104`
- All 20260615 realtime projection rows: stock/index/board/total = `11364/498/762/12624`

N3 action-confirmation metric missing proof:

- 20260615 action-confirmation metric rows: stock/index/board/total = `0/0/0/0`
- Rows for source B2 run id: `0/0/0/0`
- Rows for source N4 run id: `0/0/0/0`
- Rows for source N5 run id: `0/0/0/0`

Downstream proof:

- `user_projection_run=0`
- `user_signal_projection=0`
- `user_signal_card=0`
- `user_notification_queue=0`

## Decision

`blocked_by_layer=N3_market_data`

The correct next step is to generate a scoped N3 action-confirmation metric contract/preflight for the 836 N4 matched triggers, then execute that N3 metric run in the `N3_market_data` layer after final review. Only after the N3 metric rows exist should N5 replay be planned and executed with a new run id.

The old N5 run should be preserved as superseded evidence for now. Do not rollback it before the new N5 replay passes post-review.

## Forbidden Scope Proof

- DB business write executed: `false`
- N3/N4/N5/N6 execute: `false`
- Rollback executed: `false`
- Outbox/inbox/checkpoint consume or update: `false`
- Scheduler/worker started: `false`
- Old system touched: `false`
- Voice/mobile/sim/position/PnL/real trade touched: `false`

## Next Prompt

```text
layer_role=N3_market_data

进入 V3_20260615_N3_ACTION_CONFIRMATION_METRIC_CONTRACT_PREFLIGHT_GATE。

目标：基于 runtime_control root cause registration，为 20260615 N4 TriggerMatched=836 生成 N3 action-confirmation metric dry-run / contract / preflight / rollback。source N4 run = n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000；target metric_run_id = action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1；覆盖 N4 TriggerMatched 对应 asset_kind / identity_key / signal_type / condition_key / trigger_time / trigger refs，并计划写入 stock/index/board_action_confirmation_projection_metric。

要求：不得 execute、不写数据库、不执行 rollback、不进入 N4/N5/N6、不消费/update outbox/inbox/checkpoint、不启动 scheduler/worker、不触碰 voice/mobile/sim/position/PnL/real trade。
```
