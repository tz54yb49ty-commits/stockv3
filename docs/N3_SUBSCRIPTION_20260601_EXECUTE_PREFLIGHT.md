# N3 Subscription 20260601 Execute Preflight

## Result

```text
PREFLIGHT_PASS
layer_role = N3_market_data
market_data_run_id = market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6
source_condition_run_id = condition_layer_20260529_source_20260529_v6
P0/P1/P2 = 0/1/0
blocked_reasons = []
```

## Baseline

```text
common_market_data_run = 0
common_market_data_subscription_candidate = 0
common_market_data_subscription = 0
common_market_data_pull_plan = 0
common_market_data_quality_item = 0
common_event_outbox = 0
common_event_inbox = 0
common_event_consumer_checkpoint_refs = 0
```

## Calendar Warning

```text
20260601 common_trade_calendar detail row missing.
```

This warning does not block subscription control-row execute. It does block or limit later realtime snapshot readiness until a N1/calendar gate provides the missing detail row.

## Execute Boundary

Execute is allowed to write only:

```text
common_market_data_run
common_market_data_quality_item
common_market_data_subscription_candidate
common_market_data_subscription
common_market_data_pull_plan
```

Execute remains forbidden from:

```text
market data facts
outbox/inbox/checkpoint
N4/N5/N6
worker
old system
real trading
```
