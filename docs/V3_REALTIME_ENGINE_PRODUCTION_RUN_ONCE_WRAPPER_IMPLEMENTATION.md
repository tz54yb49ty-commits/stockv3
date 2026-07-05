# V3 Realtime Engine Production Run Once Wrapper Implementation

- stage: `V3_REALTIME_ENGINE_PRODUCTION_RUN_ONCE_WRAPPER_IMPLEMENTATION_GATE`
- layer_role: `N3_market_data`
- result: `IMPLEMENTATION_PASS`

## Implemented Files

- `scripts/run_v3_realtime_engine_once.py`
- `tests/test_v3_realtime_engine_once.py`

## Wrapper Behavior

- Default mode is `PLAN_ONLY`.
- Execute requires both `--execute` and `--user-confirmed`.
- No-overlap lock path is `tmp/v3_realtime_engine.lock`.
- Child commands are argv lists only and do not use shell strings.
- Each pass exits after one bounded run.

## Stage Order

1. `N3_REALTIME_VIRTUAL_METRIC`
2. `N4_TRIGGER`
3. `N5_ACTION`

N3 calls `scripts/run_v3_realtime_virtual_metric_writer_once.py` with the reviewed contract, preflight, and payload artifacts. N4 calls `scripts/run_trigger_projection_matcher_once.py` and consumes the N3 metric run id. N5 calls `scripts/run_action_consumer_once.py` with `--source-event-type TriggerMatched`; `TriggerPendingMarketData` and `TriggerStateChanged` are not action-confirmation entry events.

## Idempotency

The wrapper checks deterministic run ids. If N3, N4, and N5 are already `passed`, the wrapper returns `NOOP_PASS`. If lineage/source readiness returns `noop`, the wrapper returns `NOOP_PASS` before any child command. If any child returns non-zero, the wrapper returns `BLOCKED` and stops downstream stages.

## Forbidden Scope

This implementation gate did not install or enable scheduler, execute wrapper children, write database business rows, execute rollback SQL, consume/update outbox/inbox/checkpoint, enter N6, start a worker, touch voice/mobile/sim/position/PnL/real trade, or touch the old system.

## Validation

- targeted tests: `PASS` (`23` tests)
- compileall: `PASS`
- JSON parse: `PASS`
- CLI plan-only smoke: `PASS`
- forbidden scope scan: `PASS`
- git diff --check: `PASS`

## Next

`V3_REALTIME_ENGINE_PRODUCTION_RUN_ONCE_WRAPPER_POST_REVIEW_GATE`
