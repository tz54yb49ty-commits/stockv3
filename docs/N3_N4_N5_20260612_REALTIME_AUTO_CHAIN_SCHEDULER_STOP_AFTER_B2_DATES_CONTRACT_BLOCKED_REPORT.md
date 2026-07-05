# N3-N4-N5 20260612 Scheduler Stop After B2 Dates Contract Blocker

Result: `STOP_PASS`

## Stop Proof

Stopped scoped LaunchAgent:

```text
label=com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll
bootout exit code=0
post-stop launchctl rc=113
state=not_loaded/service_not_found
wrapper/N3/N4/N5 process count=0
```

## Blocker Registry

The previous rows-by-asset blocker was cleared. The latest automatic pass reached B2 write preparation and then blocked on:

```text
KeyError: source_trade_date
```

Owner:

```text
N3_market_data
```

Blocked stage:

```text
N3-B2 trace-aligned standard outbox realtime projection
```

Required handoff:

```text
N3_20260612_B2_TRACE_ALIGNED_STANDARD_OUTBOX_DATES_CONTRACT_COMPATIBILITY_REPAIR_GATE
```

## Row Boundary Proof

```text
B1 standard outbox rows=2082
B1 standard outbox pending=2082
B1 delivered/delivering=0/0
B2 common_market_data_run=0
B2 quality=0
B2 projection stock/index/board=0/0/0
B2 outbox/inbox/checkpoint refs=0/0/0
N4 refs=0
N5 refs=0
```

## Forbidden Scope Proof

This gate did not manually execute wrapper/N3/N4/N5, did not execute rollback, did not consume/update outbox/inbox/checkpoint, did not enter N6, and did not touch voice/mobile/sim/trade.

## Next Prompt

```text
layer_role=N3_market_data。

进入 N3_20260612_B2_TRACE_ALIGNED_STANDARD_OUTBOX_DATES_CONTRACT_COMPATIBILITY_REPAIR_GATE。

目标：修复 20260612 N3-B2 trace-aligned standard outbox contract dates compatibility。当前 reactivation 已清除 rows-by-asset blocker，但 B2 在写入 projection facts 前因 contract["dates"]["source_trade_date"] 缺失 BLOCK；要求 contract/dry-run/preflight 补齐 source_trade_date（应为 20260611）并保留 for_trade_date/prev_trade_date/projection_time_policy/expected_distribution 不变。不得启动 scheduler，不手动执行 wrapper/N3/N4/N5，不写数据库，不执行 rollback，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/trade。验证 targeted tests、compileall、JSON parse、forbidden scope scan、git diff --check。
```
