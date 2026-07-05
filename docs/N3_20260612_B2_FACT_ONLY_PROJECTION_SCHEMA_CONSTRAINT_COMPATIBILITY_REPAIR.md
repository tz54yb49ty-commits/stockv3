# N3 20260612 B2 Fact-Only Projection Schema Constraint Compatibility Repair

Result: `IMPLEMENTATION_PASS`

## Root Cause

Fact-only B2 used the source B1 `snapshot_time` with seconds and microseconds as the projection metric `snapshot_time`, while `projection_window_for_snapshot()` derived the projection window from the floored closed label.

At a half-hour boundary, this produced an invalid row:

- source snapshot time: `2026-06-12T14:00:00.010889+08:00`
- derived window: `13:30-14:00`
- table constraint: `snapshot_time <= window_end`

So B2 reached `N3-B2 writing 2082 projection facts`, then PostgreSQL rejected the stock projection insert on `stock_realtime_projection_metric_check2`.

## Repair

Changed `src/ashare_v3/market/realtime_projection_execute.py` for policy mode `fact_only_defer_off_bucket_source_snapshot_time`:

- store a DB-valid projection bucket timestamp in the projection metric `snapshot_time`
- clamp the bucket timestamp to `window_end` when source observed time is just after a half-hour boundary
- preserve the original `source_snapshot_time` in `raw_json` trace
- keep `NOOP_PASS_NO_WRITE` for true midday/off-bucket source times

This does not forge closed data and does not write outbox.

## Proof

The historical failing `1357` contract now builds rows read-only:

- rows: `2082`
- stock/index/board: `1872/83/127`
- `snapshot_time > window_end` violations: `0`
- max `snapshot_time - window_end`: `0.0s`

## Validation

- red test observed for boundary source time
- targeted tests: `61 OK`
- compileall: `PASS`
- JSON parse: `PASS`
- forbidden scope scan: `PASS`
- `git diff --check`: `PASS`

## Forbidden Scope

No scheduler start, no manual wrapper/N3/N4/N5 execution, no DB write, no rollback, no outbox/inbox/checkpoint mutation, no N6, no voice/mobile/sim/trade.

Next: `N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_REACTIVATION_FINAL_GATE_AFTER_B2_FACT_ONLY_SCHEMA_CONSTRAINT_REPAIR`.
