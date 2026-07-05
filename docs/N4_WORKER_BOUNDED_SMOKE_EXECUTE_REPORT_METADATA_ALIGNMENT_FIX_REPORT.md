# N4 Worker Bounded Smoke Execute Report Metadata Alignment Fix

Result: `FIX_PASS`

## Root Cause

The bounded smoke execute runner seeded reports from the implementation-gate report, where `database_written=false` is correct for dry validation. After a scoped execute, the runner merged `write_counts` but did not recompute write metadata, so reports could show scoped N4 rows written while still claiming `database_written=false`.

## Code Repair Summary

- `scripts/run_n4_worker_bounded_smoke_once.py` now derives execute metadata from scoped N4 `write_counts`.
- Execute reports now distinguish scoped N4 writes from forbidden side effects:
  - `scoped_n4_database_writes=true` when any allowed smoke table has positive writes.
  - `database_written=true` for the scoped N4 smoke write.
  - `worker_started=false`.
  - `n3_outbox_updated=false`.
  - `n3_outbox_status_updated=false`.
  - `n5_n6_entered=false`.
- Status JSON now carries the same scoped write metadata.
- `src/ashare_v3/trigger/worker_consumer.py` markdown formatting now renders boundary flags dynamically instead of always printing `database_written=false`.

## Test Proof

- Added a main-level regression test for consumption-only execute report metadata.
- The test proves scoped run/quality/inbox/checkpoint writes are reported as scoped N4 DB writes while forbidden side effects remain false.

## Forbidden Scope Proof

- N4 was not executed.
- No worker was started.
- No database writes were performed by this fix gate.
- No outbox/inbox/checkpoint rows were consumed or updated.
- N5/N6 were not entered.
- No delivery, push, voice, mobile, sim, position, order, trade, or real trade path was touched.

## Validation

- `PYTHONPATH=src:scripts python3 -m unittest tests.test_n4_worker_bounded_smoke` -> PASS.
- `python3 -m compileall scripts/run_n4_worker_bounded_smoke_once.py src/ashare_v3/trigger/worker_consumer.py tests/test_n4_worker_bounded_smoke.py` -> PASS.
- Report JSON parse -> PASS.
- `git diff --check` -> PASS.

## Next Gate

`N4_WORKER_BOUNDED_SMOKE_EXECUTE_REPORT_METADATA_ALIGNMENT_FIX_POST_REVIEW_GATE`
