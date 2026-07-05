# N2 Target Price Double Adjustment 002831 Proof

Date: 2026-06-16

Layer: N2_condition

## Result

`002831.SZ` / source_trade_date `20260615` proved the target price double-adjustment bug:

```text
old_segment_low = 12.51
old_low_source_date = 20251021
bug = already-adjusted open/close was adjusted again by row_adj_factor / current_adj_factor
```

After the code repair, the same Q anchor segment is:

```text
main_up_anchor = Q
up_reference_period = M
segment_start_date = 20251009
segment_end_date = 20260615
segment_low_date = 20251021
segment_low = 17.86
segment_high_date = 20260520
segment_high = 31.65
amplitude = 13.79
base_price = 26.88
buy_target_price = 40.67
reference_target_price = 40.67
```

Secondary anchor remains:

```text
up_secondary_anchor = W
up_secondary_reference_period = D
up_secondary_trend_start_date = 20260608
up_secondary_trend_end_date = 20260615
up_secondary_amplitude = 4.24
up_secondary_base_price = 29.66
up_secondary_target_price = 33.90
secondary_target_price = 33.90
```

Full 20260615 dry-run comparison against active v2:

```text
stock_basis_rows_compared = 5504
target_price_changed_count_vs_active_v2 = 814
002831 active_v2 buy/secondary = 44.87 / 33.90
002831 repaired preview buy/secondary = 40.67 / 33.90
```

## Low Point Proof

For `20251021`:

```text
raw_open = 25.49
raw_close = 28.09
row_adj_factor = 2.5843
current_adj_factor = 3.6893
single_adjusted_entity_low = 25.49 * 2.5843 / 3.6893 = 17.86
double_adjusted_entity_low = 17.86 * 2.5843 / 3.6893 = 12.51
```

Therefore `12.51` is not a valid A-segment low under the repaired N2 QFQ/as-of policy.

## Boundary

This proof is code/test/artifact only:

```text
writes_performed = false
condition_active_run_executed = false
N3/N4/N5/N6 entered = false
outbox/inbox/checkpoint touched = false
```
