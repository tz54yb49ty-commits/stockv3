# N4 Worker Bounded Smoke Execute Runner Alignment Report

Gate: `N4_WORKER_BOUNDED_SMOKE_EXECUTE_RUNNER_ALIGNMENT_GATE`  
Layer role: `N4_trigger`  
Result: `ALIGNMENT_PASS`

## Summary

The bounded smoke runner has been aligned from dry-validation-only into a future scoped DB smoke execute runner. This gate did not execute the smoke, did not write the database, did not consume or update N3 outbox, and did not enter N5/N6.

## Runner Parameterization Proof

`scripts/run_n4_worker_bounded_smoke_once.py` now supports explicit:

- `--smoke-run-id`
- `--consumer-name`
- `--source-run-id`
- `--source-event-type`
- `--source-trade-date`
- `--max-events`
- `--max-runtime-seconds`
- `--heartbeat-interval-seconds`
- `--status-json`
- `--stop-file`
- `--json-report-path`
- `--markdown-report-path`
- `--rollback-sql-path`
- `--execute`
- `--user-confirmed`

The execute path requires an explicit `--smoke-run-id`; the default smoke run id can still be used for dry-validation reports, but it is not silently written to production tables.

## Scoped DB Execute Path Proof

Future authorized execute can write only:

- `common_trigger_run`
- `common_trigger_quality_item`
- `common_trigger_state`
- `common_trigger_match`
- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`

The execute path uses:

- `fetch_source_events_for_smoke`
- `fetch_existing_consume_keys`
- `fetch_smoke_run_metadata`
- `fetch_smoke_baseline_counts`
- `build_smoke_write_plan`
- `persist_worker_smoke_write_plan`

There is still no N3 outbox status update path, no N5/N6 write path, and no long-running loop.

## Guard Proof

- missing `--execute` blocks before DB write
- missing `--user-confirmed` blocks before DB write
- missing `--smoke-run-id` blocks before DB write
- existing scoped baseline rows block
- selected source events over `max_events` block
- non-pending source events block
- unsupported source event type blocks
- existing stop file blocks before DB write
- `TriggerPendingMarketData` does not write `common_trigger_match`
- `TriggerStateChanged` does not write `common_trigger_match`
- only `TriggerMatched` can set N5 entry eligibility

## Live Read-Only Proof

Read-only DB proof after this alignment:

```text
source pending MarketSnapshotUpdated = 2155
target smoke scoped rows run/quality/state/match/outbox/inbox/checkpoint = 0/0/0/0/0/0/0
```

## Rollback Proof

Rollback SQL:

```text
sql/N4_worker_bounded_smoke_20260608_unified_output_probe_rollback.sql
```

Static proof:

- `RAISE EXCEPTION` before first `DELETE` / `UPDATE`
- exact smoke run id present
- exact consumer name present
- no `DROP`
- no `TRUNCATE`
- no `CASCADE`
- rollback not executed

## Validation

```text
PYTHONPATH=src:scripts python3 -m unittest tests.test_n4_worker_state_transition tests.test_n4_worker_bounded_smoke
# PASS, 17 tests

PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'
# PASS, 128 tests

python3 -m compileall src/ashare_v3/trigger scripts tests
# PASS

PYTHONPATH=src python3 scripts/check_n4_contract.py
# PASS

git diff --check
# PASS
```

## Forbidden Scope Proof

This gate did not execute worker smoke, did not write DB rows, did not consume/update N3 outbox, did not enter N5/N6, did not start a long-running worker, did not touch delivery/push/voice/mobile, did not touch sim/position/PnL/real trade, did not create proposal/order/trade, and did not touch the old system.

## Decision

`ALIGNMENT_PASS`

Allowed next gate:

```text
N4_WORKER_BOUNDED_SMOKE_CONTRACT_GATE
```
