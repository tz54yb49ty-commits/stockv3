# N4 20260611 Trigger Semantic Smoke Preflight

Result: `PREFLIGHT_PASS`

## Baseline

```json
{
  "common_trigger_run": 0,
  "common_trigger_quality_item": 0,
  "common_trigger_state": 0,
  "common_trigger_match": 0,
  "common_event_outbox": 0,
  "common_event_inbox": 0,
  "common_event_consumer_checkpoint": 0
}
```

## Event Distribution

- TriggerMatched: `2`
- TriggerPendingMarketData: `2`
- TriggerStateChanged: `6`

## Planned Write Counts

```json
{
  "common_trigger_run": 1,
  "common_trigger_quality_item": 2,
  "common_event_inbox": 6,
  "common_event_consumer_checkpoint": 6,
  "common_trigger_state": 6,
  "common_trigger_match": 2,
  "common_event_outbox": 10
}
```

## Checks

```json
{
  "metadata_alignment_cleared": "PASS",
  "target_baseline_clean": "PASS",
  "n4_context_available": "PASS",
  "n3_source_pending_available": "PASS",
  "semantic_fixture_traceable": "PASS",
  "planned_TriggerMatched_gt_0": "PASS",
  "planned_TriggerPendingMarketData_gt_0": "PASS",
  "planned_TriggerStateChanged_gt_0": "PASS",
  "pending_and_state_changed_no_match_rows": "PASS",
  "n3_outbox_update_forbidden": "PASS",
  "n5_n6_forbidden": "PASS",
  "rollback_sql_generated": "PASS"
}
```

## Rollback

`sql/N4_20260611_trigger_semantic_smoke_rollback.sql` is generated with a hard-fail block before row removal and scoped to the smoke run and consumer.

## Forbidden Scope

No N4 execute, no worker start, no database write, no N3 outbox consume/update, no N5/N6, no delivery/push/voice/mobile, no sim/position/order/trade/real trade.
