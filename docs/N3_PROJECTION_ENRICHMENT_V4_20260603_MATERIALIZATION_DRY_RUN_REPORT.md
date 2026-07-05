# N3 Projection Enrichment v4 Row-Level Materialization Dry-Run

- result: `BLOCKED`
- dry_run_data_result: `MATERIALIZATION_DRY_RUN_PASS`
- target_run_id: `projection_enrichment_v4_20260603_until_1500__realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- expected_rows: `5222`
- projection_enrichment_rows: `5222`
- complete_lineage_rows: `5218`
- BJ quality-visible rows: `{'index:BJ:899050': 2, 'index:BJ:899601': 2}`
- trigger_amount_chain_pass coverage: `5218/5222`
- projection_30m coverage: `5218/5222`
- P0/P1/P2: `1/1/0`

## Blocker
The current 032 action-confirmation projection metric tables are identity-level and have a uniqueness constraint on `projection_run_id, identity_key, trade_date, metric_minute_label, projection_schema_version`. The target grain is one row per `source_trigger_context_id`, so DB materialization needs an additive row-level schema migration first.

## Artifacts
- row payload: `docs/N3_projection_enrichment_v4_20260603_row_payload.json`
- contract: `docs/N3_projection_enrichment_v4_20260603_materialization_contract.json`
- preflight: `docs/N3_projection_enrichment_v4_20260603_materialization_preflight.json`
- rollback draft: `sql/N3_projection_enrichment_v4_20260603_materialization_rollback.sql`

## Boundary
- no DB write
- no outbox/inbox/checkpoint
- no N4/N5/N6
- no worker
