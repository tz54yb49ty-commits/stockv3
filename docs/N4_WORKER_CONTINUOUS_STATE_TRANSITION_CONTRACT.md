# N4 Worker Continuous State Transition Contract

Result: `CONTRACT_PASS`

Gate: `N4_WORKER_CONTINUOUS_STATE_TRANSITION_CONTRACT_GATE`

Layer role: `runtime_control`

This gate only defines the N4 continuous monitoring, state transition, idempotency, bounded worker smoke, and rollback contract. It does not start a worker, execute N4, write the database, enter N5/N6, consume/update outbox, or touch voice/push/mobile/sim/position/order/real trade.

## Scope

N4 worker may continuously consume N3 standard market events and approved N3 projection facts only after a later implementation/final gate. The initial worker path must be bounded smoke. Long-running worker operation is explicitly out of scope.

Canonical inputs:

```text
MarketSnapshotUpdated
N3 standardized realtime projection facts
N3 action-confirmation projection facts when approved by current trigger contract
localized N4 trigger_context_snapshot
```

Optional quality/strong-confirmation inputs, only when a later gate enables them:

```text
MarketDataDelayed
MarketDataMissing
MinuteBarClosed / closed 30m summary
```

Forbidden inputs:

```text
external market APIs
raw unclosed minute bars assembled by N4
N1/N2 raw historical K as high-frequency path
N5/N6 facts
old system data
```

## N3 Outbox / N4 Inbox Contract

N4 must not update N3 outbox status.

```text
N4 must not mutate common_event_outbox rows produced by N3.
N4 must not ack by changing N3 outbox delivered/delivering state.
N4 maintains its own common_event_inbox rows and common_event_consumer_checkpoint watermark.
consumer_name=n4_trigger_worker_v1
```

N4 inbox/checkpoint keys:

```text
inbox idempotency key=consumer_name + source_event_id
checkpoint key=consumer_name + partition_key
checkpoint payload includes:
  last_event_id
  last_event_time
  last_source_run_id
  last_source_layer
  processed_event_count
  bounded_smoke_run_id
```

Failure policy:

```text
A failed event is recorded as N4 quality/inbox failure without advancing checkpoint past that event unless the failure is explicitly classified as safe-skip.
```

## N4 Idempotency Keys

Three separate idempotency layers are required:

```text
source_event_consume_key =
  consumer_name:n4_trigger_worker_v1 | source_event_id

trigger_state_key =
  trade_date | asset_kind | identity_key | direction | signal_type | condition_key

trigger_match_dedup_key =
  trade_date | asset_kind | identity_key | direction | signal_type |
  condition_key | primary_trigger_period | trigger_mark_candidate |
  match_basis | source_market_event_or_projection_id

trigger_pending_dedup_key =
  trade_date | asset_kind | identity_key | direction | signal_type |
  condition_key | expected_primary_trigger_period | trigger_mark_candidate |
  missing_evidence_kind | source_market_event_or_projection_id

trigger_state_changed_dedup_key =
  state_key | previous_status | current_status | previous_trigger_live |
  trigger_live | previous_primary_trigger_period | primary_trigger_period |
  previous_projection_30m_type | projection_30m_type |
  state_change_reason | source_event_id
```

Requirements:

```text
Re-consuming the same source event must not create duplicate TriggerMatched, TriggerPendingMarketData, or TriggerStateChanged rows.
TriggerMatched may be emitted only once for the same dedup key.
TriggerPendingMarketData may be emitted only when evidence is insufficient and the pending dedup key has not already been recorded.
TriggerStateChanged may be emitted only for material state changes; repeated no-op state evaluation must not emit a new event.
```

## State Machine

Canonical states:

```text
inactive:
  trigger_live=false
  n5_entry_allowed=false

pending_market_data:
  trigger_live=false
  n5_entry_allowed=false

matched:
  trigger_live=true
  n5_entry_allowed=true
```

State transitions:

