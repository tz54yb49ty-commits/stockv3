# N6 026 Canonical User Projection Schema Alignment Post-Review

Status: POST_REVIEW_PASS

Layer role: N6_user

Date: 2026-05-29

Scope: post-review registration for the executed 026 N6 canonical user
projection schema alignment migration.

```text
migration_executed=true
database=ashare_v3
database_user=ashare_v3_user
host=127.0.0.1
port=5432
n5_outbox_consumed=false
n5_outbox_status_updated=false
user_projection_business_rows_written=false
notification_business_rows_written=false
session_written=false
decision_written=false
watchlist_written=false
sim_written=false
worker_started=false
push_voice_mobile=false
position_real_trade=false
n1_to_n5_writeback=false
```

## Migration

Executed migration:

```text
sql/026_n6_canonical_user_projection_schema_alignment.sql
```

Rollback remains available:

```text
sql/026_n6_canonical_user_projection_schema_alignment_rollback.sql
```

The migration touched only N6 projection schema tables:

```text
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
```

No N1/N2/N3/N4/N5 table, N5 outbox, inbox, checkpoint, action fact, trigger
fact, market fact, condition fact, user session, user decision, watchlist, sim,
voice/mobile, position, or real trade table was touched by this migration.

## Schema Readiness Summary

Canonical trace columns exist.

`user_signal_projection`:

```text
source_action_event_type
action_state
action_mark
condition_key
original_condition_key
trace_json
projection_policy
```

`user_signal_card` and `user_notification_queue`:

```text
source_action_event_id
source_action_event_type
action_state
action_mark
condition_key
original_condition_key
trace_json
projection_policy
```

Canonical constraints now support:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

Legacy compatibility remains:

```text
ActionEvent
HintEvent
```

Canonical notification sources now support:

```text
n5_action_eligible
n5_action_blocked
n5_action_executed
n5_action_skipped
```

Legacy notification sources remain:

```text
n5_action_event
n5_hint_event
```

Canonical action indexes exist:

```text
idx_user_signal_projection_canonical_action
idx_user_signal_card_canonical_action
idx_user_notification_queue_canonical_action
```

PostgreSQL truncated several long CHECK constraint names in the executed
schema, but their definitions are present and match the canonical compatibility
contract.

## Boundary Summary

N5 outbox remained unchanged after migration:

```text
ActionBlocked pending=4309
ActionBlocked delivered=0
ActionBlocked delivering=0
ActionEligible pending=0
ActionExecuted pending=0
ActionSkipped pending=0
legacy ActionEvent pending=0
legacy HintEvent pending=0
legacy RiskEvent pending=0
legacy PositionEvent pending=0
```

20260529 action run N6 refs remain zero:

```text
user_projection_run=0
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
```

Existing projection table totals are historical 20260525 legacy data, not new
026 writes:

```text
user_projection_run=1
user_signal_projection=488
user_signal_card=488
user_notification_queue=488
```

Forbidden N6 business tables remain unchanged for this gate:

```text
user_signal_decision=0
user_watchlist=0
user_watchlist_item=0
user_sim_order=0
user_sim_trade=0
user_sim_position=0
```

## Rollback Safety

Rollback guard probe is zero for all 026 canonical guards:

```text
user_projection_run=0
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
```

Therefore 026 schema rollback is currently available. If future canonical N6
projection rows are written, schema rollback must be blocked until a reviewed
business rollback by `user_projection_run_id` removes those rows.

Rollback must not touch N5 outbox, N5 action facts, N4/N3/N2/N1 facts, user
accounts, sessions, voice/mobile state, sim execution state, or real trading.

## Decision

POST_REVIEW_PASS.

Allowed next gate:

```text
N6 canonical dry-run runner alignment
```

Still blocked:

```text
N6 projection execute
N5 outbox consumption/status update
user decision/session/watchlist/sim writes
worker
push/voice/mobile
position/real trade
N1-N5 writeback
```
