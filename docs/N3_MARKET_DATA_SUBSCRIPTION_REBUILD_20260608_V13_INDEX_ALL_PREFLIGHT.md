# N3 Market Data Subscription Rebuild 20260608 v13 Index-All Preflight

Status: **PREFLIGHT_PASS**

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

## Baseline

```json
{
  "common_market_data_run": 0,
  "common_market_data_quality_item": 0,
  "common_market_data_subscription_candidate": 0,
  "common_market_data_subscription": 0,
  "common_market_data_pull_plan": 0
}
```

Fact baseline total: 0

Projection refs total: 0

Event/downstream refs total: 0

## Boundary

No subscription execute, no market data pull, no minute/snapshot fact write, no outbox/inbox/checkpoint write or consume, no N4/N5/N6, no worker.

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