```text
inactive -> pending_market_data:
  emit TriggerPendingMarketData + TriggerStateChanged
  condition=N2 context exists, N3 evidence insufficient
  N5 entry=false

pending_market_data -> matched:
  emit TriggerMatched + TriggerStateChanged
  condition=missing evidence becomes sufficient and a new trigger fact is established
  N5 entry=true

inactive -> matched:
  emit TriggerMatched + TriggerStateChanged
  condition=evidence sufficient on first evaluation and a new trigger fact is established
  N5 entry=true

matched -> inactive:
  emit TriggerStateChanged only
  condition=trigger condition becomes inactive, trigger_live=false, or source quality invalidates live state
  N5 entry=false

pending_market_data -> inactive:
  emit TriggerStateChanged only
  condition=candidate expires or source condition/state becomes inactive before evidence is sufficient
  N5 entry=false

matched -> matched:
  emit TriggerStateChanged only
  condition=same trigger remains live but period/projection/mark/quality/source trace materially changes
  N5 entry=no new N5 entry unless a distinct TriggerMatched dedup key is created
```

Period priority:

```text
Y > Q > M > W > D
```

Period rules:

```text
Within the same trade date, primary_trigger_period may upgrade according to priority.
A downgrade is permitted only when the previous stronger period becomes invalid and must emit TriggerStateChanged(state_change_reason=period_downgrade).
Any primary_trigger_period change must carry previous_primary_trigger_period and previous_all_trigger_periods.
```

Projection rules:

```text
projection_30m_flag false -> true is TriggerStateChanged.
projection_30m_type none/unknown -> volume_up/shrink_down is TriggerStateChanged.
projection_30m_type volume_up/shrink_down -> none/unknown is TriggerStateChanged and may set trigger_live=false if matched evidence is no longer valid.
trigger_mark_candidate normal/30m_volume/30m_shrink changes are TriggerStateChanged.
```

## Event Rules

### TriggerMatched

```text
writes_common_trigger_match=true
trigger_live=true
current_status=matched
n5_entry_allowed=true
```

Emit only when a new trigger fact is established and the `trigger_match_dedup_key` has not been written.

Required payload top-level fields:

```text
trigger_price
trigger_kind
triggered_periods
all_trigger_periods
primary_trigger_period
trigger_live
current_status
n5_entry_allowed
match_basis
projection_30m_flag
projection_30m_type
trigger_mark_candidate
```

### TriggerPendingMarketData

```text
writes_common_trigger_match=false
trigger_live=false
current_status=pending_market_data
n5_entry_allowed=false
```

Emit only when N2 context exists and evidence is insufficient. N5 must treat it as no-op / quality-only / state-gate.

Required payload top-level fields:

```text
missing_evidence_kind
expected_required_data_kind
trigger_live
current_status
n5_entry_allowed
data_quality_status
```

### TriggerStateChanged

```text
writes_common_trigger_match=false
is_n5_action_entry=false
```

Emit only for material changes in:

```text
current_status
trigger_live
primary_trigger_period / all_trigger_periods
projection_30m_flag / projection_30m_type
trigger_mark_candidate
data_quality_status
source trace
```

Required payload top-level fields:

```text
trigger_live
previous_trigger_live
current_status
previous_status
primary_trigger_period
previous_primary_trigger_period
all_trigger_periods
previous_all_trigger_periods
projection_30m_flag
projection_30m_type
previous_projection_30m_flag
previous_projection_30m_type
previous_trigger_mark_candidate
state_change_reason
source_outcome_event_type
source_outcome_event_id
```

`TriggerStateChanged` never writes `common_trigger_match` and never starts N5 action confirmation.

## Bounded Worker Smoke Contract

Status:

```text
contract_only_not_implemented
long_running_worker_allowed=false
```

Required bounded controls:

```text
max_events
max_runtime_seconds
stop_file
status_json
heartbeat_interval_seconds
consumer_checkpoint
recent_event_summary
error_count
lag_metrics
dry_run_mode
execute_requires_user_confirmed
```

