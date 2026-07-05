# N3/N4/N5 20260612 Realtime Auto Chain Scheduler Reactivation After B2 Calculation Config Repair

Result: `BLOCKED`

Generated at: `2026-06-12T12:09:10+08:00`

## Reactivation

Approved command executed:

```bash
launchctl bootstrap gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

Exit code: `0`

## What Cleared

The previous B2 trace-aligned `calculation_method` blocker is cleared. The generated B2 execute contract now contains:

- `calculation_method=active_30m_bucket_projection_v1_strict_current_lineage`
- `calculation_config_hash=c0e47d3beec744930c098fae1a083fc1da95f9752bb2efc01dc76b3ed4d92b1d`

## Current Blocker

Ownership: `N3_market_data`

Blocked stage: `N3-B2 fact-only realtime projection`

Error:

```text
RealtimeProjectionExecuteError: N3-B2 blocked: snapshot_time outside trading buckets: 2026-06-12 12:05:35.615051+08:00
```

This occurred before B1 standard outbox, N4, or N5 for the reactivated pass.

The policy gap is that B2 fact-only auto-poll has `projection_time_policy=null`. During the midday break, B1 fact snapshot uses observed time around `12:05`, which is outside B2 trading buckets. B2 then blocks in `projection_window_for_snapshot`.

## Stage Proof

- N3 auto-poll: `blocked`
- latest closed minute: `2026-06-12T11:30:00+08:00`
- B1 fact: return code `0`, rows `1872/83/127`
- C1: return code `0`, minute rows `35343`
- B2 fact projection: return code `1`, report not written
- N4/N5: not entered

## Boundary Proof

- No manual wrapper/N3/N4/N5 execution by this gate
- No rollback
- No outbox/inbox/checkpoint consumption or update by this gate
- No N6/voice/mobile/sim/trade

## Safe Stop Recommendation

The scheduler remains loaded and will retry every 60 seconds. Recommended next step is scoped stop before N3 repair:

```bash
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

This gate did not execute stop.

## Next Prompt

```text
layer_role=runtime_control。

进入 N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_STOP_AFTER_B2_PROJECTION_TIME_POLICY_BLOCKED_GATE。

目标：在 reactivation 后 BLOCKED 于 N3-B2 fact-only projection_time outside trading buckets during midday 后，scoped 停用 com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll。只允许执行 launchctl bootout/disable 与 post-check；不得手动执行 wrapper/N3/N4/N5，不执行 rollback，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/trade。停用后交接 N3_20260612_B2_FACT_ONLY_PROJECTION_TIME_POLICY_MIDDAY_REPAIR_GATE。
```
