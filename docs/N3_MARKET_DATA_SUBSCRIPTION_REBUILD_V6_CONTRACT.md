# N3 Market Data Subscription Rebuild V6 Contract

Status: CONTRACT_PASS

```text
source_condition_run_id=condition_layer_20260528_source_20260528_v6
market_data_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
source_trade_date=20260528
for_trade_date=20260529
prev_trade_date=20260528
source_scope rows stock/index/board=4251/169/875 total=5295
objects stock/index/board=2011/83/428 total=2522
candidate/subscription/pull_plan=5807/3034/9
required_data_kind realtime/minute/previous=2522/256/256
P0/P1/P2=0/0/0
```

## Future Execute Write Scope

- common_market_data_run: 1
- common_market_data_quality_item: 34
- common_market_data_subscription_candidate: 5807
- common_market_data_subscription: 3034
- common_market_data_pull_plan: 9
- pull_plan.execute_allowed=false
- minute/snapshot facts: 0
- outbox events: 0

## Input Boundary

N3 reads only stock/index/board_minute_target_scope for the trading subscription chain. condition_display_basis is forbidden as an N3 input.

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_market_data_subscription_execute.py \
  --source-condition-run-id condition_layer_20260528_source_20260528_v6 \
  --source-trade-date 20260528 \
  --for-trade-date 20260529 \
  --market-data-run-id market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6 \
  --execute --user-confirmed \
  --pre-backup-path docs/N3_market_data_subscription_rebuild_v6_execute_backup_before.json \
  --post-backup-path docs/N3_market_data_subscription_rebuild_v6_execute_backup_after.json \
  --report-path docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_V6_EXECUTE_REPORT.json \
  --markdown-report-path docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_V6_EXECUTE_REPORT.md
```

## Rollback

Rollback SQL: sql/N3_market_data_subscription_rebuild_v6_rollback.sql

The rollback hard-fails before row removal and is scoped to v6 N3 subscription control rows only.