Allowed future write scope for an execute smoke, after implementation/final gate only:

```text
common_trigger_run
common_trigger_quality_item
common_trigger_state
common_trigger_match
common_event_outbox for N4 events
common_event_inbox for N4 consumer only
common_event_consumer_checkpoint for N4 consumer only
```

Forbidden future write scope:

```text
N3 facts
common_event_outbox status update for N3 events
N5 action facts/events
N6 projection/user tables
voice/push/mobile
sim/position/order/real trade
old system
```

Bounded smoke command draft, not runnable in this gate:

```bash
PYTHONPATH=src:scripts python3 scripts/run_n4_worker_bounded_smoke_once.py \
  --contract-path docs/N4_WORKER_CONTINUOUS_STATE_TRANSITION_CONTRACT.json \
  --consumer-name n4_trigger_worker_v1 \
  --max-events 50 \
  --max-runtime-seconds 120 \
  --heartbeat-interval-seconds 10 \
  --stop-file tmp/n4_worker_bounded_smoke.stop \
  --status-json docs/N4_WORKER_BOUNDED_SMOKE_STATUS.json \
  --json-report-path docs/N4_WORKER_BOUNDED_SMOKE_REPORT.json \
  --markdown-report-path docs/N4_WORKER_BOUNDED_SMOKE_REPORT.md \
  --execute \
  --user-confirmed
```

The script is a future implementation target. Do not run this draft until implementation, preflight, rollback, and final gate review pass.

## Rollback Requirements

Rollback SQL is required before any bounded execute smoke.

Hard requirements:

```text
hard-fail before DELETE
guard N5 action refs
guard N6 refs
guard delivered/delivering N4 outbox refs
guard N4 inbox refs consumed by downstream
guard N4 checkpoint refs beyond target smoke run
guard active worker heartbeat/running status
guard voice/push/mobile/sim/position/order/real trade refs
```

Rollback delete scope:

```text
N4 smoke run_id only
N4 trigger_state rows created by smoke run, or revert state to previous snapshot
N4 trigger_match rows created by smoke run
N4 outbox events created by smoke run
N4 inbox/checkpoint rows for smoke consumer and smoke run only
N4 quality rows for smoke run
```

Rollback must not touch:

```text
N1/N2 facts
N3 facts
N3 outbox status
N5/N6
old system
```

## Implementation Gate Requirements

Allowed next gate:

```text
N4_WORKER_BOUNDED_SMOKE_IMPLEMENTATION_GATE
```

Expected implementation files:

```text
src/ashare_v3/trigger/worker_state_transition.py
src/ashare_v3/trigger/worker_consumer.py
scripts/run_n4_worker_bounded_smoke_once.py
tests/test_n4_worker_state_transition.py
tests/test_n4_worker_bounded_smoke.py
sql/N4_worker_bounded_smoke_rollback.sql
```

Required tests:

```text
TriggerPendingMarketData never writes common_trigger_match and never sets n5_entry_allowed=true.
TriggerStateChanged never writes common_trigger_match and is never N5 action entry.
pending -> matched emits TriggerMatched + TriggerStateChanged idempotently.
matched -> inactive emits TriggerStateChanged only.
period upgrade/downgrade emits exactly one TriggerStateChanged per material change.
projection_30m state change emits exactly one TriggerStateChanged per material change.
re-consuming same N3 event does not duplicate N4 facts/events.
N4 consumer writes only N4 inbox/checkpoint and never updates N3 outbox status.
bounded smoke blocks missing --execute or --user-confirmed before DB write.
bounded smoke respects max_events, max_runtime_seconds, stop_file, and status_json.
```

## Decision

```text
contract_status=CONTRACT_PASS
allow_bounded_worker_smoke_implementation_gate=true
allow_start_worker_now=false
allow_n4_execute_now=false
allow_n5_n6=false
```
