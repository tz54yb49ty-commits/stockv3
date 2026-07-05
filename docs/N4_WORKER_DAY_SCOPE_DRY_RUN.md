# N4 Worker Day-Scope Dry-Run

Result: `DRY_RUN_PASS`

This runtime-control gate generated a day-scope dry-run and readiness artifact only. It did not start a worker, execute N4, write database rows, consume/update N3/N4/N5 outbox/inbox/checkpoint, enter N4/N5/N6 execute, run rollback SQL, or touch delivery, sim, trade, or the old system.

## Prerequisite Proof

Required upstream evidence parsed successfully:

- rollout policy contract=`CONTRACT_PASS`
- bounded rollout registration refresh=`REGISTRATION_PASS`
- 2000 scope smoke post-review=`POST_REVIEW_PASS`
- continuous state transition contract=`CONTRACT_PASS`
- current policy forbids long-running worker start=true
- current policy forbids N3 outbox status update=true
- this gate no-write / no-execute=true

## Day-Scope Source Proof

Target source:

- source_run_id=`realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- source_event_type=`MarketSnapshotUpdated`
- source_trade_date=`20260608`

Read-only source proof:

- N3 `MarketSnapshotUpdated` total=`2155`
- pending/delivered/delivering=`2155/0/0`
- distinct event_id/dedup_key/partition_key=`2155/2155/2155`
- asset_kind distribution stock/index/board=`1945/83/127`
- event_time min=`2026-06-08 09:44:21.069286+08`
- event_time max=`2026-06-08 15:00:00+08`
- event_id/dedup_key/partition_key/event_schema_version/payload_json present=`2155/2155`
- payload trace subscription_id/pull_plan_id/run_id/source_adapter/data_quality_status/snapshot_id present=`2155/2155`
- source snapshot fact counts stock/index/board=`1945/83/127`
- N3 outbox status unchanged; no lock, no update, no consume.

## Dry-Run Plan

Consumption-only day-scope plan:

- accepted_source_event_count=`2155`
- skipped_duplicate_source_event_count expected=`0`
- transition_event_plan_count=`0`
- TriggerMatched=`0`
- TriggerPendingMarketData=`0`
- TriggerStateChanged=`0`
- common_trigger_state=`0`
- common_trigger_match=`0`
- common_event_outbox=`0`
- expected common_event_inbox rows if future bounded execute is authorized=`2155`
- expected checkpoint rows if future bounded execute is authorized=`2155`
- semantic_smoke=`false`
- fixture_only=`false`
- not_new_market_decision=`true`
- N5 entry=`0`

This dry-run does not fabricate trigger events. It is only a full-day N3 source consumption planning pass.

## Throughput / Lag Estimate

The 2000 scope bounded smoke is the empirical capacity baseline:

- 2000 scope execute wrote common_event_inbox/checkpoint=`2000/2000`
- max_runtime_seconds in that bounded contract=`900`
- elapsed runtime seconds were not recorded in the execute report, so exact events/sec is not asserted.

Day total events=`2155`.

With max_events=`2000`, projected chunks=`2`:

- chunk 1: 2000 events
- chunk 2: 155 events

Recommended next contract strategy:

- Either authorize one day-scope bounded execute with max_events >= 2155, max_runtime_seconds around 1200, heartbeat 10s.
- Or keep max_events=2000 and use two chunked bounded executes with unique run_id/consumer per chunk, preserving rollback isolation.

Later contract should include lag metrics:

- source_event_time_min/max
- last_processed_event_time
- checkpoint_partition_count
- processed_event_count
- processed_per_second
- duplicate_skip_count
- retry_count
- error_count
- checkpoint_lag_by_partition

## Baseline / Conflict Proof

Proposed future dry-run lineage:

- proposed_run_id=`n4_worker_day_scope_dry_run_20260608_consumption_only_probe`
- proposed_consumer_name=`n4_trigger_worker_v1_day_scope_dry_run_probe`

Target baseline rows are all zero:

- common_trigger_run=`0`
- common_trigger_quality_item=`0`
- common_trigger_state=`0`
- common_trigger_match=`0`
- common_event_outbox=`0`
- common_event_inbox=`0`
- common_event_consumer_checkpoint=`0`

Downstream refs for the proposed lineage are `0`. Existing smoke rows are registered evidence and are not a blocker because this proposed lineage uses a distinct run_id and consumer.

## Policy Decision

The day-scope dry-run can pass because source proof is clean and P0=`0`.

This does not authorize:

- long-running N4 worker
- N3 outbox status update or consumption policy change
- N5 worker
- N4 outbox consumption by N5
- N6, delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade

Any future day-scope execute must enter a separate bounded contract / preflight / final gate with rollback SQL.

## P0/P1/P2

- P0=`0`
- P1=`2`
- P2=`0`

P1 items:

- day total 2155 exceeds the latest successful single bounded max_events baseline of 2000; future execute must either raise max_events in a separate contract or use chunked run_id/consumer lineages.
- 2000 scope execute report does not expose elapsed runtime seconds; later contract should add elapsed_seconds, processed_per_second, and lag metrics.

## Forbidden Scope Proof

This gate did not execute write SQL or mutation SQL, did not write database rows, did not consume/update N3/N4/N5 outbox/inbox/checkpoint, did not enter N4/N5/N6 execute, did not start a worker, did not run rollback SQL, and did not touch delivery/push/voice/mobile, sim/position/pnl/real_trade, proposal/order/trade, or the old system.

## Validation

- referenced artifacts parse=`PASS`
- live day-source proof=`PASS`
- dry-run plan consistency=`PASS`
- policy consistency=`PASS`
- forbidden scope proof=`PASS`
- JSON parse=`PASS`
- git diff --check=`PASS`

Recommended next gate:

`N4_WORKER_DAY_SCOPE_BOUNDED_CONTRACT_GATE`
