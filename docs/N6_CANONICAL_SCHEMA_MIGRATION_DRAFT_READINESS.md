# N6 Canonical Schema Migration Draft Readiness

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-05-29

This readiness artifact covers only the N6 canonical schema alignment draft:

```text
migration_executed=false
database_written=false
n5_outbox_consumed=false
n5_outbox_status_updated=false
user_projection_written=false
notification_written=false
session_written=false
decision_written=false
sim_written=false
voice_mobile_push=false
real_trade=false
worker_started=false
```

## Inputs

Authoritative runtime specs:

```text
docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md
docs/N5_CANONICAL_ACTION_FLOW_v0.1.md
```

Current N6 and N5 evidence:

```text
docs/N6_PROJECTION_CONTRACT.md
docs/N6_PROJECTION_EXECUTE_CONTRACT.md
docs/N6_USER_PROJECTION_SCHEMA_READINESS.md
docs/N5_20260529_CANONICAL_ACTION_EXECUTE_REPORT.md
docs/N5_20260529_canonical_action_execute_report.json
```

## Migration Files

```text
sql/026_n6_canonical_user_projection_schema_alignment.sql
sql/026_n6_canonical_user_projection_schema_alignment_rollback.sql
```

Business rollback for future projection rows remains:

```text
sql/N6_projection_business_rollback.sql
```

## Touched Tables

The migration draft touches only:

```text
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
```

It does not touch user accounts, sessions, decisions, watchlists, sim tables,
N5 outbox/inbox/checkpoint, or any N1-N5 fact table.

## Constraint Alignment

The draft widens legacy event checks from:

```text
ActionEvent
HintEvent
```

to legacy plus canonical compatibility:

```text
ActionEvent
HintEvent
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

`user_notification_queue.notification_source` is widened to include:

```text
n5_action_eligible
n5_action_blocked
n5_action_executed
n5_action_skipped
```

while preserving:

```text
index_signal
board_signal
stock_filter_signal
n5_action_event
n5_hint_event
```

`user_signal_card.card_type` and `card_status` are widened to represent
canonical blocked, action-confirmed, skipped, and informational display states.

## Additive Nullable Columns

`user_signal_projection` gains nullable canonical trace columns:

```text
source_action_event_type
action_state
action_mark
condition_key
original_condition_key
trace_json
projection_policy
```

`user_signal_card` and `user_notification_queue` gain the same trace columns
and also:

```text
source_action_event_id
```

No provider delivery, voice/mobile push, sim execution, position execution, or
real trade columns are added.

## Indexes

The draft adds source/action lookup indexes for canonical projection review:

```text
idx_user_signal_projection_canonical_action
idx_user_signal_card_canonical_action
idx_user_notification_queue_canonical_action
```

These indexes are read/query support only and do not imply outbox consumption.

## DML Scan

The migration draft contains no business DML:

```text
INSERT=false
UPDATE=false
DELETE=false
TRUNCATE=false
COPY=false
```

It uses DDL only:

```text
ALTER TABLE
CREATE INDEX IF NOT EXISTS
DROP CONSTRAINT
DROP INDEX in rollback only
```

## Readiness Decision

The draft resolves the schema blocker that prevented canonical N6 planning:

```text
020 schema/runner legacy-only ActionEvent / HintEvent support
```

It does not resolve runner alignment. After migration review/final gate, N6
still needs a canonical dry-run runner update before any projection execute can
be considered.

## Rollback Readiness

Schema rollback is guarded and blocks if canonical N6 projection values exist.
If canonical projection rows exist, use the business rollback by
`user_projection_run_id` first.

Business rollback order remains:

```text
user_notification_queue
user_signal_card
user_signal_projection
user_projection_run
```

It must block if linked `user_signal_decision` or `user_sim_*` rows exist.
No rollback path may touch N5 outbox, N5 action facts, N4/N3/N2/N1 facts,
accounts, sessions, voice/mobile state, sim execution state, or real trade.

## Remaining Blockers

```text
N6 migration not executed
N6 canonical dry-run runner not implemented
N6 canonical execute not authorized
N5 outbox consumption not authorized
voice/mobile/sim/real trade disabled
worker disabled
```

Allowed next gate:

```text
N6 canonical schema migration final gate
```
