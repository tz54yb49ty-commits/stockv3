# V3 20260615 C1 Today Minute Refresh Preflight

- result: `PREFLIGHT_PASS`
- P0/P1/P2: `0/0/0`
- source_market_data_run_id: `market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1`
- today_minute_run_id: `today_minute_bar_1m_20260615_until_1005_action_confirmation_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1`
- single-source C1 compatibility: `PASS`
- target C1 baseline: `0`
- exact 10:05 minute rows: `0`
- expected rows: `stock/index/board/total = 28175/35/0/28210`
- forbidden scope: no C1 execute, no market pull, no DB write, no outbox/inbox/checkpoint, no N4/N5/N6

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_today_minute_bar_1m_once.py --c0-plan-path docs/V3_20260615_C1_TODAY_MINUTE_REFRESH_UNTIL_1005_FOR_ACTION_CONFIRMATION_DRY_RUN.json --json-report-path docs/V3_20260615_C1_TODAY_MINUTE_REFRESH_UNTIL_1005_FOR_ACTION_CONFIRMATION_EXECUTE_REPORT.json --markdown-report-path docs/V3_20260615_C1_TODAY_MINUTE_REFRESH_UNTIL_1005_FOR_ACTION_CONFIRMATION_EXECUTE_REPORT.md --rollback-sql-path sql/V3_20260615_C1_today_minute_refresh_until_1005_for_action_confirmation_rollback.sql --for-trade-date 20260615 --today-minute-run-id today_minute_bar_1m_20260615_until_1005_action_confirmation_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1 --execute --user-confirmed
```

