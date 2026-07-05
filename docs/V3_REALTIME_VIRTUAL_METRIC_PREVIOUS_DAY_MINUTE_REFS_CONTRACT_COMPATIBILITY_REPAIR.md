# V3 Realtime Virtual Metric Previous Day Minute Refs Contract Compatibility Repair

- result: `REPAIR_PASS`
- layer_role: `N3_market_data`
- generated_at: `2026-06-12T23:34:39+08:00`

## Root Cause

The DB CHECK requires every `metric_ready=true` row with any `previous_*_period_source=previous_trade_date_last_period` to carry non-empty `previous_day_minute_refs`.

The builder already marked the 09:31 rows as using `previous_trade_date_last_period`, but still emitted:

```text
previous_day_minute_refs=[]
```

The first failed row was:

```text
stock:SZ:300776 / 09:31
```

## Repair

- `realtime_virtual_metric.py` now collects previous-day refs from previous 1m and previous 5m/30m/120m aggregates whenever their source is `previous_trade_date_last_period`.
- `v3_realtime_virtual_metric_writer.py` now blocks before DB with `previous_day_minute_refs_missing` if a metric-ready row needs previous-day refs but does not carry them.

## Materialized Payload Proof

For the approved 20260612 payload:

- rows stock/index/board/total: `62/0/38/100`
- rows requiring previous-day refs: `66`
- rows missing previous-day refs: `0`
- previous-day refs length distribution: `120=66`
- writer validation: `valid=true`, `blocked_reasons=[]`
- signal counts: `B_BUY=76`, `S_SELL=24`

## Contract / Preflight

The writer contract and preflight now record the previous-day refs compatibility policy.

- execute_ready: `true`
- P0/P1/P2: `0/0/0`
- blockers: `[]`

## Validation

- RED observed: builder emitted empty previous-day refs and writer validation did not catch the missing refs
- focused tests after repair: PASS
- targeted tests: `15 tests OK`
- payload materialization check: PASS

Final JSON parse / compileall / git diff verification is recorded in terminal validation for this gate.

## Forbidden Scope

This gate did not execute writer, write DB, execute rollback, consume/update outbox/inbox/checkpoint, execute N4/N5, enter N6, start scheduler/worker, or touch voice/mobile/sim/trade.

## Next Gate

Return to runtime_control for:

```text
V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_EXECUTE_FINAL_GATE_REVIEW_AFTER_PREVIOUS_DAY_REFS_REPAIR
```
