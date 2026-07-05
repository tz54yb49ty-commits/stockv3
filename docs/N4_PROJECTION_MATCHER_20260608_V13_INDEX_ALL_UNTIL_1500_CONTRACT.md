# N4 Projection Matcher 20260608 Until 15:00 Contract

- result: `CONTRACT_PASS`
- execute_run_id: `trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry`
- consumer_name: `n4_projection_matcher_consumer_v1_until_1500_reprocess`
- matched/pending: `122/3770`
- HINT BUY/SELL: `116/6`
- P0/P1/P2 dry-run: `0/1/0`
- P0/P1/P2 preflight: `0/0/0`

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_projection_matcher_once.py --execute --user-confirmed --execute-run-id trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry --trigger-context-run-id trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute --snapshot-run-id realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute --projection-run-id realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute --consumer-name n4_projection_matcher_consumer_v1_until_1500_reprocess --dry-run-report-path docs/N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_1500_DRY_RUN.json --json-report-path docs/N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_1500_EXECUTE_REPORT.json --markdown-report-path docs/N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_1500_EXECUTE_REPORT.md --rollback-sql-path sql/N4_projection_matcher_20260608_v13_index_all_until_1500_v4_repair_retry_rollback.sql
```
