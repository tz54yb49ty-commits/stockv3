# N3/N4/N5 20260612 Realtime Auto Chain Scheduler Reactivation After B2 Midday Policy Repair

Result: `BLOCKED`

Generated at: `2026-06-12T13:16:09+08:00`

## Reactivation

Approved command executed:

```bash
launchctl bootstrap gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

Exit code: `0`

## What Cleared

The previous B2 fact-only midday projection-time blocker is cleared.

- N3 auto-poll status: `passed`
- B2 fact-only projection until `1307`: return code `0`
- B2 fact-only projection rows: `2082`

## Current Blocker

Ownership: `N3_market_data`

Blocked stage: N3-B2 trace-aligned standard outbox realtime projection.

Error:

```text
RealtimeProjectionExecuteError: N3-B2 blocked: projection rows by asset differ from contract
```

The B1 standard outbox for `until_1307` succeeded and wrote `2082` `MarketSnapshotUpdated` rows, but trace-aligned B2 blocked before writing projection facts or an execute report.

Contract expected distribution:

- ready rows: `297`
- ready by asset: `stock/index/board=245/33/19`
- not-ready rows: `1785`
- not-ready by asset: `stock/index/board=1627/50/108`

Dry-run still has `expected_distribution=null`; execute contract has a materialized expected distribution. The runner-built rows differ by asset from the contract and validation blocks before write.

## Boundary Proof

- Standard outbox until `1307`: total `2082`, pending `2082`, delivered/delivering `0/0`
- Inbox/checkpoint refs for this outbox: `0/0`
- Trace-aligned B2 rows: `0/0/0`
- N4 refs: `0`
- N5 refs: `0`
- N6/voice/mobile/sim/trade: not touched
- No rollback executed
- No manual wrapper/N3/N4/N5 command was run by this gate

## Safe Stop Recommendation

The scheduler remains loaded and started another automatic pass after the first pass blocked. Stop before repair:

```bash
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

This gate did not execute stop.

## Next Prompt

```text
layer_role=runtime_control。

进入 N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_STOP_AFTER_TRACE_ALIGNED_B2_DISTRIBUTION_BLOCKED_GATE。

目标：在 reactivation 后 BLOCKED 于 N3-B2 trace-aligned projection rows by asset differ from contract 后，scoped 停用 com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll。只允许执行 launchctl bootout/disable 与 post-check；不得手动执行 wrapper/N3/N4/N5，不执行 rollback，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/trade。停用后交接 N3_20260612_B2_TRACE_ALIGNED_STANDARD_OUTBOX_EXPECTED_DISTRIBUTION_REPAIR_GATE。
```
