# N3/N4/N5 20260612 Realtime Auto Chain Scheduler Stop After Trace-Aligned B2 Distribution Blocker

Result: `STOP_PASS`

Generated at: `2026-06-12T13:20:59+08:00`

## Stop Execution

Scoped command executed:

```bash
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

Exit code: `0`

## Pre-Stop State

- Plist lint: `PASS`
- Scheduler state: `running`
- Observed runs: `2`
- Last exit code: `2`
- Active pass was running B1 standard outbox `until_1314`

## Post-Stop Proof

- `launchctl print`: `rc=113`, service not found
- State: `not_loaded`
- wrapper/N3/N4/N5 process count: `0`

## Blocked Context

Ownership: `N3_market_data`

Blocked stage: `N3-B2 trace-aligned standard outbox realtime projection`

Error:

```text
RealtimeProjectionExecuteError: N3-B2 blocked: projection rows by asset differ from contract
```

The latest chain report remains:

- report: `docs/N3_N4_N5_REALTIME_CHAIN_REPORT_20260612.json`
- result: `BLOCKED`
- blocked reason: `n3_b2_trace_aligned_projection_failed`

## Boundary Proof

- No manual wrapper/N3/N4/N5 execution
- No rollback
- No outbox consumption/update by this gate
- No inbox/checkpoint update by this gate
- No N6/voice/mobile/sim/trade

## Next Prompt

```text
layer_role=N3_market_data。

进入 N3_20260612_B2_TRACE_ALIGNED_STANDARD_OUTBOX_EXPECTED_DISTRIBUTION_REPAIR_GATE。

目标：修复 20260612 N3-B2 trace-aligned standard outbox expected_distribution / rows-by-asset contract compatibility。当前 reactivation 在 B1 standard outbox until_1307 写出 2082 条 MarketSnapshotUpdated 后，N3-B2 因 projection rows by asset differ from contract BLOCK。不得启动 scheduler，不手动执行 wrapper/N3/N4/N5，不写数据库，不执行 rollback，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/trade。验证 targeted tests、compileall、JSON parse、forbidden scope scan、git diff --check。
```
