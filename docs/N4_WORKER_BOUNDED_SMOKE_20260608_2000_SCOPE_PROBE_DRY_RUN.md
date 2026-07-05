# N4 Worker Bounded Smoke 2000 Scope Dry Run

Result: `DRY_RUN_PASS`

## Scope

```text
smoke_run_id=n4_worker_bounded_smoke_20260608_2000_scope_probe
consumer_name=n4_trigger_worker_v1_bounded_smoke_2000_scope_probe
source_run_id=realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
source_event_type=MarketSnapshotUpdated
source_trade_date=20260608
max_events=2000
max_runtime_seconds=900
mode=consumption-only
```

## Source Proof

```text
N3 MarketSnapshotUpdated total=2155
pending=2155
delivered/delivering=0/0
selected source events=2000
selected pending=2000/2000
selected not pending=0
event_id/dedup_key/partition_key/event_schema_version/payload_json=2000/2000
payload trace fields=2000/2000
distinct event_id/dedup_key=2000/2000
existing consume keys for target consumer=0
```

N3 outbox was not locked, updated, or consumed.

## Dry-Run Summary

```text
accepted_source_event_count=2000
skipped_duplicate_source_event_count=0
transition_event_plan_count=0
TriggerMatched=0
TriggerPendingMarketData=0
TriggerStateChanged=0
semantic_smoke=false
fixture_only=false
not_new_market_decision=true
N5 entry=0
```

This is a consumption-only bounded smoke plan. It validates source selection, JSON-safe consumption planning, inbox/checkpoint scope, and bounded controls. It does not fabricate trigger events.

## Planned Write Scope If Future Execute Is Authorized

```text
common_trigger_run=1
common_trigger_quality_item=2
common_event_inbox=2000
common_event_consumer_checkpoint=2000
common_trigger_state=0
common_trigger_match=0
common_event_outbox=0
N3 outbox status update=0
N5/N6 refs=0
```

## Baseline

```text
target baseline run/quality/state/match/outbox/inbox/checkpoint=0/0/0/0/0/0/0
downstream refs=0
status_json exists=false
```

## Quality

```text
P0/P1/P2=0/1/0
```

P1 is advisory: this consumption-only probe is not long-running worker approval.

