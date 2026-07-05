# N3-N4-N5 20260612 Reactivation After B2 Dates Contract Repair

Result: `BLOCKED`

## Activation

Bootstrap succeeded:

```bash
launchctl bootstrap gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

## First Automatic Pass

Latest chain report:

```text
result=BLOCKED
blocked_reason=n3_auto_poll_failed
as_of=2026-06-12T13:58:39.447553+08:00
```

N3 auto-poll:

```text
status=blocked
reason=child_step_failed
failed_stage=B2
effective_hhmm=1357
executed_child_command_count=3
```

## Blocker

The previous trace-aligned B2 `dates.source_trade_date` blocker is cleared enough for the chain to proceed to a fresh N3 auto-poll pass. The new blocker is in N3-B2 fact-only projection:

```text
psycopg.errors.CheckViolation:
new row for relation "stock_realtime_projection_metric"
violates check constraint "stock_realtime_projection_metric_check2"
```

Evidence:

```text
N3-B2 building realtime projection rows
N3-B2 writing 2082 projection facts
failed row: stock:SZ:000617
projection_snapshot_time=2026-06-12 14:00:00.010889+08
```

Required repair gate:

```text
N3_20260612_B2_FACT_ONLY_PROJECTION_SCHEMA_CONSTRAINT_COMPATIBILITY_REPAIR_GATE
```

## Row Boundary Proof

```text
B1 common run=1
C1 common run=1
B2 common run=0
B2 quality=0
B2 projection stock/index/board=0/0/0
B2 outbox/inbox refs=0/0
N4 refs=0
N5 refs=0
```

## Scheduler State

At report generation, scheduler had already started a second automatic pass:

```text
state=running
runs=2
last exit code=2
pid=13961
```

This gate did not execute bootout because the authorized scope was bootstrap + post-check only.

## Stop Recommendation

Next gate should stop it:

```text
N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_STOP_AFTER_B2_FACT_ONLY_SCHEMA_CONSTRAINT_BLOCKED_GATE
```

Stop command registry:

```bash
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

## Forbidden Scope Proof

This gate did not manually execute wrapper/N3/N4/N5, did not execute rollback, did not consume/update outbox/inbox/checkpoint, did not enter N6, and did not touch voice/mobile/sim/trade.

## Next Prompt

```text
layer_role=runtime_control。

进入 N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_STOP_AFTER_B2_FACT_ONLY_SCHEMA_CONSTRAINT_BLOCKED_GATE。

目标：在 reactivation 后 BLOCKED 于 N3-B2 fact-only projection stock_realtime_projection_metric check constraint 后，scoped 停用 com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll，避免每 60 秒继续重复失败。只允许执行 launchctl bootout/disable 与 post-check；不得手动执行 wrapper/N3/N4/N5，不执行 rollback，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/trade。停用后交接 N3_20260612_B2_FACT_ONLY_PROJECTION_SCHEMA_CONSTRAINT_COMPATIBILITY_REPAIR_GATE。
```
