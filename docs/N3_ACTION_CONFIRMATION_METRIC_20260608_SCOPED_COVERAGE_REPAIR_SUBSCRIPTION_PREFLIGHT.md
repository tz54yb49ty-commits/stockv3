# Preflight

- stage: `N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_PREFLIGHT`
- market_data_run_id: `market_data_subscription_20260608_action_metric_coverage_repair_v1__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry`
- result: `PREFLIGHT_PASS`
- P0/P1/P2: `0/0/0`
- expected_objects: `{'stock': 256, 'index': 48, 'board': 77}`
- required_data_kind_counts: `None`
- rollback_sql: `sql/N3_action_confirmation_metric_20260608_scoped_coverage_repair_subscription_rollback.sql`

Forbidden scope: no market-data facts, no outbox/inbox/checkpoint, no N4/N5/N6, no worker, no old system, no trading.
