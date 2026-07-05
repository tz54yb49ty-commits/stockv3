# N4 20260605 Execute Contract

- result: `CONTRACT_PASS`
- layer_role: `N4_trigger`
- execute_authorized: `false`
- execute_run_id: `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- context_run_id: `trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1`
- snapshot_run_id: `realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- projection_run_id: `realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`

## Input Contract

- consumes_n3_outbox: `false`
- reads_fact_only_b1_snapshot: `true`
- reads_b2_projection_facts_for_trace_compatible_projection_matches: `true`
- uses_old_outbox_consuming_projection_matcher_execute_route: `false`
- pulls_market_data: `false`
- enters_n5_n6: `false`

## Matched-Only Persistence

Only valid N5-entry `TriggerMatched` rows are planned for future persistence.

- local ordinary matched: `1262`
- B2 projection matched: `275`
- valid N5-entry TriggerMatched total: `1537`
- invalid_n5_entry_count: `0`

Suppressed from N5 entry:

- local TriggerPendingMarketData shadow: `8632`
- local TriggerStateChanged shadow: `9894`
- projection TriggerPendingMarketData shadow: `3034`
- projection not_matched: `1809`
- board quality-visible not_ready: `428`

## Expected Writes After Future Final Confirmation

- common_trigger_run: `1`
- common_trigger_state: `1537`
- common_trigger_match: `1537`
- common_event_outbox: `1537`
- TriggerMatched: `1537`
- TriggerPendingMarketData: `0`
- TriggerStateChanged: `0`

## Runner Readiness

- ready: `true`
- runner: `scripts/run_n4_20260605_matched_only_execute_once.py`
- double confirmation required: `true`
- old projection execute route used: `false`

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_n4_20260605_matched_only_execute_once.py \
  --execute-run-id trigger_execute_20260605_condition_layer_20260604_source_20260604_v1 \
  --trigger-context-run-id trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1 \
  --snapshot-run-id realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1 \
  --projection-run-id realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1 \
  --contract-path docs/N4_20260605_execute_contract.json \
  --preflight-path docs/N4_20260605_execute_preflight.json \
  --local-dry-run-json-path docs/N4_20260605_local_trigger_dry_run_report.json \
  --projection-dry-run-json-path docs/N4_20260605_projection_matcher_dry_run_report.json \
  --rollback-sql-path sql/N4_20260605_execute_rollback.sql \
  --execute \
  --user-confirmed
```

## Rollback

- rollback_sql: `sql/N4_20260605_execute_rollback.sql`
- hard_fail_before_delete_required: `true`
- delete_scope: `execute_run_id only`
- delete_tables: `common_event_outbox`, `common_trigger_match`, `common_trigger_state`, `common_trigger_quality_item`, `common_trigger_run`
