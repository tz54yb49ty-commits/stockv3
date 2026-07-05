# V3 20260612 N5 Action Mark Aligned Replay Preflight

Result: `DRY_RUN_PREFLIGHT_PASS`

## Scope

- source N4 run: `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`
- N5 action run: `v3_n5_action_mark_aligned_replay_20260612_from_n4_action_confirmation_metric_after_n3_repair_v1`
- consumer: `n5_action_consumer_v1`

## Preconditions

- N3 `previous_day_same_window_amount` repair post-review: pass
- stale N5 action_mark rollback post-review: pass
- V3 realtime engine scheduler: stopped / not loaded

## N4 Input State

- `TriggerMatched pending`: `49`
- `TriggerPendingMarketData pending`: `4405`
- `TriggerStateChanged pending`: `0`
- delivered / delivering: `0 / 0`

## Target Baseline

Scoped N5 baseline is zero for the new action run:

- run / quality / stock / index / board / action_event / N5 outbox: `0`
- N5 consumer inbox for scoped source: `0`
- N5 consumer checkpoint for scoped source partitions: `0`
- N6 refs: `0`

## Dry-Run Result

- read events: `4454`
- action candidates: `49`
- planned action facts after dedup: `43`
- quality-only plans: `4405`
- duplicate action confirmation grain skipped: `6`
- metric facts available: `49/49`
- period trigger baseline trace: `4454/4454`
- P0/P1/P2: `0/0/0`

Expected N5 events:

- `ActionExecuted`: `43`
- `ActionBlocked`: `0`
- `ActionEligible`: `0`
- `ActionSkipped`: `0`

Expected action fact split:

- stock / index / board: `33 / 0 / 10`
- buy / sell: `39 / 4`
- final action_mark after dedup: `normal=38`, `30m_volume=5`, `30m_shrink=0`

## Rollback Requirements

Rollback SQL: `sql/V3_20260612_n5_action_mark_aligned_replay_rollback.sql`

It must hard-fail before the first DELETE if:

- scoped N5 outbox has delivered/delivering rows
- scoped N5 outbox has downstream inbox/checkpoint refs
- N6/user/voice/mobile/sim/position/trade refs exist

It must delete only scoped N5 outputs:

- `common_event_delivery_attempt` for scoped N5 events
- `common_event_consumer_checkpoint` for this consumer and source partitions
- `common_event_inbox` for this consumer and source run
- N5 `common_event_outbox` / `common_event_ledger`
- `common_action_event`
- stock/index/board action facts
- `common_action_quality_item`
- `common_action_run`

It must not mutate N4 trigger facts, N4 outbox status, N3 projection/metric facts, N6, scheduler, voice/mobile/sim/position/trade, or the old system.

## Final Gate Prompt

```text
layer_role=N5_action。

进入 V3_20260612_N5_ACTION_MARK_ALIGNED_REPLAY_EXECUTE_FINAL_GATE_REVIEW。

依据：
- docs/V3_20260612_N5_ACTION_MARK_ALIGNED_REPLAY_CONTRACT.md/json
- docs/V3_20260612_N5_ACTION_MARK_ALIGNED_REPLAY_PREFLIGHT.md/json
- docs/V3_20260612_N5_ACTION_MARK_ALIGNED_REPLAY_DRY_RUN.md/json
- sql/V3_20260612_n5_action_mark_aligned_replay_rollback.sql

请只读复核是否允许执行 N5 scoped replay：
source_trigger_run_id=v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1
action_run_id=v3_n5_action_mark_aligned_replay_20260612_from_n4_action_confirmation_metric_after_n3_repair_v1

预期：
- read_event_count=4454
- TriggerMatched=49
- TriggerPendingMarketData=4405
- planned ActionExecuted=43
- ActionBlocked/ActionEligible/ActionSkipped=0/0/0
- final action_mark normal=38, 30m_volume=5, 30m_shrink=0
- stock/index/board action facts=33/0/10
- quality rows=4405
- inbox/checkpoint=4454/2082

禁止进入 N6、消费/update outbox、重启 scheduler、voice/mobile/sim/position/trade。
输出 PASS/BLOCKED 和 execute 用户确认命令。
```

`execute_authorized=false` until runtime_control final gate and explicit user confirmation.
