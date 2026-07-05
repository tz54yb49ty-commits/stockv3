# N3 20260611 B2 Trace-Aligned Standard Outbox Dry-Run Contract Compatibility Repair

Result: `REPAIR_PASS`

## Root Cause

B2 runner `ensure_dry_run_matches_contract()` requires:

```text
dry_run.projection_run_id_candidate == contract.projection_run_id
```

The trace-aligned dry-run artifact had `projection_run_id`, but omitted `projection_run_id_candidate`, so the runner blocked before any database write:

```text
N3-B2 blocked: dry-run projection_run_id does not match contract
```

## Repair

Added `projection_run_id_candidate` to the dry-run JSON:

```text
realtime_projection_metric_20260611_trace_aligned_standard_outbox__realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
```

It matches the execute contract `projection_run_id`.

Preserved unchanged:

- `projection_time_policy`
- expected rows and expected distribution
- trace alignment
- rollback SQL path
- contract stage: `N3-B2-realtime-projection-execute-contract`
- preflight stage: `N3-B2-realtime-projection-execute-preflight`

## No-Write Proof

Target B2 scoped rows remain zero:

- `common_market_data_run=0`
- `common_market_data_quality_item=0`
- stock/index/board projection rows: `0/0/0`
- target outbox/inbox/checkpoint refs: `0/0/0`

## Forbidden Scope

This gate did not execute B2, did not write database rows, did not consume/update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start workers, did not modify scheduler, and did not execute rollback SQL.

## Next Gate

Return to runtime_control:

```text
N3_20260611_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_EXECUTE_FINAL_GATE_REVIEW_AFTER_DRY_RUN_COMPATIBILITY_REPAIR
```
