# N3 Projection Enrichment Schema Contract

Stage: `N3_PROJECTION_ENRICHMENT_SCHEMA_CONTRACT_DRY_RUN_GATE`

Result: `CONTRACT_PASS`

This contract prepares N3 projection enrichment for `N4_TRIGGER_RULE_SPEC_v4`. It is a contract and dry-run gate only: no execute, no database writes, no historical run edits, no outbox consumption, and no N4/N5/N6 entry.

## Ownership

N3 owns the projection enrichment facts consumed by N4 v4. `trigger_amount_chain_pass` is generated from the N2 frozen baseline plus N3 current metrics. N4 must not recompute enrichment fields from raw minute facts, B1 snapshots, or N2 baseline.

The minimum N4-facing enrichment fields are:

- `current_price_or_close`
- `current_amount_metric`
- `current_metric_time`
- `current_metric_quality_status`
- `projection_period`
- `projection_30m_flag`
- `projection_30m_type`
- `current_30m_virtual_amount`
- `reference_30m_amount`
- `reference_30m_entity_high`
- `reference_30m_entity_low`
- `trigger_amount_chain_pass`
- `projection_lineage_json`
- `source_freshness_status`
- `source_snapshot_run_id`
- `source_minute_run_id`
- `source_previous_day_minute_run_id`

## Contract

`current_price_or_close`, `current_amount_metric`, `current_metric_time`, and `current_metric_quality_status` are standardized N3 current metric fields. `projection_period` is `30m` in v1. `projection_30m_type` is one of `volume_up`, `shrink_down`, `none`, or `unknown`; `projection_30m_flag` is true only for `volume_up` or `shrink_down`.

`current_30m_virtual_amount` is the N3 active-bucket 30m virtual amount. `reference_30m_amount`, `reference_30m_entity_high`, and `reference_30m_entity_low` come from the previous-day same 30m bucket. Missing reference data keeps the row quality-visible and prevents N4 from silently inferring the value.

`trigger_amount_chain_pass` is a JSON object keyed by `Y`, `Q`, `M`, `W`, `D`, and `projection_30m`. It is computed by N3 using `N2 period_trigger_baseline_json` and N3 current metrics. N4 consumes the selected key only.

`projection_lineage_json` must carry source condition, subscription, snapshot, today minute, previous-day minute, source fact, minute ref, previous-day minute ref, and calculation config hash trace. `source_freshness_status` is one of `fresh`, `stale`, `missing`, or `unknown`.

## Storage

This gate does not execute a schema migration. Implementation may write the enrichment as an `enrichment_v1` payload in the physically separated `stock/index/board_realtime_projection_metric` tables or propose additive columns in a later implementation/migration gate. Historical runs must not be rewritten.

## Boundary

- No database writes
- No market data pull
- No outbox/inbox/checkpoint write or consumption
- No N4/N5/N6 execution
- No worker startup
- No historical run mutation

The next allowed step is the N3 projection enrichment implementation gate. Business execute remains unauthorized.
