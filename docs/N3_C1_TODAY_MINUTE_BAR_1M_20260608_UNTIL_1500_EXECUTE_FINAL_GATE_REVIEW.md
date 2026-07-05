# N3 C1 Today Minute 20260608 Until 15:00 Execute Final Gate Review

Result: `PASS`

Gate: `N3_C1_TODAY_MINUTE_BAR_1M_20260608_UNTIL_1500_EXECUTE_FINAL_GATE_REVIEW`

Generated at: `2026-06-09T01:52:00.267143+08:00`

## Lineage

- source_market_data_run_id: `market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- today_minute_run_id: `today_minute_bar_1m_20260608_until_1500__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- for_trade_date: `20260608`
- latest_closed_minute: `2026-06-08T15:00:00+08:00`

## Planned Rows

- objects stock/index/board: `353/6/13`
- rows stock/index/board/total: `84720/1440/3120/89280`

## Adapter Temporal Proof

- `stock 600016 bars` target-date rows: `240`; pass=`true`
- `index 000905 index_bars` target-date rows: `240`; pass=`true`
- `board 881184 index_bars` target-date rows: `240`; pass=`true`

## Target Baseline

- run_exists: `False`
- target row counts: `{'stock_minute_bar_1m': 0, 'index_minute_bar_1m': 0, 'board_minute_bar_1m': 0, 'common_market_data_quality_item': 0, 'common_market_data_run': 0}`
- outbox/inbox refs: `0/0`

## Rollback

- rollback SQL: `sql/N3_C1_today_minute_bar_1m_20260608_until_1500_rollback.sql`
- hard-fail guard generated before DELETE/UPDATE
- no CASCADE/DROP/TRUNCATE expected

## Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_today_minute_bar_1m_once.py --c0-plan-path docs/N3_C0_today_minute_bar_1m_20260608_next_cutoff_dry_run.json --pre-backup-path docs/N3_C1_today_minute_bar_1m_20260608_until_1500_backup_before.json --post-backup-path docs/N3_C1_today_minute_bar_1m_20260608_until_1500_backup_after.json --json-report-path docs/N3_C1_TODAY_MINUTE_BAR_1M_20260608_UNTIL_1500_EXECUTE_REPORT.json --markdown-report-path docs/N3_C1_TODAY_MINUTE_BAR_1M_20260608_UNTIL_1500_EXECUTE_REPORT.md --rollback-sql-path sql/N3_C1_today_minute_bar_1m_20260608_until_1500_rollback.sql --for-trade-date 20260608 --today-minute-run-id today_minute_bar_1m_20260608_until_1500__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute --execute --user-confirmed
```

## Forbidden Scope Proof

- no execute performed by this artifact gate
- no DB write by this artifact gate
- no outbox/inbox/checkpoint consumption/update
- no N4/N5/N6 entry
- no worker / delivery / push / voice / mobile / sim / position / real trade / old system
