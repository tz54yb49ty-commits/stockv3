# V3 20260612 Realtime Virtual Metric Writer Lineage Compatibility Repair

Result: `REPAIR_PASS`

Gate: `V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_LINEAGE_COMPATIBILITY_REPAIR_GATE`

Target run:

`action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1`

## Root Cause

The writer execute attempt was blocked before any target scoped rows were written because live metric tables require legacy lineage columns to be non-null. The first stock row had `source_snapshot_run_id=null`, while `stock_action_confirmation_projection_metric.source_snapshot_run_id` is `NOT NULL`.

Affected required lineage columns:

- `source_snapshot_run_id`
- `source_today_minute_run_id`
- `source_previous_day_minute_run_id`

## Repair

Updated `src/ashare_v3/market/v3_realtime_virtual_metric_writer.py` so the row builder fills required lineage deterministically when the source payload has no snapshot-run lineage:

- `source_snapshot_run_id=v3_realtime_virtual_metric_source_payload_20260612_no_snapshot_source`
- `source_today_minute_run_id=v3_realtime_virtual_metric_source_payload_20260612_retained_today_1m`
- `source_previous_day_minute_run_id=v3_realtime_virtual_metric_source_payload_20260611_retained_previous_day_1m`

The same values are included in `source_fact_ids`, with:

`lineage_policy=deterministic_fallback_for_required_legacy_projection_columns`

This is a schema compatibility repair only. It does not change N4/N5 business rules.

## Plan-Only Proof

Plan-only writer output remains:

- result: `PLAN_ONLY`
- planned rows stock/index/board/total: `62/0/38/100`
- signal counts: `B_BUY=76`, `S_SELL=24`
- database written: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- N4/N5/N6 entered: `false`
- voice/mobile/sim/trade touched: `false`

## Post-Failure Live Baseline

Target scoped rows remain zero:

- `common_market_data_run=0`
- `common_market_data_quality_item=0`
- `stock_action_confirmation_projection_metric=0`
- `index_action_confirmation_projection_metric=0`
- `board_action_confirmation_projection_metric=0`

No rollback is needed for the failed attempt.

## Rollback Registry

Rollback SQL:

`sql/V3_20260612_realtime_virtual_metric_writer_runner_rollback.sql`

Static checks:

- hard-fail before first `DELETE/UPDATE`: PASS
- event infra guards: PASS
- downstream guards: PASS
- no `DROP` / `TRUNCATE` / `CASCADE`: PASS

Rollback was not executed.

## Validation

- TDD red test observed before repair: PASS
- targeted tests: `19 tests OK`
- plan-only writer proof: PASS
- compileall: PASS
- rollback static check: PASS
- JSON parse: PASS
- `git diff --check`: PASS

## Forbidden Scope

This gate did not execute writer, did not write database business rows, did not consume or update outbox/inbox/checkpoint, did not start scheduler/worker, did not enter N4/N5/N6, and did not touch voice/mobile/sim/trade or modify the old system.

## Next Gate

Allowed next gate:

`V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_EXECUTE_FINAL_GATE_REVIEW_AFTER_LINEAGE_REPAIR`
