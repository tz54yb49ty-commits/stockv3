# N3 Formal Amount Chain Metric Implementation

Status: `IMPLEMENTATION_PASS`

Layer: `N3_market_data`

Scope: code, tests, and implementation artifact only. No database write, no scheduler or worker, no outbox/inbox/checkpoint mutation, no N4/N5/N6 execution, no voice/mobile/sim/position/order/real trade, and no old-system access.

## Metric Policy

- `metric_policy=previous_day_same_window_elapsed_ratio_v1`
- `amount_unit=yuan`
- `current_period_amount_source_kind=N3_standard_period_metric`
- 5m and 30m calibrated virtual amount formula:
  `today_elapsed_amount / previous_day_same_elapsed_amount * previous_day_same_full_amount`
- Missing previous-day same elapsed amount, missing previous-day same full amount, or non-positive denominator fails closed. No fallback and no linear extrapolation.

## Formal Amount Chain

N3 now emits the formal attachment-rule amount chain metrics in the realtime virtual metric payload and trace:

- `today_virt_amount`
- `weekly_avg_with_today`
- `monthly_avg_with_today`
- `quarterly_avg_with_today`
- `yearly_avg_with_today`
- `prev_weekly_avg`
- `prev_monthly_avg`
- `prev_quarterly_avg`
- `prev_yearly_avg`

The values are available under `trace_json.formal_period_amount_proof.amount_chain_metrics` for downstream N4 consumption. Physical DB columns were not added in this gate; adding physical columns must use a separate additive schema migration gate.

## HINT Metrics

N3 keeps and strengthens HINT calibrated amount evidence:

- `current_5m_virtual_amount`
- `current_30m_virtual_amount`
- `previous_day_same_5m_full_amount`
- `previous_day_same_30m_full_amount`

Both 5m and 30m proofs are validated by the writer before execution.

## Validation

- targeted N3 tests: `PASS`
- compileall: `PASS`
- JSON parse: `PASS`
- git diff --check: `PASS`
