# N4 Worker Bounded Smoke Larger Scope Readiness

Result: `READINESS_PASS`

## Prerequisite Proof

```text
planning=PLANNING_PASS
scoped consumption smoke=POST_REVIEW_PASS
expanded consumption smoke=POST_REVIEW_PASS
TriggerMatched semantic smoke=POST_REVIEW_PASS
Pending+StateChanged semantic fixture smoke=POST_REVIEW_PASS
idempotency / duplicate / retry smoke=POST_REVIEW_PASS
JSONB serialization fix=FIX_PASS
execute runner alignment=ALIGNMENT_PASS
trigger semantic runner alignment=ALIGNMENT_PASS
idempotency runner alignment=ALIGNMENT_PASS
```

Covered N4 paths:

```text
TriggerMatched=true
TriggerPendingMarketData=true
TriggerStateChanged=true
idempotency / duplicate / retry=true
```

N3 outbox status was not updated in prior smoke probes, N5/N6 refs remain zero, and no long-running worker was started.

## Existing Smoke Boundary

Existing smoke rows remain scoped to their own run_id / consumer:

```text
scoped_consumption run/quality/state/match/outbox/inbox/checkpoint=1/2/0/0/0/5/5
expanded_consumption run/quality/state/match/outbox/inbox/checkpoint=1/2/0/0/0/50/50
trigger_matched_semantic run/quality/state/match/outbox/inbox/checkpoint=1/2/10/10/10/10/10
pending_state_changed_semantic run/quality/state/match/outbox/inbox/checkpoint=1/2/6/0/8/6/6
idempotency_duplicate_retry run/quality/state/match/outbox/inbox/checkpoint=1/2/0/0/0/9/9
```

Where N4 outbox rows exist, they remain pending:

```text
trigger_matched_semantic pending=10, delivered/delivering=0
pending_state_changed_semantic pending=8, delivered/delivering=0
```

Selected N3 source events for existing smoke rows remain pending, and existing smoke N5/N6 refs remain zero.

## Larger Source Readiness

Source:

```text
source_run_id=realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
source_layer=N3_market_data
event_type=MarketSnapshotUpdated
source_trade_date=20260608
```

Read-only proof:

```text
N3 MarketSnapshotUpdated pending=2155
delivered/delivering=0
proposed selected source events=100
selected pending=100/100
event_id/event_schema_version/dedup_key/partition_key/payload_json present=100/100
payload trace present=100/100
distinct event_id/dedup_key/partition_key=100/100/100
outbox locked/updated/consumed=false
```

## Proposed Larger Scope

```text
smoke_run_id=n4_worker_bounded_smoke_20260608_larger_scope_probe
consumer_name=n4_trigger_worker_v1_bounded_smoke_larger_scope_probe
max_events=100
max_runtime_seconds=180
heartbeat_interval_seconds=10
status_json=docs/N4_WORKER_BOUNDED_SMOKE_20260608_LARGER_SCOPE_PROBE_STATUS.json
stop_file=tmp/n4_worker_bounded_smoke_20260608_larger_scope_probe.stop
mode=consumption-only by default
```

Expected future writes if execute is authorized by a later gate:

```text
common_trigger_run=1
common_trigger_quality_item=as planned
common_event_inbox<=100
common_event_consumer_checkpoint<=accepted partitions
common_trigger_state/common_trigger_match/common_event_outbox=according to dry-run plan
```

Expected no writes:

```text
N3 outbox status update=0
N5/N6=0
delivery/push/voice/mobile=0
sim/position/order/trade/real_trade=0
```

## Baseline Clean Proof

Target new run:

```text
run/quality/state/match/outbox/inbox/checkpoint=0/0/0/0/0/0/0
N5 refs=0
N6/user refs=0
active worker heartbeat/status evidence=0
```

## Safety Requirements

```text
must remain bounded by max_events / max_runtime / stop_file / status_json
must not start long-running worker
must not update or consume N3 outbox
must not enter N5/N6
must not consume N5 outbox
must not delivery/push/voice/mobile
must not sim/position/pnl/real_trade
must not proposal/order/trade
must not touch old system
rollback must be generated for exact run_id/consumer before execute
semantic fixture requires explicit contract and not_new_market_decision=true
```

## Quality

```text
P0/P1/P2=0/1/0
```

P1 is advisory: this readiness is consumption-only by default and is not long-running worker approval.

## Forbidden Scope

This gate did not generate an execute fixture, execute smoke, write DB rows, consume/update N3 outbox, enter N5/N6, start worker, touch delivery/push/voice/mobile, sim/position/pnl/real_trade, proposal/order/trade, or the old system.

## Validation

```text
JSON parse PASS
live baseline proof PASS
current smoke boundary proof PASS
source event pending proof PASS
code support static scan PASS
downstream refs scan PASS
rollback requirement proof PASS
git diff --check PASS
```

Next gate:

```text
N4_WORKER_BOUNDED_SMOKE_LARGER_SCOPE_CONTRACT_GATE
```
