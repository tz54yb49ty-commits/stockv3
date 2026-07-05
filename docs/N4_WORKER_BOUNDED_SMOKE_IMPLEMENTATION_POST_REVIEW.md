# N4 Worker Bounded Smoke Implementation Post-Review

Gate: `N4_WORKER_BOUNDED_SMOKE_IMPLEMENTATION_POST_REVIEW_GATE`  
Layer role: `runtime_control`  
Result: `POST_REVIEW_PASS`  
Generated at: `2026-06-10T01:10:48+08:00`

## Implementation Proof Summary

The implementation report exists and parses as JSON:

- `docs/N4_WORKER_BOUNDED_SMOKE_IMPLEMENTATION.json`
- result: `IMPLEMENTATION_PASS`

Reviewed components:

- `src/ashare_v3/trigger/worker_state_transition.py`
- `src/ashare_v3/trigger/worker_consumer.py`
- `scripts/run_n4_worker_bounded_smoke_once.py`
- `tests/test_n4_worker_state_transition.py`
- `tests/test_n4_worker_bounded_smoke.py`
- `sql/N4_worker_bounded_smoke_rollback.sql`

The state transition helper is pure and deterministic. It covers:

- `inactive -> pending_market_data`
- `pending_market_data -> matched`
- `inactive -> matched`
- `matched -> inactive`
- `pending_market_data -> inactive`
- `matched -> matched` material change

Idempotency helpers are present:

- `source_event_consume_key`
- `trigger_state_key`
- `trigger_match_dedup_key`
- `trigger_pending_dedup_key`
- `trigger_state_changed_dedup_key`

Consumer boundary proof:

- N4 may plan scoped inbox/checkpoint writes in a future authorized smoke execute.
- N4 must not update N3 outbox status.
- Static scan found no `UPDATE common_event_outbox` path in `worker_consumer.py`.
- Static scan found no generic `SET status` path in `worker_consumer.py`.

CLI guard proof:

- missing `--execute` blocks before any DB write path
- missing `--user-confirmed` blocks before any DB write path
- default mode is dry validation only

## Runtime Semantics Proof

- `TriggerMatched` is emitted only for valid matched output.
- valid `TriggerMatched` sets `trigger_live=true`.
- valid `TriggerMatched` sets `n5_entry_allowed=true`.
- valid `TriggerMatched` writes `common_trigger_match`.
- `TriggerPendingMarketData` does not write `common_trigger_match`.
- `TriggerPendingMarketData` has `trigger_live=false` and `n5_entry_allowed=false`.
- `TriggerStateChanged` does not write `common_trigger_match`.
- `TriggerStateChanged` is not an N5 action entry.
- `TriggerPendingMarketData` and `TriggerStateChanged` do not enter N5.
- No N4 direct market pull path was introduced.
- No N5/N6 write path was introduced.

## Bounded Worker Smoke Safety Proof

Bounded controls exist:

- `max_events`
- `max_runtime_seconds`
- `stop_file`
- `status_json`
- `heartbeat_interval_seconds`

Safety decisions:

- long-running worker is not allowed by default
- default mode is no-execute / dry guard
- worker cannot become long-running without explicit bounded execute args
- no delivery/push/voice/mobile path
- no sim/position/order/trade/real_trade path
- old system untouched

## Rollback Draft Proof

Rollback SQL exists:

```text
sql/N4_worker_bounded_smoke_rollback.sql
```

Rollback status:

- hard-fail draft: `true`
- `RAISE EXCEPTION` occurs before first `DELETE`
- downstream ref review is required before enabling deletes
- N5/N6/user/sim/order/trade/position refs are explicitly listed for review
- N3 facts and N3 outbox status must not be touched
- no `CASCADE`, `DROP`, or `TRUNCATE`
- rollback not executed

If a future rollback is authorized, delete scope must remain limited to this smoke run:

- scoped `common_event_inbox`
- scoped `common_event_consumer_checkpoint`
- `common_event_outbox` where `source_layer='N4_trigger'` and `source_run_id='n4_worker_bounded_smoke'`
- `common_trigger_match`
- `common_trigger_state`
- `common_trigger_quality_item`
- `common_trigger_run`

This post-review does not authorize executing the rollback SQL. A future smoke execute must have its own final gate, and any real rollback must first pass a scoped rollback final gate.

## Live DB Baseline Proof

Read-only DB proof for `n4_worker_bounded_smoke`:

| proof | rows |
|---|---:|
| `common_trigger_run` | 0 |
| `common_trigger_quality_item` | 0 |
| `common_trigger_state` | 0 |
| `common_trigger_match` | 0 |
| N4 outbox | 0 |
| worker inbox | 0 |
| worker checkpoint | 0 |
| N5 refs | 0 |
| N6 refs | 0 |

## Regression Proof

Fresh verification:

```text
PYTHONPATH=src:scripts python3 -m unittest tests/test_n4_worker_state_transition.py tests/test_n4_worker_bounded_smoke.py
# Ran 12 tests OK

PYTHONPATH=src:scripts python3 -m unittest tests/test_trigger_projection_matcher.py tests/test_n4_trigger_rule_v4_matcher.py tests/test_n4_v4_enforcement.py tests/test_trigger_projection_matcher_execute.py
# Ran 86 tests OK

PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'
# Ran 128 tests OK

PYTHONPATH=src python3 scripts/check_n4_contract.py
# passed, finding_count=0

python3 -m compileall src/ashare_v3/trigger tests
# PASS
```

## Forbidden Scope Proof

This gate did not start a worker, did not execute N4, did not write business DB rows, did not consume or update N3 outbox, did not enter N5/N6, did not touch delivery/push/voice/mobile, did not touch sim/position/PnL/real_trade, did not create proposal/order/trade, and did not touch the old system.

## Validation

- implementation JSON parse: `PASS`
- source static review: `PASS`
- rollback static check: `PASS`
- live DB baseline proof: `PASS`
- targeted worker tests: `PASS`
- trigger test group: `PASS`
- compileall: `PASS`
- `scripts/check_n4_contract.py`: `PASS`
- post-review JSON parse: `PASS`
- `git diff --check`: `PASS`

## Decision

`POST_REVIEW_PASS`

Allowed next gate:

```text
N4_WORKER_BOUNDED_SMOKE_READINESS_GATE
```
