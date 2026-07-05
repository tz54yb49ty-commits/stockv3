# N4 Projection Matcher 20260608 v13 Index-All Contract

Result: `CONTRACT_PASS`

## Scope

- execute_run_id: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- trigger_context_run_id: `trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- projection_run_id: `realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- snapshot_run_id: `realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- consumer_name: `n4_projection_matcher_consumer_v1`

## Planned Inputs And Outputs

- accepted source `MarketSnapshotUpdated` events: `2155`
- context candidates: `4677`
- trigger output plan: `3920`
- TriggerMatched: `320`
- TriggerPendingMarketData: `3600`
- TriggerStateChanged: `0`
- matched by signal type: `B_BUY=313`, `S_SELL=7`
- pending by signal type: `B_BUY=1803`, `S_SELL=1797`
- board/BJ not-ready matched count: `0`

## Planned Writes

- common_trigger_run: `1`
- common_trigger_quality_item: `10`
- common_event_inbox: `2155`
- common_event_consumer_checkpoint: `2155`
- common_trigger_state: `3920`
- common_trigger_match: `320`
- common_event_outbox: `3920`
- N3 outbox status updates: `0`

## Execute Command Candidate

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

## Rollback

Rollback SQL: `sql/N4_projection_matcher_20260608_v13_index_all_until_0952_rollback.sql`

The rollback is hard-failed before the first `DELETE`, scoped to this execute run, must not delete N3 facts or N4 context rows, and must block if N5/N6 downstream refs exist.

## Forbidden Scope

No N3 outbox status update, no market data pull, no worker, no N5/N6, no delivery/push/voice/mobile, no sim/position/pnl/real trade, no proposal/order/trade, and no old-system touch.
