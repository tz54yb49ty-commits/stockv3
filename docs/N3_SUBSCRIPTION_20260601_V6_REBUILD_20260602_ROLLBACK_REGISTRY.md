# N3 Subscription 20260601 v6 Rebuild Rollback Registry

Status: `ROLLBACK_REGISTRY_PASS`

## Scope

```text
market_data_run_id = market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1
source_condition_run_id = condition_layer_20260529_source_20260529_v6
rollback_sql = sql/N3_subscription_20260601_v6_rebuild_20260602_rollback.sql
```

The rollback is scoped only to the rebuild subscription control rows and does
not affect the existing passed run:

```text
market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6
```

## Hard-Fail Guards

The SQL raises before the first `DELETE` if any scoped downstream refs exist:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
downstream common_market_data_run
B1 realtime snapshot facts
A1/C1 minute facts
previous-day preload status
B2 realtime projection metrics
action-confirmation projection metrics
EOD settlement facts
N4/N5/N6/user/voice/mobile/sim/position/real-trade refs
```

## Delete Scope

Allowed deletes are limited to:

```text
common_market_data_pull_plan
common_market_data_subscription
common_market_data_subscription_candidate
common_market_data_quality_item
common_market_data_run
```

No rollback is executed in this gate. Subscription rebuild execute still
requires a separate explicit final gate.
