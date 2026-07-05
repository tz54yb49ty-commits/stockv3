# N3 Formal Amount Chain Unit Alignment Implementation Report

Result: `IMPLEMENTATION_PASS`

Layer: `N3_market_data`

## Summary

N3 formal amount chain metrics now convert N2/N1 daily amount seeds from `thousand_yuan` to `yuan` before combining them with intraday virtual amount metrics.

Canonical policy:

```text
amount_unit=yuan
source_amount_unit=thousand_yuan
unit_conversion_factor=1000
unit_conversion_policy=formal_amount_chain_thousand_yuan_to_yuan_v1
with_today_units_policy=current_trade_days_seed_plus_one
```

Formula:

```text
avg_with_today = (current_amount_total_seed_yuan + today_virt_amount_yuan) / (current_trade_days_seed + 1)
previous_avg = previous_avg_amount_yuan or previous_amount_yuan / total_units
```

Missing `today_virt_amount`, `current_trade_days_seed`, current amount seed, or a valid denominator now fails closed for that formal chain proof.

## Changed Files

- `src/ashare_v3/market/realtime_virtual_metric.py`
- `tests/test_v3_realtime_virtual_metric_builder.py`

## Verification

```text
PYTHONPATH=src python3 -m unittest tests.test_v3_realtime_virtual_metric_builder.V3RealtimeVirtualMetricBuilderTest.test_formal_amount_chain_metrics_use_today_virtual_and_period_averages tests.test_v3_realtime_virtual_metric_builder.V3RealtimeVirtualMetricBuilderTest.test_formal_amount_chain_metrics_fail_closed_without_seed_days
PASS

PYTHONPATH=src python3 -m unittest tests.test_v3_realtime_virtual_metric_builder tests.test_v3_realtime_virtual_metric_writer_runner
PASS

python3 -m compileall src/ashare_v3/market tests/test_v3_realtime_virtual_metric_builder.py
PASS

git diff --check -- src/ashare_v3/market/realtime_virtual_metric.py tests/test_v3_realtime_virtual_metric_builder.py
PASS
```

## Forbidden Scope

No database write, no N3 execute, no N4/N5/N6 entry, no outbox/inbox/checkpoint consumption or update, no scheduler/worker start, no voice/mobile/sim/position/order/real trade, and no old-system access.

## Next Gate

`N4_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_GUARD_ALIGNMENT_GATE`
