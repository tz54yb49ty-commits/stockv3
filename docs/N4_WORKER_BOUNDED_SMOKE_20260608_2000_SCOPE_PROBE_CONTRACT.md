# N4 Worker Bounded Smoke 2000 Scope Contract

Result: `CONTRACT_PASS`

## Contract Scope

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

## Proof Summary

```text
readiness=READINESS_PASS
dry-run=DRY_RUN_PASS
target baseline total=0
selected pending events=2000/2000
transition_event_plan_count=0
TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=0/0/0
```

## Planned Writes

```text
common_trigger_run=1
common_trigger_quality_item=2
common_event_inbox=2000
common_event_consumer_checkpoint=2000
common_trigger_state=0
common_trigger_match=0
common_event_outbox=0
```

Expected no writes:

```text
N3 outbox status update=0
N5/N6 refs=0
delivery/push/voice/mobile=0
sim/position/order/trade/real_trade=0
```

## Contract Requirements

```text
execute requires --execute
execute requires --user-confirmed
execute requires explicit --smoke-run-id
execute requires clean target baseline
execute requires selected source events remain pending
execute must not update N3 outbox
execute must not enter N5/N6
execute must not fabricate trigger events
semantic_smoke=false
fixture_only=false
not_new_market_decision=true
N5 entry=0
```

## Rollback

```text
rollback_sql=sql/N4_worker_bounded_smoke_20260608_2000_scope_probe_rollback.sql
hard-fail before first DELETE/UPDATE=true
guards delivered/delivering=true
guards downstream refs=true
rollback_not_executed=true
```

## Quality

```text
P0/P1/P2=0/1/0
blockers=[]
```

P1 is advisory: this is not long-running worker approval.

