# N4 Projection Matcher Execute Runner SQL Placeholder Fix Report

Result: `FIX_PASS`

Generated at: `2026-06-08T11:31:31+08:00`

## Failure

The 20260608 v13 index-all N4 projection matcher execute failed before completing DB writes:

```text
psycopg.ProgrammingError:
the query has 23 placeholders but 24 parameters were passed
```

Root cause: `upsert_trigger_state()` inserted into `common_trigger_state` with `raw_json, updated_at` in the column list, but the `VALUES` list had only 23 `%s` placeholders plus `now()`. The parameter tuple correctly supplied 24 values, including `raw_json`.

## Fix

- Added the missing `%s` placeholder for `raw_json`; `updated_at` still uses `now()`.
- Added a regression assertion that the `common_trigger_state` SQL placeholder count equals the parameter count.
- Added hard-fail `RAISE EXCEPTION` to `build_projection_matcher_rollback_sql()` so future preflight regeneration preserves rollback safety.
- Restored the hard-fail guard in `sql/N4_projection_matcher_20260608_v13_index_all_until_0952_rollback.sql`.

## Red / Green Proof

- Placeholder regression was red before fix: `23 != 24`.
- Placeholder regression is green after fix.
- Rollback generator regression was red before fix: missing `RAISE EXCEPTION`.
- Rollback generator regression is green after fix.

## Post-Failure Baseline

No partial write remains for `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`:

- common_trigger_run: `0`
- common_trigger_quality_item: `0`
- common_trigger_state: `0`
- common_trigger_match: `0`
- common_event_outbox: `0`
- common_event_inbox: `0`
- common_event_consumer_checkpoint: `0`
- N5 refs: `0`
- N6 refs: `0`

## Validation

- targeted placeholder test: `PASS`
- targeted rollback generator test: `PASS`
- `PYTHONPATH=src:scripts python3 -m unittest tests/test_trigger_projection_matcher.py tests/test_trigger_projection_matcher_execute.py`: `21 OK`
- compileall: `PASS`
- existing N4 projection matcher gate JSON parse: `PASS`
- live DB post-failure baseline: `PASS`

## Forbidden Scope Proof

This fix gate did not retry N4 execute, did not write business rows, did not execute rollback SQL, did not consume/update outbox/inbox/checkpoint, did not enter N5/N6, did not start a worker, did not pull market data, did not touch delivery/push/voice/mobile, sim/position/pnl/real trade, proposal/order/trade, or the old system.

## Next Gate

Allowed next gate:

`N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_FINAL_GATE_REVIEW_RETRY`

Direct execute without renewed final gate review remains blocked.
