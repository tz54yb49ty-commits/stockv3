# N3/N4/N5 20260602 11:05 After B2 Next Gate

- completed_b2: {'projection_run_id': 'realtime_projection_metric_20260602_live3__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1', 'status': 'passed', 'rows': {'stock': 1976, 'index': 83, 'board': 428, 'total': 2487}, 'post_review': 'docs/N3_B2_20260602_LIVE3_EXECUTE_POST_REVIEW.json', 'rollback_safe': True}
- next_stage: N4 trigger context snapshot execute
- next_status: PASS_WAIT_USER_CONFIRMATION
- expected_rows: {'board': 1006, 'index': 220, 'stock': 4715, 'total': 5941}
- current_rows: {'common_trigger_run': 0, 'stock': 0, 'index': 0, 'board': 0}
- rollback_sql: sql/N4_20260602_trigger_context_snapshot_rollback.sql
- downstream_after_next: {'n4_matcher_status': 'BLOCKED_UNTIL_N4_CONTEXT_EXECUTE', 'n4_matcher_current_run_rows': 0, 'n5_status': 'BLOCKED_UNTIL_N4_MATCHER_EXECUTE', 'n5_current_run_rows': 0}
- boundary: {'outbox_total': 153828, 'inbox_total': 56170, 'checkpoint_total': 4368, 'worker_started': False, 'n5_n6_touched': False, 'database_modified_by_this_review': False}

## Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_context_snapshot_execute.py --condition-run-id condition_layer_20260601_source_20260601_v1 --for-trade-date 20260602 --json-report-path docs/N4_20260602_trigger_context_snapshot_execute_report.json --markdown-report-path docs/N4_20260602_TRIGGER_CONTEXT_SNAPSHOT_EXECUTE_REPORT.md --rollback-sql-path sql/N4_20260602_trigger_context_snapshot_rollback.sql
```
