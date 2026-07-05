# N3 20260612 B2 Trace-Aligned Standard Outbox Calculation Config Compatibility Repair

- Result: IMPLEMENTATION_PASS
- Generated at: 2026-06-12T11:52:10+08:00

## Root Cause

`build_b2_calculation_config()` omitted runner-required canonical fields, so `materialize_b2_expected_distribution()` built a temporary B2 contract that failed inside `realtime_projection_execute.build_projection_rows` with `KeyError: calculation_method`.

## Repair

Added canonical B2 calculation config fields: `calculation_method`, `calculation_config_hash`, `window_total_seconds`, `completion_ratio_min_ready`, `amount_projection_expand_threshold`, `amount_projection_shrink_threshold`, and `price_flat_abs_pct_threshold`. Existing trace-aligned fields remain preserved.

## Boundary

No scheduler/wrapper/N3/N4/N5 execution was started. No database write, rollback execution, outbox/inbox/checkpoint consumption/update, N6, voice, mobile, sim, or trade path was entered.

## Validation

- Red test observed: PASS
- Targeted tests: PASS, 28 tests
- Compileall: PASS
- JSON parse: PASS
- Forbidden scope scan: PASS
- git diff --check: PASS
