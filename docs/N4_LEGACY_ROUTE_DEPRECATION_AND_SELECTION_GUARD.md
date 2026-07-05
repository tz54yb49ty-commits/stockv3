# N4 Legacy Route Deprecation And Selection Guard

Gate: `N4_LEGACY_ROUTE_DEPRECATION_AND_SELECTION_GUARD_GATE`

Layer role: `N4_trigger`

Result: `GUARD_PASS`

Finding: `N1N5-P2-002`

## Decision

Legacy route:

```text
src/ashare_v3/trigger/projection_matcher_execute.py
scripts/run_trigger_projection_matcher_once.py
```

Status: `deprecated_for_current_v4_corrected_flow`

The route is retained only for historical compatibility or for an explicitly reviewed projection-matcher gate. It is not selectable for the current 20260605 v4 corrected / matched-only N4 execute chain.

## Legacy Route Fence

The legacy module now exposes explicit route metadata:

```text
route_name=legacy_outbox_consuming_projection_matcher_execute
deprecated=true
allowed_scope=historical_compatibility_or_explicit_projection_matcher_gate_only
allowed_for_current_v4_corrected_flow=false
allowed_for_20260605_n4_execute_gate=false
n5_entry_source_for_current_chain=false
```

The module also blocks the current corrected execute run id before any write path:

```text
trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

This prevents `scripts/run_trigger_projection_matcher_once.py` from being used as the accidental execute route for the 20260605 corrected chain.

## Current Route Selection Proof

Current corrected route:

```text
scripts/run_n4_20260605_v4_corrected_execute_once.py
```

Current matched-only route:

```text
scripts/run_n4_20260605_matched_only_execute_once.py
```

These runners do not import `projection_matcher_execute` and do not call `run_projection_matcher_once`.

The matched-only contract/preflight already encode:

```text
uses_old_outbox_consuming_projection_matcher_execute_route=false
```

The test suite now asserts that this route flag remains false and that both current runners avoid the legacy execute route.

## N5 Entry Boundary

For the current 20260605 chain, the legacy projection matcher route is not a N5 entry source.

N5 entry must come only from the approved current N4 execute runner and its v4 compliant `TriggerMatched` outbox rows. Historical projection matcher runs remain historical evidence and must not be treated as the current 20260605 corrected chain.

## Modified Files

- `src/ashare_v3/trigger/projection_matcher_execute.py`
- `tests/test_trigger_projection_matcher_execute.py`
- `tests/test_n4_20260605_v4_corrected_execute_runner.py`
- `tests/test_n4_20260605_matched_only_execute.py`
- `docs/N4_LEGACY_ROUTE_DEPRECATION_AND_SELECTION_GUARD.md`
- `docs/N4_LEGACY_ROUTE_DEPRECATION_AND_SELECTION_GUARD.json`

## Forbidden Scope Proof

- N4 execute: not performed
- database writes: not performed
- rollback SQL: not executed
- outbox/inbox/checkpoint consumption or update: not performed
- worker start: not performed
- N5/N6 execution: not entered
- delivery/push/voice/mobile/sim/position/order/trade/real trade: not touched
- historical run evidence: not rewritten
- old system: not touched

## Next Gate

Return to runtime_control for:

```text
N4_LEGACY_ROUTE_DEPRECATION_AND_SELECTION_GUARD_POST_REVIEW_GATE
```

After post-review, runtime_control may rerun the N1-N5 cross-layer audit.
