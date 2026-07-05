# N3-B2 20260602 Live3 Execute Final Gate

status = PASS_WAIT_USER_CONFIRMATION
projection_run_id = realtime_projection_metric_20260602_live3__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
today_minute_run_id = today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1

## Expected Rows

```text
stock/index/board/total = 1976 / 83 / 428 / 2487
ready_rows = 819
not_ready_rows = 1668
ready_by_asset = {'stock': 765, 'index': 54}
not_ready_by_asset = {'stock': 1211, 'index': 29, 'board': 428}
projection_signal_status = {'unknown': 1668, 'up_volume_shrinking': 118, 'down_volume_expanding': 55, 'up_volume_flat': 125, 'flat': 127, 'up_volume_expanding': 83, 'down_volume_flat': 93, 'down_volume_shrinking': 218}
P0/P1/P2 = 0/3/0
```

## Boundary

```text
writes_outbox = false
updates_market_snapshot_payload = false
consumes_outbox = false
downstream_layers_touched = false
worker_started = false
execute_authorized = false
blocked_reasons = []
```

## Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_realtime_projection_metric_once.py \
  --contract-path docs/N3_B2_realtime_projection_20260602_live3_execute_contract.json \
  --preflight-path docs/N3_B2_realtime_projection_20260602_live3_execute_preflight.json \
  --dry-run-path docs/N3_B2_realtime_projection_20260602_live3_dry_run.json \
  --json-report-path docs/N3_B2_realtime_projection_20260602_live3_execute_report.json \
  --markdown-report-path docs/N3_B2_REALTIME_PROJECTION_20260602_LIVE3_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N3_B2_realtime_projection_20260602_live3_rollback.sql \
  --projection-run-id realtime_projection_metric_20260602_live3__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1 \
  --for-trade-date 20260602 \
  --execute \
  --user-confirmed
```
