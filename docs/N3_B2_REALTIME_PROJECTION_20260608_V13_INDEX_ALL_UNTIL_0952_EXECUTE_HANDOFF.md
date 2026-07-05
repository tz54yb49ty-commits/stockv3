# N3 B2 Realtime Projection 20260608 v13 Index-All Execute Handoff

- handoff_result: `WAIT_N3_MARKET_DATA_USER_CONFIRMATION`
- layer_role: `runtime_control`
- next_layer_role: `N3_market_data`
- projection_run_id: `realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`

## Current State

B2 execute has not run yet.

| item | value |
|---|---:|
| common_market_data_run | 0 |
| stock_realtime_projection_metric | 0 |
| index_realtime_projection_metric | 0 |
| board_realtime_projection_metric | 0 |
| common_market_data_quality_item | 0 |
| common_event_outbox | 0 |

## Approved Execute Scope

Expected projection rows:

| asset | rows |
|---|---:|
| stock | 1945 |
| index | 83 |
| board | 127 |
| total | 2155 |

Allowed write scope is limited to:

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_realtime_projection_metric`
- `index_realtime_projection_metric`
- `board_realtime_projection_metric`

## Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_realtime_projection_metric_once.py \
  --contract-path docs/N3_B2_realtime_projection_20260608_v13_index_all_until_0952_execute_contract.json \
  --preflight-path docs/N3_B2_realtime_projection_20260608_v13_index_all_until_0952_execute_preflight.json \
  --dry-run-path docs/N3_B2_realtime_projection_20260608_v13_index_all_until_0952_dry_run.json \
  --projection-run-id realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --for-trade-date 20260608 \
  --execute --user-confirmed \
  --json-report-path docs/N3_B2_REALTIME_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.json \
  --markdown-report-path docs/N3_B2_REALTIME_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N3_B2_realtime_projection_20260608_v13_index_all_until_0952_rollback.sql
```

## Forbidden Scope

- runtime_control did not execute B2.
- rollback SQL was not executed.
- no outbox/inbox/checkpoint was consumed or updated.
- no worker was started.
- no N4/N5/N6 facts were written.
- no delivery/push/voice/mobile/sim/position/pnl/real_trade/proposal/order/trade was entered.
