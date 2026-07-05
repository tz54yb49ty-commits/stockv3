# V3 20260617 N3 B2 Action Confirmation Full Scope Metric Execute Report

- result: `EXECUTE_PASS`
- metric_run_id: `action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1`
- identity_metric_rows: `2048`
- canonical_condition_distribution: `{"BUY": 1939, "BUY:FULL": 109, "BUY_HINT": 59, "SELL": 2020, "SELL:FULL": 28, "SELL_HINT": 165}`
- quality_visible_blockers: `6`
- source_snapshot_quality_status_distribution: `{"partial": 208, "passed": 1840}`
- rollback_sql: `sql/V3_20260617_n3_b2_action_confirmation_full_scope_metric_rollback.sql`
- forbidden_scope: no outbox/inbox/checkpoint, no worker, no N4/N5/N6, no voice/mobile/sim/order/trade.
