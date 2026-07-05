# N3/N4/N5 20260612 Realtime Auto Chain Scheduler Reactivation After B1 Source-Time Policy And Cleanup

Result: `BLOCKED`

Generated at: `2026-06-12T11:16:12+08:00`

## Reactivation

Approved command executed:

```bash
launchctl bootstrap gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

Exit code: `0`

Scheduler loaded successfully. First observed automatic pass exited with `last exit code=1`. At report time the scheduler had already started a second automatic pass, so this gate recommends an immediate scoped stop gate before repair.

## Progress Before Block

The previous B1 source-time / cleanup blocker is cleared.

- N3 auto-poll status: `passed`
- latest closed minute: `2026-06-12T11:07:00+08:00`
- B1 fact run: `EXECUTE_PASS`, rows `stock/index/board=1872/83/127`
- C1 today minute run: return code `0`, minute rows `28809`
- B2 fact projection run: return code `0`, projection rows `2082`
- B1 standard outbox: `EXECUTE_PASS`, `MarketSnapshotUpdated=2082`

N4 and N5 were not entered.

## Blocker

Ownership: `N3_market_data`

Blocked stage: N3-B2 trace-aligned standard outbox artifact builder.

The wrapper crashed before writing a fresh chain report:

```text
KeyError: 'calculation_method'
scripts/run_n3_n4_n5_realtime_chain_once.py default_artifact_builder -> materialize_b2_expected_distribution
src/ashare_v3/market/realtime_projection_execute.py build_projection_row calculation_config['calculation_method']
```

Root cause summary: the chain wrapper builds a temporary trace-aligned B2 projection contract whose `calculation_config` lacks `calculation_method`. The B2 row builder requires that field.

## Boundary Proof

- No manual wrapper/N3/N4/N5 execution by this gate
- No rollback
- No outbox/inbox/checkpoint consumption or update by this gate
- N4/N5 not entered
- N6/voice/mobile/sim/trade not touched

## Safe Stop Recommendation

The scheduler remains loaded and has already begun another automatic pass. Recommended next gate is a scoped stop:

```bash
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

This gate did not execute stop because it was only authorized to bootstrap and post-check.

## Next Prompt

```text
layer_role=runtime_control。

进入 N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_STOP_AFTER_B2_TRACE_ALIGNED_CALCULATION_CONFIG_BLOCKED_GATE。

目标：在 reactivation 后 BLOCKED 于 N3-B2 trace-aligned expected-distribution calculation_config.calculation_method 后，scoped 停用 com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll。只允许执行 launchctl bootout/disable 与 post-check；不得手动执行 wrapper/N3/N4/N5，不执行 rollback，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/trade。停用后交接 N3_20260612_B2_TRACE_ALIGNED_STANDARD_OUTBOX_CALCULATION_CONFIG_COMPATIBILITY_REPAIR_GATE。
```
