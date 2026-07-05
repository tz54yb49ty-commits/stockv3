# N4 20260611 Trigger Semantic Smoke Dry Run

Result: `DRY_RUN_PREFLIGHT_PASS`

## Scope

- smoke_run_id: `n4_worker_bounded_smoke_20260611_trigger_semantic_probe`
- consumer_name: `n4_trigger_worker_v1_bounded_smoke_20260611_trigger_semantic_probe`
- source_run_id: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- trigger_context_run_id: `trigger_context_snapshot_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- semantic_fixture_path: `docs/N4_20260611_TRIGGER_SEMANTIC_SMOKE_FIXTURE.json`

## Dry Run Summary

- accepted source events: `6`
- transition event plans: `10`
- TriggerMatched / TriggerPendingMarketData / TriggerStateChanged: `2/2/6`

## Planned Writes For Future Execute

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

## Caveat

This is a deterministic semantic smoke fixture using live 20260611 N3 source events, N4 localized context, and N3 snapshot prices. It is `fixture_only=true` and `not_new_market_decision=true`.

## Forbidden Scope

No N4 execute, no worker start, no database write, no N3 outbox consume/update, no N5/N6, no delivery/push/voice/mobile, no sim/position/order/trade/real trade.
