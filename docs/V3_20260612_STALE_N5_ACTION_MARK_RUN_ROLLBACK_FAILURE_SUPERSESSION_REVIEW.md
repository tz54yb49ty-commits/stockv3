# V3 20260612 Stale N5 Action Mark Rollback Failure / Supersession Review

Result: `BLOCKED`

This runtime-control review did not execute rollback, did not write database rows, did not modify the scheduler, did not consume or update outbox/inbox/checkpoint, and did not enter N4/N5/N6/voice/mobile/sim/trade.

## What Happened

The scoped stale N5 rollback was attempted from `N5_action`.

The first execution reported `COMMIT` and delete counts for the original scoped rollback:

- `common_event_consumer_checkpoint=2082`
- `common_event_inbox=4454`
- `common_event_outbox=43`
- `common_action_event=43`
- `stock_action_fact=33`
- `board_action_fact=10`
- `common_action_quality_item=4405`
- `common_action_run=1`

But post-check showed the rollback was not complete. The original scoped consumer rows were gone, while the N5 action facts/outbox/run were present again or remained present. A second attempt correctly hard-failed before the first `DELETE`:

```text
N5 rollback blocked: non-scoped consumer inbox refs exist for source_trigger_run_id (49)
```

## Current Live State

- `common_action_run=1`
- `common_action_quality_item=0`
- `stock_action_fact=33`
- `index_action_fact=0`
- `board_action_fact=10`
- `common_action_event=43`
- N5 outbox `43`, delivered/delivering `0`
- Original scoped consumer `n5_action_consumer_v1` inbox/checkpoint: `0/0`
- Non-scoped consumer inbox refs for the same N4 source: `49`

Non-scoped consumer evidence:

- consumer: `v3_realtime_engine_n5_consumer_20260612`
- inbox refs: `49`
- received_at: `2026-06-13 09:59:11.293845+08`

## Scheduler Proof

`com.ashare-v3.v3-realtime-engine` is still loaded:

- state: `spawn scheduled`
- run interval: `3` seconds
- runs observed: `638`
- last exit code: `0`
- script: `/Users/chuanfuchen/Documents/A股监控系统v3/scripts/run_v3_realtime_engine_once.py`
- flags include `--execute --user-confirmed`

Latest wrapper report says `NOOP_PASS` because deterministic run ids are considered passed, but the child command plan still uses:

- N5 consumer: `v3_realtime_engine_n5_consumer_20260612`
- N5 action run id: `v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1`

## Root Cause Assessment

The rollback failed as an operational sequence issue: the writable V3 realtime engine scheduler was still loaded during or after the stale N5 rollback attempt.

The final gate covered `n5_action_consumer_v1`, but the active production wrapper uses `v3_realtime_engine_n5_consumer_20260612`. That consumer wrote `49` inbox refs for the same preserved N4 source, outside the original rollback scope.

So this is not safe to solve by repeatedly rerunning the same rollback SQL. The writable source must be isolated first, then the rollback scope must explicitly include or supersede the production wrapper consumer refs.

## N4 Preservation Proof

N4 remains preserved:

- `common_trigger_run=1`
- `common_trigger_match=4454`
- `common_trigger_state=4454`
- `common_event_outbox_n4=4454`
- N4 outbox delivered/delivering: `0`

N4 should still not be rolled back as part of this step.

## Decision

Do not continue rollback now.

Required route:

1. Stop `com.ashare-v3.v3-realtime-engine`.
2. Repair N5 rollback scope to include `v3_realtime_engine_n5_consumer_20260612` or explicitly supersede its refs.
3. Re-run runtime-control rollback final gate.

## Forbidden Scope Proof

- Rollback executed by this review: `false`
- Database written by this review: `false`
- Scheduler modified by this review: `false`
- Wrapper manually executed by this review: `false`
- Outbox consumed or updated by this review: `false`
- Inbox/checkpoint consumed or updated by this review: `false`
- N4/N5/N6 executed by this review: `false`
- Voice/mobile/sim/position/trade touched: `false`
- Old system modified: `false`

## Next Prompt

```text
layer_role=runtime_control。

进入 V3_REALTIME_ENGINE_SCHEDULER_STOP_AFTER_STALE_N5_ROLLBACK_PARTIAL_GATE。

目标：在 stale N5 action_mark rollback 出现 partial/复写后，scoped 停用 com.ashare-v3.v3-realtime-engine，避免每 3 秒 scheduler 继续以 v3_realtime_engine_n5_consumer_20260612 触碰同一 N4 source / N5 action_run。只允许执行 launchctl bootout/disable 与 post-check；不得手动执行 wrapper/N3/N4/N5，不执行 rollback，不写业务数据，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/position/trade。停用后复核 scheduler not_loaded、wrapper process count=0、当前 N5 partial state、N4 preserved，然后交接 N5_action 做 rollback scope repair。
```
