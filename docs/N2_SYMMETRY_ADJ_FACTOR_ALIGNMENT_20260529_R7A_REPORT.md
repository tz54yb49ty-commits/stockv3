# N2 Symmetry Adj-Factor Alignment 20260529 R7A

Status: `R7A_DRY_RUN_PASS_PARTIAL`

Layer: `N2_condition`

This round only fixed and verified N2 target-price adj-factor normalization. It did not execute an N2 active run, did not write `condition_*` business rows, did not pull market data, did not enter N3/N4/N5/N6, and did not start a worker.

## Scope

- Add `adj_factor` to stock daily rows used by N2 period contexts.
- Normalize stock target-machine A-segment body boundaries with `row_adj_factor / current_adj_factor`.
- Preserve target-machine body-boundary policy: `max(open, close)` / `min(open, close)`.
- Record `adjustment_policy` and `current_adj_factor` in `target_price_trace_json`.

## Live Dry-Run Sample

`stock:SZ:300327 / source_trade_date=20260529`

```text
main_up_anchor = Y
up_reference_period = Q
up_trend_start_date = 20250102
up_trend_end_date = 20260529
up_segment_low = 19.25
up_segment_high = 34.28
up_amplitude = 15.03
up_base_price = 23.24
buy_target_price = 38.27
reference_target_price = 38.27
adjustment_policy = ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR
current_adj_factor = 3.1316
```

The primary target now matches the target-machine golden value.

## Remaining Blocker

The secondary target remains blocked by an N1 historical daily fact gap:

```text
blocked_by_layer = N1_ingestion
stock_daily_bar_fact rows for 20260525 = 2052
stock:SZ:300327 on 20260525 = missing
```

Current N2 secondary dry-run remains:

```text
up_secondary_anchor = W
up_secondary_reference_period = D
up_secondary_trend_start_date = 20260526
up_secondary_trend_end_date = 20260529
up_secondary_amplitude = 3.38
up_secondary_base_price = 29.60
up_secondary_target_price = 32.98
```

Expected target-machine secondary requires the missing `20260525` daily fact:

```text
up_secondary_target_price = 33.04
```

## Next Route

1. Hand off to `layer_role=N1_ingestion` to repair or reload the 20260525 official stock daily gap.
2. Re-run N2 full dry-run / preflight after N1 is clean.
3. Only then open an N2 active supersede final gate.
