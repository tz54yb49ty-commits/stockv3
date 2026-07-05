# N4 Worker Bounded Polling Cross-Run Idempotency Repair Report

Result: `FIX_PASS`

Layer role: `N4_trigger`

## Root Cause

The scheduler reactivation itself worked. The first scheduled bounded polling pass wrote `common_event_inbox=50` and `common_event_consumer_checkpoint=50`.

The next scheduled pass selected the same first pending N3 `MarketSnapshotUpdated` events because N4 deliberately does not update N3 outbox status. The duplicate was not filtered because `fetch_existing_consume_keys` returned `common_event_inbox.dedup_key`, which is the upstream N3 event dedup key, while the dry-run helper compares against `source_event_consume_key(consumer_name,event_id)`.

So the cross-run duplicate was invisible until the DB unique key rejected it:

```text
uq_common_event_inbox_consumer_event
```

## Repair Summary

- `src/ashare_v3/trigger/worker_consumer.py`
  - `fetch_source_events_for_smoke` now accepts `consumer_name`.
  - Source selection excludes rows already present in `common_event_inbox` for the same consumer/event.
  - Source selection also excludes rows already represented in `common_event_consumer_checkpoint` via `last_event_id`, `checkpoint_payload.source_event_id`, or `checkpoint_payload.source_event_consume_key`.
  - `fetch_existing_consume_keys` now returns canonical `consumer_name|event_id` consume keys from inbox raw_json and checkpoint payload/last_event_id.
- `scripts/run_n4_worker_bounded_smoke_once.py`
  - Nonsemantic polling/consumption source selection passes the active consumer name to the source fetcher.
- `tests/test_n4_worker_bounded_smoke.py`
  - Added regression coverage for inbox/checkpoint exclusion and canonical consume-key loading.

## Idempotency Proof

- first pass can still select unprocessed pending N3 events
- second pass excludes events already in this consumer's inbox
- second pass excludes events already in this consumer's checkpoint
- duplicate `common_event_inbox(consumer_name,event_id)` insertion is prevented before write planning
- `max_events` bound remains enforced
- N3 outbox remains pending by design
- no N3 outbox status update path was introduced
- no N5/N6 path was introduced

## Validation

- targeted RED tests failed before the fix and now pass:
  `2 tests OK`
- worker/polling regression group:
  `45 tests OK`
- compileall:
  `PASS`
- forbidden scope scan:
  no `UPDATE common_event_outbox` / `SET status` path in `worker_consumer`
- scheduler state:
  `not_loaded`
- live N3 source outbox:
  `MarketSnapshotUpdated pending=2100`
- live repaired source selection helper check:
  `existing_consume_key_count=50`, `selected_unprocessed_count=50`, `selected_distinct_event_id_count=50`, `selected_intersects_existing_consume_keys=false`

## Forbidden Scope Proof

This gate did not manually execute the wrapper, did not execute the N4 child runner, did not write the database, did not consume/update N3 outbox/inbox/checkpoint, did not execute rollback SQL, did not load/start the scheduler, did not start a long-running worker, did not enter N5/N6, and did not touch delivery/push/voice/mobile, sim/position/PnL/real trade, proposal/order/trade, or the old system.

Next gate: `N4_WORKER_BOUNDED_POLLING_CROSS_RUN_IDEMPOTENCY_REPAIR_POST_REVIEW_GATE`.
