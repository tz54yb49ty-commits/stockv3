# N3 20260612 B2 Trace-Aligned Standard Outbox Dates Contract Compatibility Repair

Result: `REPAIR_PASS`

## Root Cause

`realtime_projection_execute.py` requires `contract.dates.source_trade_date`, but the trace-aligned B2 standard outbox artifact builder and expected-distribution materializer only emitted `for_trade_date` and `prev_trade_date`. The dry-run and preflight artifacts also lacked a unified top-level `dates` block.

## Repair

- Threaded `source_trade_date` from resolved lineage into B2 expected-distribution materialization.
- Threaded `source_trade_date` into B2 trace-aligned artifact generation.
- Added a unified `dates` block to B2 dry-run, execute contract, and preflight artifacts:
  - `for_trade_date=20260612`
  - `source_trade_date=20260611`
  - `prev_trade_date=20260611`
- Refreshed the existing `UNTIL_1307` and `UNTIL_1333` B2 trace-aligned standard outbox artifacts without changing run ids, expected rows, distributions, write scope, rollback paths, or `writes_outbox=false`.

## Compatibility Proof

The runner-compatible `dates` contract is now present in:

- `docs/N3_20260612_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_UNTIL_1307_DRY_RUN.json`
- `docs/N3_20260612_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_UNTIL_1307_EXECUTE_CONTRACT.json`
- `docs/N3_20260612_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_UNTIL_1307_PREFLIGHT.json`
- `docs/N3_20260612_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_UNTIL_1333_DRY_RUN.json`
- `docs/N3_20260612_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_UNTIL_1333_EXECUTE_CONTRACT.json`
- `docs/N3_20260612_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_UNTIL_1333_PREFLIGHT.json`

## Validation

- RED tests before fix: expected `TypeError` for missing `source_trade_date` keyword.
- Targeted tests: `49 OK`
- Compileall: `PASS`
- JSON parse and dates assertion: `PASS`, 6 artifacts
- Forbidden scope scan: `PASS`
- `git diff --check`: `PASS`

## Forbidden Scope

No B1/B2/N4/N5/N6 execute was run. No database write, rollback execution, outbox/inbox/checkpoint consume or update, scheduler/worker start, voice/mobile/sim/trade path, or old-system touch occurred.

## Next Gate

Return to `runtime_control` for B2 trace-aligned standard outbox execute final gate review.
