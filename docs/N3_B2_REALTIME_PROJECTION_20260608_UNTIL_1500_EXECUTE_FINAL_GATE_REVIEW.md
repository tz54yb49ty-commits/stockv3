# N3 B2 Realtime Projection 20260608 Until 15:00 Execute Final Gate Review

- result: `PASS`
- projection_run_id: `realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- expected rows: `{"board": 127, "index": 83, "stock": 1945, "total": 2155}`
- ready/not_ready: `372/1783`
- P0/P1/P2: `0/1/0`

## Boundary

- writes_outbox: `false`
- consumes_outbox: `false`
- downstream_layers_touched: `false`
- worker_started: `false`

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_realtime_projection_metric_once.py --contract-path docs/N3_B2_realtime_projection_20260608_v13_index_all_until_1500_execute_contract.json --preflight-path docs/N3_B2_realtime_projection_20260608_v13_index_all_until_1500_execute_preflight.json --dry-run-path docs/N3_B2_realtime_projection_20260608_v13_index_all_until_1500_dry_run.json --projection-run-id realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute --for-trade-date 20260608 --execute --user-confirmed --json-report-path docs/N3_B2_REALTIME_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_1500_EXECUTE_REPORT.json --markdown-report-path docs/N3_B2_REALTIME_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_1500_EXECUTE_REPORT.md --rollback-sql-path sql/N3_B2_realtime_projection_20260608_v13_index_all_until_1500_rollback.sql
```
