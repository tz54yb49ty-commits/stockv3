# N6 Delivery Schema Alignment Migration Draft

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-06-04

This is a schema-only draft for the N6 delivery noop preview path. It does not
run migration SQL, materialize delivery rows, consume N5 outbox, start workers,
or perform provider delivery.

## Failure Context

The previous noop preview execute reached preflight but failed at DB constraint
compatibility. No target rows were materialized.

```text
materialized rows=0
source queued_only rows unchanged=863
N5 outbox ActionBlocked pending=863
rollback_safe=true
```

## Scope

Migration draft:

```text
sql/035_n6_delivery_notification_queue_schema_alignment.sql
```

Rollback draft:

```text
sql/035_n6_delivery_notification_queue_schema_alignment_rollback.sql
```

The migration only replaces two `user_notification_queue` CHECK constraints:

```text
notification_source
channel
```

No other N6 table is touched. N1-N5 tables and N5 outbox are not touched.

## Constraint Diff

`notification_source` keeps all existing values and adds exactly:

```text
n6_delivery_materialized_noop
```

`channel` keeps all existing values and adds exactly:

```text
in_app_notification_preview
```

Existing `notification_source` values preserved:

```text
index_signal
board_signal
stock_filter_signal
n5_action_event
n5_hint_event
n5_action_eligible
n5_action_blocked
n5_action_executed
n5_action_skipped
```

Existing `channel` values preserved:

```text
broadcast_queue
voice_future
mobile_future
in_app_future
```

## Rollback

Rollback restores the old CHECK constraints, but first hard-fails if any rows
already use the delivery preview values:

```text
notification_source=n6_delivery_materialized_noop
channel=in_app_notification_preview
```

If those rows exist, business rollback must happen first through the delivery
materialization rollback path. The schema rollback does not touch N5 outbox or
N1-N5 facts.

## Boundary

```text
execute=false
database_write=false
N5 outbox consumption=false
N5 outbox status update=false
worker=false
provider delivery=false
push=false
voice=false
mobile=false
sim=false
position=false
real_trade=false
```

## Validation

Static checks are in:

```text
tests/test_n6_delivery_schema_alignment_migration.py
```

Required verification:

```text
python3 -m compileall scripts src tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_delivery_schema_alignment_migration.py'
python3 -m json.tool docs/N6_delivery_schema_alignment_migration_draft.json
git diff --check
```

## Execute Readiness

Allowed next step:

```text
runtime_control schema migration execute final gate review
```

Execute candidate for that future gate:

```text
psql "$ASHARE_V3_POSTGRES_DSN" -v ON_ERROR_STOP=1 -f sql/035_n6_delivery_notification_queue_schema_alignment.sql
```
