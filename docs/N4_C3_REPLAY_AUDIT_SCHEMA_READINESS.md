# N4 C3 Replay Audit Schema Readiness

- result: `DESIGN_PASS`
- layer_role: `N4_trigger`
- stage: `N4-C3-replay-audit-schema-design`
- schema_path: `sql/018_trigger_replay_audit_schema.sql`
- schema_rollback_path: `sql/018_trigger_replay_audit_rollback.sql`
- business_rollback_path: `sql/N4_C3_replay_audit_business_rollback.sql`
- generated_at: `2026-05-26`

## Purpose

This design adds an N4 audit-only fact surface for C3 `MinuteBarClosed` replay
diffs after C2B closed signal enrichment. It does not turn replay results into
live trigger facts and does not make them consumable by N5.

Current dry-run evidence:

```text
C3 accepted = 17432
C2B enrichment rows read = 17432
comparison candidates = 35970
would_match = 4734
would_clear = 245
would_change = 243
unchanged = 30730
missing = 18
not_ready = 0
P0/P1/P2 = 0/1/0
closed_signal_status_missing = 0
```

## Schema Design

The schema adds three physical replay audit fact tables:

```text
stock_trigger_replay_audit
index_trigger_replay_audit
board_trigger_replay_audit
```

Each table includes:

```text
replay_audit_id
replay_run_id
source_c3_run_id
source_c2b_run_id
source_n4_projection_run_id
source_trigger_context_run_id
source_condition_run_id
source_n5_action_run_id
for_trade_date
trade_date
asset_kind
identity_key
exchange
code
name
condition_key
signal_type
direction
trigger_period
trigger_bucket
replay_classification
replay_diff_type
original_trigger_status
closed_signal_status
closed_signal_quality_status
projection_signal_status
original_match_id
c3_event_id
c2b_enrichment_id
comparison_key
diff_json
trace_json
quality_status
created_at
```

The physical split keeps stock/index/board facts separate. The audit tables
store trace ids as evidence but do not create dependencies on N5 action tables
or standard N4 outbox rows.

## Enum Contract

`replay_classification`:

```text
would_match
would_clear
would_change
unchanged
missing
not_ready
```

`replay_diff_type`:

```text
projection_not_matched_but_closed_matched
projection_matched_but_closed_not_matched
both_matched_but_quality_changed
unchanged
replay_blocked
```

Replay signal scope is limited to:

```text
B_BUY_30M_VOL
BUY_HINT
S_SELL_30M_SHRINK
SELL_HINT
```

`trigger_period` is fixed to `30m` in this first audit schema.

## Keys And Indexes

Idempotency key:

```text
UNIQUE(replay_run_id, comparison_key)
```

Indexes:

```text
replay_run_id
source_c3_run_id
source_c2b_run_id
replay_classification
replay_diff_type
signal_type
identity_key + trade_date
```

## Strictly Additive Plan

The migration is intended to be strictly additive:

```text
CREATE TABLE IF NOT EXISTS only
CREATE INDEX IF NOT EXISTS only
no ALTER TABLE
no INSERT / UPDATE / DELETE / TRUNCATE
no common_event_outbox / inbox / checkpoint writes
no common_trigger_match / state writes
no N5/N6 objects
no worker objects
```

`common_trigger_quality_item.layer_scope` is not altered. Future replay quality
items should use existing layer scopes such as `trigger_run` or `event_contract`
and set `details.metric_scope = c3_replay_audit`.

## Rollback

Schema rollback:

```text
sql/018_trigger_replay_audit_rollback.sql
```

It drops the three audit tables only after confirming all three row counts are
zero.

Future business rollback:

```text
sql/N4_C3_replay_audit_business_rollback.sql
```

It deletes only rows scoped by `replay_run_id` from the three audit tables,
`common_trigger_quality_item`, and `common_trigger_run`. It refuses to proceed
if any N4 outbox, inbox, or checkpoint rows exist for the replay run.

Rollback must not touch:

```text
original N4 projection matcher passed run
N5 current-real action passed run
N3 C3 outbox
B1/B2/C2/C2B/C3 facts
old synthetic outbox
old system
```

## Boundary Confirmation

This design wrote only repository files. It did not execute migration, write
database rows, consume C3 outbox, write inbox/checkpoint, write
common_trigger_match/state, write N4 outbox, enter N5/N6, pull market data, or
start a worker.

## Next Gate

Allowed next step:

```text
N4 018 trigger replay audit migration review
```

Still blocked:

```text
018 migration execute
N4 C3 replay audit runner implementation
N4 C3 replay audit execute
standard TriggerMatched / TriggerPendingMarketData outbox emission
N5 replay consumption
N6 execution
worker
```
