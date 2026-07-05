# N3 Market Data Subscription Rebuild V6 Preflight

Status: PREFLIGHT_PASS

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
