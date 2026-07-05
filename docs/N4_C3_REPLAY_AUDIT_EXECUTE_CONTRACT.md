# N4 C3 Replay Audit Execute Contract

- result: `DESIGN_PASS`
- layer_role: `N4_trigger`
- stage: `N4-C3-replay-audit-execute-contract-design`
- contract_version: `n4.c3_replay_audit_execute.v1`
- execution_shape: `audit_only_run_once`
- generated_at: `2026-05-26`

## Purpose

This contract defines a future N4 C3 replay audit execute. It records the
already-passed C3 replay dry-run diff as audit facts, without consuming C3
outbox and without emitting live N4 trigger events.

The initial execute shape is intentionally not a replay consumer. It is a
bounded audit materialization of the reviewed dry-run result.

## Lineage Inputs

Required lineage:

```text
replay_run_id =
  trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b

source_c3_run_id =
  minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_c2b_run_id =
  closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_n4_projection_run_id =
  trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249

trigger_context_run_id =
  trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_n5_action_run_id =
  action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
```

The C3 run id must be explicit. No latest-run lookup, wildcard lookup, date
prefix lookup, or non-allowlisted C3 source is allowed.

## Input Boundary

Allowed read-only inputs:

```text
allowlisted C3 MinuteBarClosed pending outbox rows
C2B closed signal enrichment facts
current N4 trigger_context_snapshot
original N4 projection matcher trigger results
N5 current-real action run id as nullable trace only
```

Forbidden as consumption input:

```text
B1 MarketSnapshotUpdated outbox
B2 realtime projection facts as replay decision input
old synthetic N4 outbox
N5 outbox
non-allowlisted C3 outbox
raw minute tables
external market adapters
old system
```

B2 projection facts may appear only as `trace_only` evidence already captured
by dry-run artifacts. They must not change replay audit classification.

## Allowed Future Execute Writes

Audit-only execute may write only:

```text
common_trigger_run
common_trigger_quality_item
stock_trigger_replay_audit
index_trigger_replay_audit
board_trigger_replay_audit
```

`common_trigger_run.raw_json` should carry replay audit counts because the
current trigger run schema has no dedicated replay audit row counter. Expected
formal counters for live trigger facts must remain:

```text
trigger_state_row_count = 0
trigger_match_row_count = 0
trigger_event_outbox_count = 0
```

`common_trigger_quality_item.layer_scope` must use existing values such as
`trigger_run` or `event_contract`, with
`details.metric_scope = c3_replay_audit`.

## Forbidden Future Execute Writes

The audit execute must not write:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
common_trigger_match
common_trigger_state
N3 snapshot/projection/minute/C2/C2B/C3 facts
N3 C3 outbox status
N5 action facts/events/outbox
N6 user projection
action/user/voice/mobile/sim/position/real trade tables
worker state
```

## Outbox Policy

No N4 outbox may be emitted in v1.

Specifically forbidden:

```text
TriggerMatched
TriggerPendingMarketData
TriggerCleared
```

Reason: standard N4 outbox events are live N5-consumable events. Reusing them
for C3 replay could trigger a second action path.

If replay events are later required, they must be designed separately as a
replay-specific event such as:

```text
TriggerReplayDiff
```

That future event requires a separate additive event contract, schema review,
N5 replay allowlist, and user confirmation.

## Idempotency

Replay audit rows must be idempotent by:

```text
replay_run_id + comparison_key
```

The comparison key must encode:

```text
asset_kind
identity_key
direction
signal_type
condition_key
trigger_period
trigger_bucket
```

Repeated execute with the same `replay_run_id` must either be blocked by a run
gate or produce no duplicate audit rows.

## Preflight Requirements

Before future execute:

```text
018 schema migration review passed
018 migration executed and audit tables exist
C3 replay dry-run report is DRY_RUN_PASS
C3 pending input remains 17432
C3 delivered/delivering remains 0
C2B enrichment rows remain available
current N4 projection matcher run remains passed
current N5 action run remains passed
target replay_run_id does not exist in common_trigger_run
target replay_run_id has zero replay audit rows
target replay_run_id has zero common_event_outbox / inbox / checkpoint rows
rollback SQL has been generated and reviewed
```

## Expected Audit Counts From Current Dry-Run

The current expected audit materialization is:

```text
audit rows total = 35970
would_match = 4734
would_clear = 245
would_change = 243
unchanged = 30730
missing = 18
not_ready = 0
```

The execute runner must explain any difference from these counts before commit.

## Rollback Strategy

Business rollback path:

```text
sql/N4_C3_replay_audit_business_rollback.sql
```

Rollback deletes only the target replay run's audit materialization:

```text
stock_trigger_replay_audit
index_trigger_replay_audit
board_trigger_replay_audit
common_trigger_quality_item
common_trigger_run
```

Rollback must refuse to proceed if the target replay run has any:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
```

Rollback must not touch original N4/N5/C3/N3 runtime.

## Next Gates

Allowed after this design:

```text
N4 018 trigger replay audit migration review
```

Still blocked:

```text
018 migration execute
N4 C3 replay audit execute runner implementation
N4 C3 replay audit execute
C3 outbox consumption
N4 standard outbox emission
N5 replay consumption
N6 execution
worker
```
