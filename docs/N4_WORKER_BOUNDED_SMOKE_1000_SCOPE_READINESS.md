# N4 Worker Bounded Smoke 1000 Scope Readiness

Result: `READINESS_PASS`

## Prerequisite Proof

```text
rollout registration refresh=REGISTRATION_PASS
500 scope smoke=POST_REVIEW_PASS
rollback readiness=READINESS_PASS
larger scope smoke=POST_REVIEW_PASS
TriggerMatched semantic smoke=POST_REVIEW_PASS
Pending+StateChanged semantic fixture smoke=POST_REVIEW_PASS
idempotency / duplicate / retry smoke=POST_REVIEW_PASS
JSONB serialization fix=FIX_PASS
runner alignment=ALIGNMENT_PASS
semantic source selection alignment=ALIGNMENT_PASS
state persistence dedup fix=FIX_PASS
idempotency runner alignment=ALIGNMENT_PASS
```

Existing smoke rows are already registered evidence and are not blockers for the new 1000-scope run because the target `smoke_run_id` and `consumer_name` are distinct.

## Source Readiness

Source:

```text
source_run_id=realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
source_layer=N3_market_data
event_type=MarketSnapshotUpdated
source_trade_date=20260608
```

Live read-only proof:

```text
N3 MarketSnapshotUpdated total=2155
pending=2155
delivered/delivering=0/0
selected source events=1000
selected pending=1000/1000
selected not pending=0
event_id/dedup_key/partition_key/event_schema_version/payload_json present=1000/1000
distinct event_id/dedup_key=1000/1000
```

Payload trace proof:

```text
run_id=1000/1000
snapshot_id=1000/1000
pull_plan_id=1000/1000
subscription_id=1000/1000
source_adapter=1000/1000
data_quality_status=1000/1000
payload event_schema_version=1000/1000
```

N3 outbox was not locked, updated, or consumed.

## Baseline Proof

Target:

```text
smoke_run_id=n4_worker_bounded_smoke_20260608_1000_scope_probe
consumer_name=n4_trigger_worker_v1_bounded_smoke_1000_scope_probe
```

Live baseline:

```text
common_trigger_run=0
common_trigger_quality_item=0
common_trigger_state=0
common_trigger_match=0
common_event_outbox=0
common_event_inbox=0
common_event_consumer_checkpoint=0
N5/N6/downstream refs=0
status_json exists=false
```

## Existing Smoke Boundary

Existing registered smoke rows remain scoped:

```text
scoped_consumption run/quality/state/match/outbox/inbox/checkpoint=1/2/0/0/0/5/5
expanded_consumption run/quality/state/match/outbox/inbox/checkpoint=1/2/0/0/0/50/50
larger_scope_consumption run/quality/state/match/outbox/inbox/checkpoint=1/2/0/0/0/100/100
500_scope_consumption run/quality/state/match/outbox/inbox/checkpoint=1/2/0/0/0/500/500
trigger_matched_semantic run/quality/state/match/outbox/inbox/checkpoint=1/2/10/10/10/10/10
pending_state_changed_semantic run/quality/state/match/outbox/inbox/checkpoint=1/2/6/0/8/6/6
idempotency_duplicate_retry run/quality/state/match/outbox/inbox/checkpoint=1/2/0/0/0/9/9
```

Where N4 outbox rows exist:

```text
trigger_matched_semantic pending/delivered/delivering=10/0/0
pending_state_changed_semantic pending/delivered/delivering=8/0/0
```

Existing smoke downstream business refs remain `0`.

## Proposed 1000 Scope Smoke

```text
smoke_run_id=n4_worker_bounded_smoke_20260608_1000_scope_probe
consumer_name=n4_trigger_worker_v1_bounded_smoke_1000_scope_probe
max_events=1000
max_runtime_seconds=600
heartbeat_interval_seconds=10
status_json=docs/N4_WORKER_BOUNDED_SMOKE_20260608_1000_SCOPE_PROBE_STATUS.json
stop_file=tmp/n4_worker_bounded_smoke_20260608_1000_scope_probe.stop
mode=consumption-only by default
```

Expected future writes if execute is later authorized:

```text
common_trigger_run=1
common_trigger_quality_item=as planned by contract
common_event_inbox<=1000
common_event_consumer_checkpoint<=accepted partitions
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
fabricated trigger events=0
```

This gate does not approve a long-running worker.

## Safety Requirements

```text
must remain bounded by max_events / max_runtime / stop_file / status_json
must not long-run
must not update or consume N3 outbox
must not enter N5/N6
must not consume/update N5 outbox
must not delivery/push/voice/mobile
must not sim/position/pnl/real_trade
must not proposal/order/trade
must not touch old system
rollback must be generated for exact run_id/consumer before execute
semantic fixture requires explicit contract with fixture_only=true and not_new_market_decision=true
```

## Rollback Planning

Future rollback SQL must be:

```text
path=sql/N4_worker_bounded_smoke_20260608_1000_scope_probe_rollback.sql
scoped smoke_run_id=n4_worker_bounded_smoke_20260608_1000_scope_probe
scoped consumer=n4_trigger_worker_v1_bounded_smoke_1000_scope_probe
hard-fail before first DELETE/UPDATE
guard N4 outbox delivered/delivering
guard N5/N6/user/sim/order/trade/position refs
preserve N3 facts/outbox and existing smoke lineages
no CASCADE/DROP/TRUNCATE
```

This readiness gate does not authorize rollback execution.

## Quality

```text
P0/P1/P2=0/1/0
```

P1 is advisory: this is consumption-only readiness and still not long-running worker approval.

## Forbidden Scope

This gate did not start worker, execute N4, write database rows, consume/update N3 outbox, enter N5/N6, touch delivery/push/voice/mobile, sim/position/pnl/real_trade, proposal/order/trade, or the old system.

## Validation

```text
JSON parse PASS
live source readiness proof PASS
target baseline proof PASS
existing smoke boundary proof PASS
downstream refs scan PASS
rollback requirement proof PASS
git diff --check PASS
```

Next gate:

```text
N4_WORKER_BOUNDED_SMOKE_1000_SCOPE_CONTRACT_GATE
```
