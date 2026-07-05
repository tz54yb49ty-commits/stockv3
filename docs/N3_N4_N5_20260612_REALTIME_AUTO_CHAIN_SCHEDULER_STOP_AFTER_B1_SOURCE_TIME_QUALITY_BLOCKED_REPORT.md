# N3/N4/N5 20260612 Realtime Auto Chain Scheduler Stop After B1 Source-Time Quality Block

Result: `STOP_PASS`

Generated at: `2026-06-12T10:18:26+08:00`

This runtime-control gate executed only the scoped `launchctl bootout` command and post-checks. It did not manually execute wrapper/N3/N4/N5, did not execute rollback SQL, did not consume or update outbox/inbox/checkpoint, and did not enter N6 / voice / mobile / sim / trade.

## Stop Proof

Target:

```text
label=com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll
plist=/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

Pre-stop state:

```text
launchctl_state=loaded_running
runs_observed_before_stop=5
last_exit_code_before_stop=2
active chain/wrapper/B1 process = 1/1/1
active B1 run at stop = realtime_daily_snapshot_20260612_until_1014__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1
```

Executed:

```bash
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

Result:

```text
exit_code=0
launchctl_print_exit_code=113
state=not_loaded_service_not_found
wrapper/child process count after stop=0
```

## Blocker Registry

Owner: `N3_market_data`

Current blocker:

```text
stage=N3_B1_fact_only_realtime_snapshot
primary_quality_gate=n3_b1_source_time_untrusted_label
```

The scheduler was stopped because repeated automatic passes were generating failed B1 fact-only rows. B1 count mismatch is cleared; the active issue is index/board source-time semantics.

## DB Boundary Proof

Read-only DB proof:

```text
event_outbox_20260612 = []
event inbox refs for 20260612 outbox = 0
event checkpoint refs for 20260612 outbox = 0
N4 production runs = 0
N5 runs = 0
```

Failed B1 runs already created before this stop:

```text
until_1005: status=failed, P0/P1/P2=1/2/0, stock/index/board snapshot=1872/2/0, quality=219, outbox=0
until_1008: status=failed, P0/P1/P2=1/2/0, stock/index/board snapshot=1872/2/0, quality=219, outbox=0
until_1011: status=failed, P0/P1/P2=1/2/0, stock/index/board snapshot=1872/2/0, quality=219, outbox=0
```

Interrupted run at stop:

```text
until_1014: status=running, finished_at=null, fact_written=false
stock/index/board snapshot=1281/2/0
quality=208
outbox=0
rollback_sql=sql/N3_B1_realtime_snapshot_20260612_until_1014_rollback.sql
```

This gate did not execute cleanup or rollback.

## Forbidden Scope Proof

```text
manual_wrapper_executed=false
manual_N3/N4/N5_executed=false
rollback_executed=false
outbox/inbox/checkpoint consumed_or_updated_by_this_gate=false
N6 entered=false
voice/mobile/sim/trade touched=false
old_system_touched=false
only scoped launchctl bootout executed=true
```

## Decision

`STOP_PASS`: scheduler is stopped. Do not proceed to N4/N5.

Next gate should repair N3-B1 fact-only source-time semantics and create/review cleanup for failed/interrupted B1 runs.

## Next Prompt

```text
layer_role=N3_market_data。

进入 N3_20260612_B1_FACT_ONLY_SOURCE_TIME_SEMANTICS_POLICY_AND_FAILED_RUN_CLEANUP_GATE。

目标：修复 20260612 N3-B1 fact-only auto-poll 的 source_time semantics policy，使 fact-only B1 对 index/board 的 untrusted period label 采用 reviewed policy（例如 observed_at normalization 或 fact-only quality downgrade policy），并生成 failed/interrupted B1 runs 的 cleanup/rollback plan。要求：不启动 scheduler，不手动执行 wrapper/N3/N4/N5，不进入 N4/N5/N6，不消费/update outbox/inbox/checkpoint，不触碰 voice/mobile/sim/trade。必须只读登记 1005/1008/1011 failed runs 与 1014 interrupted running run，生成/复核 scoped cleanup SQL，hard-fail before DELETE/UPDATE，确认 outbox/inbox/checkpoint/N4/N5/N6 refs 为 0。
```
