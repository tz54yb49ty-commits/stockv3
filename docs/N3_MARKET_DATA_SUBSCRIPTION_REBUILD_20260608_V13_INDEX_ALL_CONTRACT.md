# N3 Market Data Subscription Rebuild 20260608 v13 Index-All Contract

Status: **CONTRACT_PASS**

This contract prepares an N3 subscription control-row registration for the active N2 v13 index-all run. It does not execute the subscription, pull market data, write minute/snapshot facts, consume outbox, or enter N4/N5/N6.

```text
source_condition_run_id=condition_layer_20260605_to_20260608_v13_index_all_execute
market_data_run_id=market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
source_trade_date=20260605
for_trade_date=20260608
prev_trade_date=20260605
source_scope rows stock/index/board=4241/169/267 total=4677
objects stock/index/board=1945/83/127 total=2155
candidate/subscription/pull_plan=5421/2899/9
required_data_kind realtime/minute/previous=2155/372/372
P0/P1/P2=0/0/0
```

## Future Execute Write Scope

- `common_market_data_run`: 1
- `common_market_data_quality_item`: 34
- `common_market_data_subscription_candidate`: 5421
- `common_market_data_subscription`: 2899
- `common_market_data_pull_plan`: 9
- `pull_plan.execute_allowed=false`
- minute/snapshot facts: 0
- outbox events: 0

## Input Boundary

N3 reads only the trading scope tables:

- `stock_minute_target_scope`
- `index_minute_target_scope`
- `board_minute_target_scope`

`condition_display_basis` is forbidden as an N3 input. The subscription dedup grain is:

```text
asset_kind + identity_key + required_data_kind + for_trade_date
```

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_market_data_subscription_execute.py \
  --source-condition-run-id condition_layer_20260605_to_20260608_v13_index_all_execute \
  --source-trade-date 20260605 \
  --for-trade-date 20260608 \
  --market-data-run-id market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --execute --user-confirmed \
  --pre-backup-path docs/N3_market_data_subscription_rebuild_20260608_v13_index_all_execute_backup_before.json \
  --post-backup-path docs/N3_market_data_subscription_rebuild_20260608_v13_index_all_execute_backup_after.json \
  --report-path docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_20260608_V13_INDEX_ALL_EXECUTE_REPORT.json \
  --markdown-report-path docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_20260608_V13_INDEX_ALL_EXECUTE_REPORT.md
```

## Rollback

Rollback SQL:
`sql/N3_market_data_subscription_rebuild_20260608_v13_index_all_rollback.sql`

The rollback hard-fails before row removal, is scoped to this N3 subscription run, does not delete N2 rows, does not delete market facts, and blocks if downstream references exist.
