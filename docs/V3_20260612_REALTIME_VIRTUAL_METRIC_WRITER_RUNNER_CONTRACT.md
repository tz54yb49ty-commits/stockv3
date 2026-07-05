# V3 20260612 Realtime Virtual Metric Writer Runner Contract

Result: CONTRACT_PASS

This gate is contract / preflight / rollback only. It does not execute a writer,
does not write database rows, does not consume or update event infrastructure,
and does not enter N4/N5/N6.

Target run:

```text
action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1
```

## Source Scope

- for_trade_date: `20260612`
- source_condition_run_id: `condition_layer_20260611_source_20260611_for_20260612_v1`
- source condition status: `passed_active`
- source_snapshot_run_id: `realtime_daily_snapshot_20260612_standard_outbox_until_1500__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- source_today_minute_run_id: `today_minute_bar_1m_20260612_until_1500__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- source_previous_day_minute_run_id: `previous_day_minute_preload_20260611_for_20260612__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- retained 1m source facts:
  - stock: `705120`
  - index: `90144`
  - board: `56832`
- retained subscription rows / objects: `2676 / 2082`

The writer must use retained N3 1m source facts plus N2/N4 context. N4/N5 must
not reconstruct these metrics from raw minute rows.

## Expected Rows

- total metric rows: `100`
- metric_ready: `100`
- metric_not_ready: `0`
- signal distribution: `B_BUY=76`, `S_SELL=24`

Downstream dry-run reference remains diagnostic:

- N4 TriggerMatched: `96`
- N5 ActionExecuted: `96`
- target-machine comparison missing: `4`

## Policy

- Auction: `09:31` label can be an N3-owned auction realtime virtual metric.
- Midday: `13:00` label bridges the missing `11:30` bar; do not fabricate an
  `11:30` source row.
- Higher periods: `D/W/M/Q/Y` context must come from N2
  `period_trigger_baseline_json` or a reviewed localized N4 context copy.
- DB column canonical form is PostgreSQL lowercase identifiers such as
  `current_d_body_high`; uppercase `D/W/M/Q/Y` names are display aliases only.
- `current_price_source` is a DB-constrained canonical source field. The writer
  maps `n3_realtime_virtual_metric.current_1m.close` to `minute_bar_1m` and
  preserves the raw path in `trace_json.raw_current_price_source`.
- Source run-id FK lineage is contract-reviewed. The legacy
  `source_snapshot_run_id` column uses the reviewed 20260612 standard outbox
  snapshot run as the FK anchor; minute evidence remains traced through
  `source_today_minute_run_id`, `source_previous_day_minute_run_id`,
  `source_minute_refs`, and `previous_day_minute_refs`.

## Write Scope

Allowed future execute tables:

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_action_confirmation_projection_metric`
- `index_action_confirmation_projection_metric`
- `board_action_confirmation_projection_metric`

Forbidden:

- minute/source facts
- realtime snapshot facts
- outbox/inbox/checkpoint
- N4/N5/N6/user/sim/voice/mobile/trade paths

## Runner Status

The source payload is present and the source_snapshot_id nullable schema
migration has passed post-review. Contract readiness is restored:

```text
P0/P1/P2 = 0/0/0
execute_ready = true
blockers = []
```

Next gate:

```text
V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_EXECUTE_FINAL_GATE_REVIEW
```


## Source Payload Refresh

- source payload: `docs/V3_20260612_realtime_virtual_metric_writer_payload.json`
- candidate count: `100`
- B_BUY/S_SELL: `76/24`
- asset distribution stock/index/board: `62/0/38`


## Source Snapshot ID Nullable Schema Refresh

- refreshed_at: `2026-06-12T22:30:00+08:00`
- live schema: `source_snapshot_id.is_nullable=YES` on stock/index/board metric tables
- stale blocker removed: `source_snapshot_id_nullable_schema_migration_required`
- execute_ready: `true`
- P0/P1/P2: `0/0/0`


## Current Price Source Compatibility

- DB allowed values: `realtime_daily_snapshot / minute_bar_1m / adapter_projection / unknown`
- writer canonicalization: `n3_realtime_virtual_metric.current_1m.close -> minute_bar_1m`
- materialized payload check: `minute_bar_1m=100`, disallowed values `0`
- raw source trace: `trace_json.raw_current_price_source`
- canonicalization trace: `trace_json.current_price_source_canonicalization`

## Previous Day Minute Refs Compatibility

- DB requirement: metric-ready rows with `previous_*_period_source=previous_trade_date_last_period` must carry non-empty `previous_day_minute_refs`
- writer builder policy: collect refs from previous 1m and previous 5m/30m/120m aggregates when their source is previous trade date
- writer validation blocker before DB: `previous_day_minute_refs_missing`
- materialized payload check: rows requiring refs `66`, missing refs `0`

## Source Run ID FK Compatibility

- DB requirement: `source_snapshot_run_id`, `source_today_minute_run_id`, and `source_previous_day_minute_run_id` must reference existing `common_market_data_run.run_id` rows.
- lineage_policy: `contract_reviewed_source_run_id_fk_lineage`
- fallback prefix rows: `0`
- writer validation blocker before DB: `source_run_id_fk_lineage_unresolved`
