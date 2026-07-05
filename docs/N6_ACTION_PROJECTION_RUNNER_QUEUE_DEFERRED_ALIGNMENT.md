# N6 Action Projection Runner Queue Deferred Alignment

Status: ALIGNMENT_PASS

Layer role: N6_user

Date: 2026-06-06

This gate fixes the N6 projection execute runner so that a contract with `notification_queue_policy=deferred` writes `user_projection_run`, `user_signal_projection`, and `user_signal_card`, while writing zero `user_notification_queue` rows.

No N6 execute was run. No database rows were written.

## Root Cause

The existing execute runner always treated notification queue rows as part of the write plan:

```text
ALLOWED_WRITE_TABLES included user_notification_queue
build_write_plan generated notification_rows for every event
write_counts set user_notification_queue=len(notification_rows)
commit_shadow_projection called insert_notification for each notification row
```

That behavior is valid for legacy/immediate queued-only projection, but it violates the 20260605 action projection contract where notification queue materialization is deferred.

## Fix Summary

`src/ashare_v3/user/projection_execute.py` now supports:

```text
notification_queue_policy=immediate
notification_queue_policy=legacy
notification_queue_policy=deferred
```

When policy is `deferred`:

```text
write_tables=user_projection_run,user_signal_projection,user_signal_card
user_projection_run=1
user_signal_projection=event_count
user_signal_card=event_count
user_notification_queue=0
notification_rows=[]
insert_notification not called
delivery/push/voice/mobile remains false
```

The runner validates contract artifacts before reading the database:

```text
deferred policy requires planned user_notification_queue=0
if deferred contract plans queue rows > 0, runner BLOCKS before repository read/write
```

It also validates the constructed write plan before commit:

```text
deferred policy requires write_counts.user_notification_queue=0
deferred policy requires user_notification_queue absent from write_tables
violations BLOCK before DB write
```

## Contract Alignment

The current 20260605 execute artifacts now include:

```text
notification_queue_policy=deferred
```

The existing execute contract/preflight artifacts remain marked from the previous blocked gate and should be refreshed in `N6_ACTION_PROJECTION_EXECUTE_CONTRACT_GATE` before runtime_control final gate review.

## Test Proof

New tests cover:

```text
deferred policy queue rows=0
projection/card rows remain equal to source event count
user_notification_queue absent from write_tables
contract deferred + planned queue rows > 0 blocks before repository read
legacy/immediate behavior remains covered by existing queued_only tests
no delivery/push/voice/mobile side effect
```

Validation:

```text
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_projection_execute.py' -> OK, 21 tests
```

## Forbidden Scope Proof

```text
execute_performed=false
database_written=false
write_user_projection_run=false
write_user_signal_projection=false
write_user_signal_card=false
write_user_notification_queue=false
consume_n5_outbox=false
update_n5_outbox_status=false
start_worker=false
delivery=false
push=false
voice=false
mobile=false
sim=false
position=false
pnl=false
proposal=false
order=false
trade=false
real_trade=false
modify_n6_ui_v1=false
modify_b_track=false
```

## Next Gate

Allowed next step:

```text
N6_ACTION_PROJECTION_EXECUTE_CONTRACT_GATE
```

That gate should refresh the execute contract/preflight status and re-check DB baseline before runtime_control final gate review.
