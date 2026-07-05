# V3 20260612 Realtime Virtual Metric Writer Source Snapshot ID Compatibility Repair

Result: `REPAIR_PASS`

Gate: `V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_SOURCE_SNAPSHOT_ID_COMPATIBILITY_REPAIR_GATE`

Target run:

`action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1`

## Root Cause

The after-lineage-repair writer execute attempt was blocked before any target rows were written because live schema requires:

`source_snapshot_id BIGINT NOT NULL REFERENCES *_realtime_daily_snapshot(snapshot_id)`

The V3 new-plan writer is a minute-source realtime virtual metric writer. It computes metrics from retained 1m source facts plus N2/N4 context, so a realtime snapshot row is not guaranteed for every candidate.

Read-only coverage proof showed:

- unique stock candidates: `34`
- unique stock candidates with 20260612 snapshot rows: `33`
- missing stock snapshot candidate: `stock:SH:603125`
- unique board candidates: `11`
- unique board candidates with 20260612 snapshot rows: `11`

Therefore a fake numeric `source_snapshot_id` would be wrong: it would either violate the FK or misrepresent lineage.

## Repair

Writer policy:

`nullable_for_minute_source_realtime_virtual_metric`

Changes:

- Preserve `candidate.source_snapshot_id` when present.
- Keep `source_snapshot_id=NULL` when the metric is sourced from retained 1m facts.
- Record the policy in:
  - `source_fact_ids.source_snapshot_id_policy`
  - `trace_json.source_snapshot_id_policy`

Schema compatibility draft:

`sql/V3_realtime_virtual_metric_source_snapshot_id_nullable_compatibility.sql`

Rollback draft:

`sql/V3_realtime_virtual_metric_source_snapshot_id_nullable_compatibility_rollback.sql`

The migration keeps the existing FK. It only drops the `NOT NULL` requirement, allowing minute-source rows to use `NULL` while snapshot-source rows can still reference real snapshot facts.

## Writer Preflight Refresh

The writer contract/preflight artifacts now block execute until schema compatibility is reviewed and applied:

- contract: `docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_CONTRACT.json`
- preflight: `docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_PREFLIGHT.json`
- preflight result: `PREFLIGHT_BLOCKED`
- P0/P1/P2: `1/0/0`
- execute_ready: `false`
- blocker: `source_snapshot_id_nullable_schema_migration_required`

## Row Builder Proof

For the reviewed payload:

- candidates: `100`
- planned rows stock/index/board/total: `62/0/38/100`
- rows with `source_snapshot_id=NULL`: `100`
- rows with source snapshot policy trace: `100`

## Post-Failure Live Baseline

Target scoped rows remain zero:

- `common_market_data_run=0`
- `common_market_data_quality_item=0`
- stock/index/board metric rows: `0/0/0`
- outbox/inbox/checkpoint refs: `0`
- N4/N5/N6 refs: `0`

No rollback is needed for the failed attempt.

## Validation

- RED tests observed before repair: PASS
- focused tests: `3 tests OK`
- targeted tests: `22 tests OK`
- compileall: PASS
- JSON parse: PASS
- schema compatibility SQL static check: PASS
- row builder policy assertion: PASS
- target scoped DB baseline: PASS
- `git diff --check`: PASS

## Forbidden Scope

This gate did not execute writer, did not execute schema migration, did not write database rows, did not execute rollback, did not consume/update outbox/inbox/checkpoint, did not start scheduler/worker, did not enter N4/N5/N6, and did not touch voice/mobile/sim/trade or modify the old system.

## Decision

Writer execute retry is **not** allowed yet.

Allowed next gate:

`V3_REALTIME_VIRTUAL_METRIC_SOURCE_SNAPSHOT_ID_NULLABLE_SCHEMA_MIGRATION_FINAL_GATE_REVIEW`
