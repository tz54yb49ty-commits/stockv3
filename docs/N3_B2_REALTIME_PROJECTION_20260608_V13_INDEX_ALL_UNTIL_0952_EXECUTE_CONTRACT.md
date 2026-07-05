# N3 B2 Realtime Projection 20260608 v13 Index-All Until 09:52 Execute Contract

- result: `CONTRACT_PASS`
- projection_run_id: `realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- generated_at_utc: `2026-06-08T02:17:45.337636+00:00`

## Source Runs

| key | value |
|---|---|
| source_condition_run_id | `condition_layer_20260605_to_20260608_v13_index_all_execute` |
| subscription_run_id | `market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute` |
| snapshot_run_id | `realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute` |
| preload_run_id | `previous_day_minute_preload_20260605__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute` |
| preload_run_ids | `["previous_day_minute_preload_20260605__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"]` |
| today_minute_run_id | `today_minute_bar_1m_20260608_until_0952__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute` |
| today_minute_run_ids | `["today_minute_bar_1m_20260608_until_0952__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"]` |

## Allowed Writes

| key | value |
|---|---|
| allowed_write_tables | `["common_market_data_run", "common_market_data_quality_item", "stock_realtime_projection_metric", "index_realtime_projection_metric", "board_realtime_projection_metric"]` |
| writes_outbox | `False` |
| consumes_outbox | `False` |

## Expected Rows

| key | value |
|---|---|
| stock | `1945` |
| index | `83` |
| board | `127` |
| total | `2155` |

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_realtime_projection_metric_once.py --contract-path docs/N3_B2_realtime_projection_20260608_v13_index_all_until_0952_execute_contract.json --preflight-path docs/N3_B2_realtime_projection_20260608_v13_index_all_until_0952_execute_preflight.json --dry-run-path docs/N3_B2_realtime_projection_20260608_v13_index_all_until_0952_dry_run.json --projection-run-id realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute --for-trade-date 20260608 --execute --user-confirmed --json-report-path docs/N3_B2_REALTIME_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.json --markdown-report-path docs/N3_B2_REALTIME_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.md --rollback-sql-path sql/N3_B2_realtime_projection_20260608_v13_index_all_until_0952_rollback.sql
```

## Rollback

`sql/N3_B2_realtime_projection_20260608_v13_index_all_until_0952_rollback.sql`
