# V3 20260612 Realtime Virtual Metric Writer Execute Blocked Post Review After Previous-Day Refs Repair

- result: `BLOCKED_POST_REVIEW_PASS`
- execute result: `BLOCKED`
- target_run_id: `action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1`

## Blocker

`source_snapshot_run_id` is still constrained by an FK to
`common_market_data_run(run_id)`.

The writer emitted:

```text
v3_realtime_virtual_metric_source_payload_20260612_no_snapshot_source
```

but that run id does not exist in `common_market_data_run`.

## Post-Failure Baseline

Target scoped rows remain zero:

- run/quality: `0/0`
- stock/index/board metric: `0/0/0`
- outbox/inbox/checkpoint refs: `0/0/0`
- N4/N5/N6 representative refs: `0`

## Rollback

`rollback_safe=true`; no rollback is required now because no target rows were committed.

## Next Gate

```text
V3_REALTIME_VIRTUAL_METRIC_SOURCE_SNAPSHOT_RUN_ID_FK_COMPATIBILITY_REPAIR_GATE
```
