# N4 Worker Bounded Polling No-Source True Noop Implementation Report

Result: `FIX_PASS`

Layer role: `N4_trigger`

## Root Cause

After cross-run idempotency began excluding already inboxed/checkpointed N3 events, exhausted-source polling passes could still call the child bounded smoke runner. The child runner then wrote zero-event `common_trigger_run` and `common_trigger_quality_item` rows every scheduler interval.

The correct exhausted-source behavior is a true no-op at the wrapper boundary: no child invocation and no scoped N4 DB writes.

## Code Repair Summary

Modified:

- `scripts/run_n4_worker_bounded_poll_once.py`
- `tests/test_n4_worker_bounded_poll_once.py`

Changes:

- Added a `source_event_probe` step after `--execute --user-confirmed` guards and before child invocation.
- Default probe uses a read-only DB transaction and `fetch_source_events_for_smoke(..., consumer_name=...)`, preserving common_event_inbox / common_event_consumer_checkpoint exclusions.
- No-source result is `NOOP_PASS` with `reason=no_unprocessed_source_events`.
- No-source report sets `child_invoked=false`, `database_written=false`, `scoped_n4_database_writes=false`, and `trigger_run_written=false`.
- Source-present path still delegates to `scripts/run_n4_worker_bounded_smoke_once.py` with the existing argv list.
- Missing `--execute` or `--user-confirmed` still blocks before source probe and child invocation.

## True Noop Proof

Expected no-source report fields:

- `result=NOOP_PASS`
- `reason=no_unprocessed_source_events`
- `accepted_source_event_count=0`
- `child_invoked=false`
- `database_written=false`
- `scoped_n4_database_writes=false`
- `trigger_run_written=false`

No-source writes:

- `common_trigger_run=0`
- `common_trigger_quality_item=0`
- `common_event_inbox=0`
- `common_event_consumer_checkpoint=0`
- `common_trigger_state=0`
- `common_trigger_match=0`
- `common_event_outbox=0`

## Child Invocation Proof

- no-source path: child not invoked
- source-present path: child invoked with existing bounded smoke runner argv
- child Python remains wrapper runtime Python, not bare `python3`
- `--execute` and `--user-confirmed` are still passed only on the delegated child path

## Forbidden Scope Proof

This gate did not install or enable scheduler, did not manually execute wrapper, did not execute the N4 child runner, did not write business DB rows, did not consume/update N3 outbox/inbox/checkpoint, did not execute rollback SQL, did not enter N5/N6, did not start a long-running worker, and did not touch delivery/push/voice/mobile/sim/position/order/trade/real trade or the old system.

Next gate: `N4_WORKER_BOUNDED_POLLING_NO_SOURCE_TRUE_NOOP_IMPLEMENTATION_POST_REVIEW_GATE`.
