# N4 Worker Bounded Smoke Pending State Changed State Persistence Dedup Fix Report

Result: `FIX_PASS`

Gate: `N4_WORKER_BOUNDED_SMOKE_PENDING_STATE_CHANGED_STATE_PERSISTENCE_DEDUP_FIX_GATE`

Layer role: `N4_trigger`

Generated date: `2026-06-10`

## Root Cause

The bounded worker smoke write plan generated one `common_trigger_state` row for every transition event plan. For semantic fixture evaluations that produce both an outcome event and a `TriggerStateChanged` event for the same trigger state key, this created duplicate state rows with the same unique key:

```text
run_id, for_trade_date, asset_kind, identity_key, direction, signal_type, condition_key, trigger_period, trigger_bucket
```

The failing execute attempted to insert both `TriggerPendingMarketData` and `TriggerStateChanged` state rows for:

```text
run_id=n4_worker_bounded_smoke_20260608_pending_state_changed_semantic_fixture_probe
asset=board:TDX:881011
direction=buy
signal_type=B_BUY
condition_key=BUY_HINT
trigger_period=30m
trigger_bucket=30m
```

The transaction rolled back cleanly. Scoped rows remained `0`, N3 outbox was not consumed/updated, and downstream refs remained `0`.

## Code Repair Summary

Updated `src/ashare_v3/trigger/worker_consumer.py`:

- Added stable state persistence key helper for the `common_trigger_state` unique key.
- Coalesced `state_rows` in `build_smoke_write_plan` so each unique trigger state key writes at most one `common_trigger_state` row.
- Kept `common_event_outbox` event rows uncoalesced, preserving multiple semantic events when required:
  - `TriggerPendingMarketData`
  - `TriggerStateChanged`
  - `TriggerMatched`
- Preserved event trace in coalesced state `raw_json` with:
  - `coalesced_output_event_types`
  - `coalesced_state_event_count`
- Prioritized state-row payload selection:
  - `TriggerMatched`
  - `TriggerPendingMarketData`
  - `TriggerStateChanged`
- Changed match persistence to map `common_trigger_match` rows to coalesced state rows by stable state key instead of relying on original state row indexes.
- Kept N3 outbox update path absent.
- Kept N5/N6 path absent.

## Regression Proof

Added/updated tests in `tests/test_n4_worker_bounded_smoke.py`:

- Pending + state changed same key:
  - `common_trigger_state=1`
  - `common_event_outbox=2`
  - `common_trigger_match=0`
  - `n5_entry_allowed=true=0`
- Matched + state changed same key:
  - `common_trigger_state=1`
  - `common_trigger_match=1`
  - `common_event_outbox=2`
  - match row carries the coalesced state key
- Multiple different state keys:
  - each unique key writes exactly one state row
- Existing CLI guards still block missing `--execute` / `--user-confirmed` before DB write.
- N3 outbox update path remains absent.

## Pending Fixture Recomputed Write Plan

Using the pending/state-changed fixture in read-only mode:

- accepted source events: `6`
- transition_event_plan_count: `8`
- `TriggerMatched=0`
- `TriggerPendingMarketData=4`
- `TriggerStateChanged=4`

Recomputed write plan after dedup:

- `common_trigger_run=1`
- `common_trigger_quality_item=2`
- `common_event_inbox=6`
- `common_event_consumer_checkpoint=6`
- `common_trigger_state=6`
- `common_trigger_match=0`
- `common_event_outbox=8`
- `n5_entry_allowed=true=0`
- `n5_entry_allowed=false=8`

The previous contract/preflight expected `common_trigger_state=8`. The next contract gate must refresh planned state rows to `6` while preserving outbox events at `8`.

## Forbidden Scope Proof

- smoke executed: `false`
- database written: `false`
- N3 outbox consumed/updated: `false`
- N5/N6 entered: `false`
- worker started: `false`
- delivery/push/voice/mobile: `false`
- sim/position/PnL/real_trade: `false`
- proposal/order/trade: `false`
- old system touched: `false`

## Validation

- targeted worker tests: `28 OK`
- compileall: `PASS`
- report JSON parse: `PASS`
- rollback static check: `PASS`
- git diff --check: `PASS`

## Next Gate

Allowed to re-enter:

`N4_WORKER_BOUNDED_SMOKE_PENDING_STATE_CHANGED_SEMANTIC_FIXTURE_CONTRACT_GATE`
