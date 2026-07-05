# N4 Worker Bounded Smoke Implementation

Result: `IMPLEMENTATION_PASS`

Gate: `N4_WORKER_BOUNDED_SMOKE_IMPLEMENTATION_GATE`

Layer role: `N4_trigger`

This implementation adds side-effect-free bounded worker smoke planning, state transition helpers, CLI guards, rollback draft SQL, and tests. It does not start a worker, execute N4, write the database, consume/update N3 outbox, enter N5/N6, or touch delivery/push/voice/mobile/sim/position/order/trade/real trade.

## Implemented Components

- `src/ashare_v3/trigger/worker_state_transition.py`
- `src/ashare_v3/trigger/worker_consumer.py`
- `scripts/run_n4_worker_bounded_smoke_once.py`
- `tests/test_n4_worker_state_transition.py`
- `tests/test_n4_worker_bounded_smoke.py`
- `sql/N4_worker_bounded_smoke_rollback.sql`

## State Transition Summary

- `inactive -> pending_market_data`: `TriggerPendingMarketData + TriggerStateChanged`
- `pending_market_data -> matched`: `TriggerMatched + TriggerStateChanged`
- `inactive -> matched`: `TriggerMatched + TriggerStateChanged`
- `matched -> inactive`: `TriggerStateChanged`
- `pending_market_data -> inactive`: `TriggerStateChanged`
- `matched -> matched` material change: `TriggerStateChanged`

## Boundary Proof

- `TriggerPendingMarketData` writes `common_trigger_match=false`, `trigger_live=false`, `n5_entry_allowed=false`.
- `TriggerStateChanged` writes `common_trigger_match=false`, `is_n5_action_entry=false`.
- The consumer planner never updates N3 `common_event_outbox.status`.
- CLI defaults to dry validation and blocks future write mode unless both `--execute` and `--user-confirmed` are present.
- Rollback SQL hard-fails before the first `DELETE`.

## Next Gate

`N4_WORKER_BOUNDED_SMOKE_IMPLEMENTATION_POST_REVIEW_GATE`
