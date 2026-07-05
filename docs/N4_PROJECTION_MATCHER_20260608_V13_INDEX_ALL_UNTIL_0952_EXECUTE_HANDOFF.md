# N4 Projection Matcher Execute Handoff

Handoff result: `WAIT_N4_TRIGGER_EXECUTE_USER_CONFIRMATION`

Next layer role: `N4_trigger`

Next gate: `N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_USER_CONFIRMATION_GATE`

## Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_projection_matcher_once.py \
  --execute-run-id trigger_projection_matcher_execute_20260608_v13_index_all_until_0952 \
  --trigger-context-run-id trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --projection-run-id realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --snapshot-run-id realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --json-report-path docs/N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.json \
  --markdown-report-path docs/N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_projection_matcher_20260608_v13_index_all_until_0952_rollback.sql \
  --dry-run-report-path docs/N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_DRY_RUN.json \
  --execute --user-confirmed
```

Approved writes are limited to this N4 execute run's trigger run, quality items, inbox/checkpoint records, trigger state, trigger match, and N4 outbox rows.

Forbidden: N3 outbox status updates, market data pull, N5/N6, worker, delivery/push/voice/mobile, sim/position/pnl/real trade, proposal/order/trade, and old-system touch.
