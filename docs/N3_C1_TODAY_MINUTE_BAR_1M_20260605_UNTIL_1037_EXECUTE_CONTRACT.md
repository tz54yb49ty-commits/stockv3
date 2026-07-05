# N3-C1 Today Minute 20260605 Until 10:37 Execute Contract

- result: CONTRACT_PASS
- layer_role: N3_market_data
- today_minute_run_id: `today_minute_bar_1m_20260605_until_1037__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- source_market_data_run_id: `market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- for_trade_date: `20260605`
- latest_closed_minute: `2026-06-05T10:37:00+08:00`
- expected objects: stock=284 index=2 board=56 total=342
- expected rows: stock=19028 index=134 board=3752 total=22914
- writes_outbox: false
- allowed writes: common_market_data_run, common_market_data_quality_item, stock/index/board_minute_bar_1m
- rollback_sql: `sql/N3_C1_today_minute_bar_1m_20260605_until_1037_rollback.sql`

Execute command candidate:

```bash
PYTHONPATH=src:scripts python3 scripts/run_today_minute_bar_1m_once.py --c0-plan-path docs/N3_C0_today_minute_bar_1m_20260605_refresh_dry_run_report.json --for-trade-date 20260605 --today-minute-run-id today_minute_bar_1m_20260605_until_1037__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1 --rollback-sql-path sql/N3_C1_today_minute_bar_1m_20260605_until_1037_rollback.sql --json-report-path docs/N3_C1_today_minute_bar_1m_20260605_until_1037_execute_report.json --markdown-report-path docs/N3_C1_TODAY_MINUTE_BAR_1M_20260605_UNTIL_1037_EXECUTE_REPORT.md --execute --user-confirmed
```
