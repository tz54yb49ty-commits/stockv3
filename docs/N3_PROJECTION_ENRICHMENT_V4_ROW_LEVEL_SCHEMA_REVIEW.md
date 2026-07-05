# N3 Projection Enrichment v4 Row-Level Schema Review

- result: `SCHEMA_REVIEW_PASS`
- migration: `sql/034_n3_projection_enrichment_v4_row_level_schema.sql`
- rollback: `sql/034_n3_projection_enrichment_v4_row_level_schema_rollback.sql`
- scope: strictly additive DDL only
- tables:
  - `stock_projection_enrichment_v4_metric`
  - `index_projection_enrichment_v4_metric`
  - `board_projection_enrichment_v4_metric`

## Design

The current `*_action_confirmation_projection_metric` tables are identity-level. Their unique key is based on `projection_run_id + identity_key + trade_date + metric_minute_label + projection_schema_version`, which cannot store the 20260603 row-level v4 payload grain of one row per N4 context candidate.

The proposed schema adds three N3-owned physical tables. Each row is keyed by:

- `projection_enrichment_id` primary key
- `UNIQUE(projection_run_id, materialization_row_key)`
- `UNIQUE(projection_run_id, spec_version, source_trigger_context_run_id, source_trigger_context_id)`

`materialization_row_key` is a stable SHA-256 writer key generated from asset kind plus the upstream context row identity.

## JSONB Fields

- `trigger_amount_chain_pass`: N3-owned chain result from N2 baseline plus N3 current metrics.
- `projection_lineage_json`: source snapshot/minute/context lineage, with `n4_recompute_allowed=false`.
- `payload_json`: exact N4-facing row-level payload.
- `raw_json`: execution diagnostics and compatibility details.

All JSONB fields have object-shape checks.

## Source References

Each table stores:

- `projection_run_id`
- `spec_version`
- `policy_hash`
- `source_condition_run_id`
- `source_subscription_run_id`
- `source_snapshot_run_id`
- `source_today_minute_run_id`
- `source_previous_day_minute_run_id`
- `source_trigger_context_run_id`
- `source_trigger_context_id`
- `source_condition_context_enrichment_id`

`source_condition_context_enrichment_id` is the canonical N2 context enrichment link when available. `source_trigger_context_id` remains as transitional row-level lineage for the current v4 payload generated from trigger-context candidates.

## Boundary

Migration writes no business rows and does not touch:

- existing `*_action_confirmation_projection_metric`
- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- N4/N5/N6 tables
- worker state

## Rollback

Schema rollback hard-fails if any of the three new tables has rows, then drops only those three tables.

## Gate

Allowed to enter schema migration execute final gate after runtime_control review. Business materialization remains blocked until migration is executed and post-reviewed.
