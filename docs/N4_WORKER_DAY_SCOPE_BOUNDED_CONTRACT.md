# N4 Worker Day-Scope Bounded Contract

Result: `CONTRACT_PASS`

This runtime-control gate generated and reviewed day-scope bounded consumption-only execute artifacts. It did not start a worker, execute N4, write database rows, consume/update N3/N4/N5 outbox/inbox/checkpoint, enter N4/N5/N6 execute, run rollback SQL, or touch delivery, sim, trade, or the old system.

## Prerequisite Proof

- day-scope dry-run=`DRY_RUN_PASS`
- rollout policy contract=`CONTRACT_PASS`
- registration refresh=`REGISTRATION_PASS`
- 2000 scope smoke post-review=`POST_REVIEW_PASS`
- continuous state transition contract=`CONTRACT_PASS`
- P0=`0`
- current policy forbids long-running worker=true
- current policy forbids N3 outbox status update=true

## Source Readiness Proof

- N3 `MarketSnapshotUpdated total=2155`
- pending/delivered/delivering=`2155/0/0`
- distinct event_id/dedup_key/partition_key=`2155/2155/2155`
- asset distribution stock/index/board=`1945/83/127`
- payload trace coverage present=`2155/2155`
- source snapshot fact counts stock/index/board=`1945/83/127`
- selected source events=`2155`
- selected source events pending=`2155`
- N3 outbox not locked, not updated, not consumed.

## Selected Contract Strategy

Selected strategy: `single_bounded_day_scope_execute`

- run_id=`n4_worker_day_scope_bounded_20260608_consumption_only_probe`
- consumer_name=`n4_trigger_worker_v1_day_scope_bounded_probe`
- max_events=`2155`
- max_runtime_seconds=`1200`
- heartbeat_interval_seconds=`10`
- stop_file=`tmp/n4_worker_day_scope_bounded_20260608_consumption_only_probe.stop`
- status_json=`docs/N4_WORKER_DAY_SCOPE_BOUNDED_STATUS.json`

Reason: runner supports parameterized `max_events`, and current policy requires bounded controls rather than a 2000-event ceiling. A single bounded execute covers the full pending day source and avoids unnecessary chunk lineage complexity.

## Contract / Preflight Proof

- contract=`CONTRACT_PASS`
- preflight=`PREFLIGHT_PASS`
- dry-run plan consistent with day-scope dry-run=true
- accepted_source_event_count=`2155`
- skipped_duplicate_source_event_count expected=`0`
- TriggerMatched=`0`
- TriggerPendingMarketData=`0`
- TriggerStateChanged=`0`
- common_trigger_state=`0`
- common_trigger_match=`0`
- common_event_outbox=`0`
- common_event_inbox=`2155`
- common_event_consumer_checkpoint=`2155`
- N5 entry=`0`
- no fabricated trigger events=true

## Planned Write Scope

Only if a later execute user-confirmation gate authorizes execution:

- common_trigger_run=`1`
- common_trigger_quality_item=`2`
- common_event_inbox=`2155`
- common_event_consumer_checkpoint=`2155`
- common_trigger_state=`0`
- common_trigger_match=`0`
- common_event_outbox=`0`
- N3 outbox status update=`0`
- N5/N6 refs=`0`

## Baseline Clean Proof

Target scoped rows are all zero:

- common_trigger_run=`0`
- common_trigger_quality_item=`0`
- common_trigger_state=`0`
- common_trigger_match=`0`
- common_event_outbox=`0`
- common_event_inbox=`0`
- common_event_consumer_checkpoint=`0`

Downstream refs for target run/consumer are `0`. Existing smoke rows are registered evidence and are not a blocker because this contract uses a distinct run_id and consumer.

## Bounded Controls Proof

- max_events covers selected source count=true
- max_runtime_seconds bounded=true
- heartbeat_interval_seconds <= 10=true
- stop_file exists=false
- status_json under docs=true
- worker_started=false
- long_running_worker_started=false
- smoke runner is not approved as a long-running worker=true

## Rollback Proof

Rollback SQL:

`sql/N4_worker_day_scope_bounded_20260608_consumption_only_probe_rollback.sql`

- scoped to exact run_id / consumer_name=true
- hard-fail before first DELETE/UPDATE=true
- guards N4 outbox delivered/delivering=true
- guards N5/N6/user/sim/order/trade/position refs=true
- deletes only scoped day-scope bounded rows if future rollback is separately authorized=true
- preserves N3 facts/outbox and existing smoke lineages=true
- no CASCADE/DROP/TRUNCATE=true
- rollback not executed=true

## P0/P1/P2

- P0=`0`
- P1=`1`
- P2=`0`

P1: prior 2000-scope execute report did not expose elapsed runtime / throughput fields. Later post-review must not assert events/sec unless the execute report emits it.

## Forbidden Scope Proof

This gate did not start worker, execute N4, write database rows, consume/update N3/N4/N5 outbox/inbox/checkpoint, enter N4/N5/N6 execute, run rollback SQL, touch delivery/push/voice/mobile, sim/position/pnl/real_trade, proposal/order/trade, or the old system.

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_n4_worker_bounded_smoke_once.py \
  --contract-path docs/N4_WORKER_DAY_SCOPE_BOUNDED_CONTRACT.json \
  --smoke-run-id n4_worker_day_scope_bounded_20260608_consumption_only_probe \
  --consumer-name n4_trigger_worker_v1_day_scope_bounded_probe \
  --source-run-id realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --source-event-type MarketSnapshotUpdated \
  --source-trade-date 20260608 \
  --max-events 2155 \
  --max-runtime-seconds 1200 \
  --heartbeat-interval-seconds 10 \
  --stop-file tmp/n4_worker_day_scope_bounded_20260608_consumption_only_probe.stop \
  --status-json docs/N4_WORKER_DAY_SCOPE_BOUNDED_STATUS.json \
  --json-report-path docs/N4_WORKER_DAY_SCOPE_BOUNDED_EXECUTE_REPORT.json \
  --markdown-report-path docs/N4_WORKER_DAY_SCOPE_BOUNDED_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_worker_day_scope_bounded_20260608_consumption_only_probe_rollback.sql \
  --execute \
  --user-confirmed
```

Allowed next gate:

`N4_WORKER_DAY_SCOPE_BOUNDED_EXECUTE_USER_CONFIRMATION_GATE`
