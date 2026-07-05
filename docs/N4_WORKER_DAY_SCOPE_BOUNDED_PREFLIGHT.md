# N4 Worker Day-Scope Bounded Preflight

Result: `PREFLIGHT_PASS`

Target:

- run_id=`n4_worker_day_scope_bounded_20260608_consumption_only_probe`
- consumer_name=`n4_trigger_worker_v1_day_scope_bounded_probe`
- source_event_type=`MarketSnapshotUpdated`
- source_trade_date=`20260608`
- mode=`consumption-only`

## Source Preflight

- accepted_source_event_count=`2155`
- pending/delivered/delivering=`2155/0/0`
- distinct event_id/dedup_key=`2155/2155`
- selected max_events covers source count=true
- N3 outbox update/consume=false

## Baseline Clean Proof

- common_trigger_run=`0`
- common_trigger_quality_item=`0`
- common_trigger_state=`0`
- common_trigger_match=`0`
- common_event_outbox=`0`
- common_event_inbox=`0`
- common_event_consumer_checkpoint=`0`
- downstream refs=`0`

## Planned Write Scope

Only if a later execute user-confirmation gate authorizes execution:

- common_trigger_run=`1`
- common_trigger_quality_item=`2`
- common_event_inbox=`2155`
- common_event_consumer_checkpoint=`2155`
- common_trigger_state=`0`
- common_trigger_match=`0`
- common_event_outbox=`0`

## Bounded Controls

- max_events=`2155`
- max_runtime_seconds=`1200`
- heartbeat_interval_seconds=`10`
- stop_file exists=false
- worker_started=false
- long_running_worker_started=false

This preflight does not authorize long-running worker, N3 outbox status update, N5 worker, N4 outbox consumption, N6, delivery, sim, or trade.
