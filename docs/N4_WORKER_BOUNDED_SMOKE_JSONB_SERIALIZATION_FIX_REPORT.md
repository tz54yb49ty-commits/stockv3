# N4 Worker Bounded Smoke JSONB Serialization Fix Report

Gate: `N4_WORKER_BOUNDED_SMOKE_JSONB_SERIALIZATION_FIX_GATE`  
Layer role: `N4_trigger`  
Result: `FIX_PASS`

## Root Cause

The bounded smoke execute failed before commit while binding `common_event_inbox` JSONB values:

```text
TypeError: Object of type datetime is not JSON serializable
```

The source event rows fetched through psycopg contain Python `datetime` values in fields such as `event_time` and `created_at`. Those values were preserved inside smoke `raw_json` and then handed to `Jsonb` without recursive normalization.

Post-failure live proof showed no residual scoped writes:

```text
run/quality/state/match/outbox/inbox/checkpoint = 0/0/0/0/0/0/0
N3 MarketSnapshotUpdated pending = 2155
N5/N6 refs = 0
```

## Code Repair

Updated:

- `src/ashare_v3/trigger/worker_consumer.py`
- `tests/test_n4_worker_bounded_smoke.py`

Added `make_json_safe`, which recursively normalizes:

- `datetime`, `date`, `time` to ISO-8601 strings
- `Decimal` to stable strings
- `UUID` to stable strings
- nested mappings and sequences recursively

All dict/list values passed through `_pg_params` are now normalized before `Jsonb` binding. Inbox payload, inbox raw_json, checkpoint payload, state raw_json, match raw_json, outbox payload, run raw_json, and quality details retain their fields instead of dropping data.

## Regression Proof

New tests cover:

- source event payload containing Python `datetime`
- checkpoint payload containing Python `datetime`
- JSON-safe conversion preserving `event_id`, `outbox_id`, `event_time`, `source_run_id`, and `payload_json`
- missing `--execute` / `--user-confirmed` still block before DB write
- no N3 outbox status update path
- no N5/N6 path

Targeted worker tests:

```text
Ran 19 tests OK
```

## Forbidden Scope Proof

This fix gate did not execute smoke, did not write DB rows, did not consume/update N3 outbox, did not enter N5/N6, did not start a worker, did not touch delivery/push/voice/mobile, did not touch sim/position/PnL/real trade, did not create proposal/order/trade, and did not touch the old system.

## Decision

`FIX_PASS`

Allowed next gate:

```text
N4_WORKER_BOUNDED_SMOKE_CONTRACT_GATE
```
