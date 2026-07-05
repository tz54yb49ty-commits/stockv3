# N3 20260612 B2 Dates Contract Compatibility Repair Post-Review And Reactivation Final Gate

Result: `PASS`

Post-review: `POST_REVIEW_PASS`

## Repair Proof

Repair artifact:

```text
docs/N3_20260612_B2_TRACE_ALIGNED_STANDARD_OUTBOX_DATES_CONTRACT_COMPATIBILITY_REPAIR.json
```

Repair result:

```text
REPAIR_PASS
```

Confirmed root cause:

```text
trace-aligned B2 artifacts and materializer temp contract omitted dates.source_trade_date
while realtime_projection_execute.py requires contract.dates.source_trade_date.
```

Code paths reviewed:

```text
scripts/run_n3_n4_n5_realtime_chain_once.py
tests/test_n3_n4_n5_realtime_chain_once.py
```

## Artifact Refresh Proof

Checked `UNTIL_1307` and `UNTIL_1333` B2 dry-run / execute contract / preflight JSON.

All contain:

```text
dates.for_trade_date=20260612
dates.source_trade_date=20260611
dates.prev_trade_date=20260611
```

Preserved surface:

```text
expected rows stock/index/board=1872/83/127
expected total=2082
expected_distribution present in contract/preflight
projection_time_policy preserved
writes_outbox=false
rollback_sql_path preserved
```

## Validation

```text
targeted tests: 49 OK
compileall: PASS
repair JSON parse: PASS
prior stop JSON parse: PASS
artifact dates assertion: PASS
```

## Scheduler Stopped Proof

```text
label=com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll
plist=/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
plutil -lint=PASS
launchctl print rc=113
state=not_loaded/service_not_found
wrapper/N3/N4/N5 process count=0
```

## Reactivation Command Draft

Allowed only in the next reactivation gate:

```bash
launchctl bootstrap gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

Stop command registry:

```bash
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

## Forbidden Scope Proof

This gate did not:

```text
start scheduler
manually execute wrapper/N3/N4/N5
write DB
execute rollback
consume/update outbox/inbox/checkpoint
enter N6
touch voice/mobile/sim/trade
```

## Decision

Allowed next gate:

```text
N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_REACTIVATION_GATE_AFTER_B2_DATES_CONTRACT_REPAIR
```

## Next Prompt

```text
layer_role=runtime_control。

进入 N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_REACTIVATION_GATE_AFTER_B2_DATES_CONTRACT_REPAIR。

目标：按 final gate approved command scoped bootstrap com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll，然后只读观察 latest chain report 是否不再因 N3-B2 trace-aligned contract dates.source_trade_date missing BLOCK。只允许执行 launchctl bootstrap 与 post-check；不得手动执行 wrapper/N3/N4/N5，不执行 rollback，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/trade。
```
