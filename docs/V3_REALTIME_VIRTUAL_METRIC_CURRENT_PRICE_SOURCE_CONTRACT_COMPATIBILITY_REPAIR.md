# V3 Realtime Virtual Metric Current Price Source Contract Compatibility Repair

- result: `REPAIR_PASS`
- layer_role: `N3_market_data`
- generated_at: `2026-06-12T22:49:41+08:00`

## Root Cause

The writer put a trace/path value into a DB-constrained canonical field:

```text
current_price_source = n3_realtime_virtual_metric.current_1m.close
```

The live DB CHECK constraint only allows:

```text
realtime_daily_snapshot / minute_bar_1m / adapter_projection / unknown
```

## Repair

The writer now canonicalizes:

```text
n3_realtime_virtual_metric.current_1m.close -> minute_bar_1m
```

The raw path is preserved in trace:

```text
trace_json.raw_current_price_source
trace_json.current_price_source_canonicalization
```

## Materialized Payload Proof

For the approved 20260612 payload:

- rows stock/index/board/total: `62/0/38/100`
- `current_price_source=minute_bar_1m`: `100`
- disallowed current_price_source values: `0`
- raw trace `n3_realtime_virtual_metric.current_1m.close`: `100`
- canonicalization trace `n3_realtime_virtual_metric.current_1m.close->minute_bar_1m`: `100`

## Contract / Preflight

The writer contract and preflight now record the current_price_source compatibility policy.

- execute_ready: `true`
- P0/P1/P2: `0/0/0`
- blockers: `[]`

## Validation

- RED observed: focused test failed because writer emitted `n3_realtime_virtual_metric.current_1m.close`
- focused test after repair: PASS
- writer targeted tests: `9 tests OK`
- payload materialization check: PASS

Final JSON parse / compileall / git diff verification is recorded in the terminal validation for this gate.

## Forbidden Scope

This gate did not execute writer, write DB, execute rollback, consume/update outbox/inbox/checkpoint, execute N4/N5, enter N6, start scheduler/worker, or touch voice/mobile/sim/trade.

## Next Gate

Return to runtime_control for:

```text
V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_EXECUTE_FINAL_GATE_REVIEW_AFTER_CURRENT_PRICE_SOURCE_REPAIR
```
