# N3 Intraday B1/C1/B2 Supervisor Report

- status: `ready`
- reason: `new_closed_minute_detected`
- for_trade_date: `20260611`
- latest_closed_minute: `2026-06-11T09:31:00+08:00`
- executed_child_command_count: `0`

## Child Steps
- `B1` run_id=`realtime_daily_snapshot_20260611_until_0931__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1` report=`docs/N3_B1_realtime_snapshot_20260611_until_0931_execute_report.json`
- `C1` run_id=`today_minute_bar_1m_20260611_until_0931__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1` report=`docs/N3_C1_today_minute_bar_1m_20260611_until_0931_execute_report.json`
- `B2` run_id=`realtime_projection_metric_20260611_until_0931__realtime_daily_snapshot_20260611_until_0931__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1` report=`docs/N3_B2_realtime_projection_20260611_until_0931_execute_report.json`

## Forbidden Scope

- no worker
- no outbox/inbox/checkpoint consume or update
- no N4/N5/N6
- no delivery/push/voice/mobile
- no proposal/order/trade/sim/position/PnL/real trade
