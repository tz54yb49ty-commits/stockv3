# N4 Worker Bounded Polling Cross-Run Idempotency Repair Post Review

Result: `POST_REVIEW_PASS`

Layer role: `runtime_control`

Generated at: `2026-06-11T18:27:49+08:00`

## Repair Proof

- repair result: `FIX_PASS`
- duplicate blocker: `uq_common_event_inbox_consumer_event`
- root cause: polling repeatedly selected the first pending N3 `MarketSnapshotUpdated` events while N4 intentionally leaves N3 outbox status pending; existing consume key lookup did not recognize already processed `consumer_name|event_id` values
- repaired source selection: `fetch_source_events_for_smoke(..., consumer_name=...)`
- selection now excludes current consumer rows already present in:
  - `common_event_inbox`
  - `common_event_consumer_checkpoint`
- repaired consume key lookup: `fetch_existing_consume_keys`
- canonical consume key shape: `consumer_name|event_id`
- N3 outbox status update path added: `false`
- smoke runner now passes `args.consumer_name` into source selection: `true`

## Idempotency Proof

- first successful polling pass rows retained:
  - `common_trigger_run=1`
  - `common_trigger_quality_item=2`
  - `common_event_inbox=50`
  - `common_event_consumer_checkpoint=50`
  - `common_trigger_state=0`
  - `common_trigger_match=0`
  - `common_event_outbox=0`
- N3 source boundary:
  - `MarketSnapshotUpdated pending=2100`
  - delivered/delivering rows: `0`
  - N3 outbox consumed or updated: `false`
- live helper proof:
  - existing consume keys: `50`
  - next selected unprocessed events: `50`
  - selected distinct event ids: `50`
  - selected intersects existing consume keys: `false`
- duplicate inbox unique key prevented: `true`

## Scheduler Stopped Proof

- stop result: `STOP_PASS`
- label: `com.ashare-v3.n4.bounded-polling`
- plist: `/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n4.bounded-polling.plist`
- fresh `launchctl print` exit code: `113`
- fresh state: `not_loaded`
- active wrapper / child process count: `0`

## Validation Summary

- targeted unittest: `PASS`, 45 tests
- command: `PYTHONPATH=src:scripts python3 -m unittest tests.test_n4_worker_bounded_smoke tests.test_n4_worker_bounded_poll_once tests.test_n4_worker_state_transition`
- compileall: `PASS`
- command: `python3 -m compileall src/ashare_v3/trigger/worker_consumer.py scripts/run_n4_worker_bounded_smoke_once.py tests/test_n4_worker_bounded_smoke.py`
- repair report JSON parse: `PASS`
- stop report JSON parse: `PASS`
- fresh launchctl not-loaded check: `PASS`
- fresh process check: `PASS`
- `git diff --check`: `PASS`

## Forbidden Scope Proof

- scheduler installed or enabled: `false`
- launchd modified: `false`
- wrapper executed: `false`
- N4 child runner executed: `false`
- database written: `false`
- N3 outbox consumed or updated: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- rollback SQL executed: `false`
- N5 entered: `false`
- N6 entered: `false`
- long-running worker started: `false`
- delivery/push/voice/mobile touched: `false`
- trade/sim/position/PnL touched: `false`
- old system touched: `false`

## Decision

- duplicate inbox blocker cleared: `true`
- allow next gate: `true`
- next gate: `N4_WORKER_BOUNDED_POLLING_SCHEDULER_REACTIVATION_FINAL_GATE_REVIEW_AFTER_IDEMPOTENCY_REPAIR`

## Next Prompt

```text
layer_role=runtime_control。

进入 N4_WORKER_BOUNDED_POLLING_SCHEDULER_REACTIVATION_FINAL_GATE_REVIEW_AFTER_IDEMPOTENCY_REPAIR。

目标：
在 N4 bounded polling cross-run idempotency repair 已 POST_REVIEW_PASS 且 scheduler 当前 not_loaded 后，只读复核是否允许进入 N4_trigger scheduler reactivation 用户确认点。
不得安装/启用 scheduler，不得执行 wrapper/N4，不得写数据库，不得消费/update outbox/inbox/checkpoint，不得进入 N5/N6。

输出：
PASS / BLOCKED
final gate findings
reactivation command draft
stop command registry
idempotency repair proof
forbidden scope proof
是否允许进入 N4_WORKER_BOUNDED_POLLING_SCHEDULER_REACTIVATION_GATE_AFTER_IDEMPOTENCY_REPAIR
next prompt
```
