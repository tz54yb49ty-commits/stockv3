# N3-N4-N5 20260612 Re-activation After B2 Expected Distribution Repair

Result: `BLOCKED`

## Activation

Bootstrap succeeded:

```bash
launchctl bootstrap gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

```text
bootstrap exit code=0
```

## First Automatic Pass

Latest chain report:

```text
path=docs/N3_N4_N5_REALTIME_CHAIN_REPORT_20260612.json
as_of=2026-06-12T13:34:28.088329+08:00
hhmm=1333
result=BLOCKED
blocked_reason=n3_b2_trace_aligned_projection_failed
```

Stage result:

```text
N3_B1_C1_B2=0
N3_B1_STANDARD_OUTBOX=0
N3_B2_TRACE_ALIGNED_PROJECTION=1
```

## Blocker

The previous rows-by-asset blocker is cleared. B2 reached:

```text
N3-B2 building realtime projection rows
N3-B2 writing 2082 projection facts
```

New blocker:

```text
KeyError: source_trade_date
```

Cause:

```text
insert_projection_run expects contract["dates"]["source_trade_date"],
but the chain trace-aligned B2 contract only has for_trade_date and prev_trade_date.
```

Required repair gate:

```text
N3_20260612_B2_TRACE_ALIGNED_STANDARD_OUTBOX_DATES_CONTRACT_COMPATIBILITY_REPAIR_GATE
```

## Row Proof

After the first automatic pass:

```text
B1 standard outbox rows=2082
B1 standard outbox pending=2082
B1 delivered/delivering=0/0
B2 common_market_data_run=0
B2 quality=0
B2 projection rows stock/index/board=0/0/0
B2 outbox/inbox/checkpoint refs=0/0/0
N4 refs=0
N5 refs=0
```

## Scheduler State

At report generation, scheduler had already started a second automatic pass:

```text
state=running
runs=2
last exit code=2
pid=87889
```

This gate did not execute bootout because the authorized scope was bootstrap + post-check only.

## Stop Recommendation

Next gate should stop it:

```text
N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_STOP_AFTER_B2_DATES_CONTRACT_BLOCKED_GATE
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

进入 N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_STOP_AFTER_B2_DATES_CONTRACT_BLOCKED_GATE。

目标：在 reactivation 后 BLOCKED 于 N3-B2 trace-aligned contract dates.source_trade_date missing 后，scoped 停用 com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll，避免每 60 秒继续重复失败。只允许执行 launchctl bootout/disable 与 post-check；不得手动执行 wrapper/N3/N4/N5，不执行 rollback，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/trade。停用后交接 N3_20260612_B2_TRACE_ALIGNED_STANDARD_OUTBOX_DATES_CONTRACT_COMPATIBILITY_REPAIR_GATE。
```
