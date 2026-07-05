# N4 Worker Bounded Smoke Idempotency Duplicate Retry Runner Alignment

Result: `ALIGNMENT_PASS`

## Root Cause

The helper model already supported duplicate detection and existing consume keys, but the execute runner had no scenario input or failure injection switch. A final gate could only run clean consumption-only smoke, which would not prove duplicate/retry behavior.

## Repair Summary

- Added `--idempotency-scenario-path` to the bounded smoke runner.
- Scenario JSON is validated before any DB write path.
- Scenario mode can inject duplicate source rows and modeled existing consume keys in memory.
- Failure injection supports `before_write` and `after_persist_before_commit`; default is disabled.
- Execute reports now include scenario metrics for accepted/skipped events and failure injection.

## Safety

- Missing `--execute` or `--user-confirmed` still blocks before DB connect/write.
- Invalid scenario JSON blocks before DB connect/write.
- N3 outbox status update path remains absent.
- N5/N6, worker, delivery, voice, mobile, sim, position, order, trade, and old system paths remain absent.

## Validation

- targeted worker tests: `PASS`
- trigger test group: `PASS`
- compileall: `PASS`
- report JSON parse: `PASS`
- rollback static check: `PASS`
- `scripts/check_n4_contract.py`: `PASS`
- `git diff --check`: `PASS`

## Next Gate

`N4_WORKER_BOUNDED_SMOKE_IDEMPOTENCY_DUPLICATE_RETRY_CONTRACT_GATE`
