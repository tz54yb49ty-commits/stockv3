# N5 Metric-Aware Retry Dry Run 20260608 Until 09:52

- result: `DRY_RUN_PASS`
- action_run_id: `action_consumer_execute_20260608_until_0952_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry`
- source_trigger_run_id: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry`
- metric_run_id: `action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry`
- consumer_name: `n5_action_consumer_v1_until_0952_metric_aware_reprocess`
- P0/P1/P2: `0/0/0`

## Consumer Guard Proof
- alignment report: `ALIGNMENT_PASS`
- dedicated consumer: `n5_action_consumer_v1_until_0952_metric_aware_reprocess`
- n5_5_consumer_name_contract: `passed`
- dedicated inbox/checkpoint baseline: `0/0`

## N4 Input Proof
- TriggerMatched pending: `119`
- TriggerPendingMarketData pending: `3801`
- delivered/delivering: `0/0`
- common_trigger_match/state: `119/3920`

## N3 Metric Coverage Proof
- stock/index/board/total: `113/6/0/119`
- coverage: `119/119`
- missing: `0`
- opaque payload.action_confirmation trusted: `false`

## Planned Metric-Aware Distribution
- ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped: `0/119/0/0`

## Rollback Proof
- rollback SQL: `sql/N5_action_confirmation_20260608_until_0952_metric_aware_retry_rollback.sql`
- hard-fail before first executable DELETE/UPDATE: `True`
- no CASCADE/DROP/TRUNCATE: `True/True/True`

## Forbidden Scope Proof
- no N5 execute, no DB write, no outbox consumption/update, no N6, no worker, no delivery/push/voice/mobile, no sim/position/real trade, old system untouched.

## Allowed Execute Command
```bash
PYTHONPATH=src python3 scripts/run_action_consumer_once.py \
  --source-trigger-run-id trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry \
  --action-run-id action_consumer_execute_20260608_until_0952_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry \
  --consumer-name n5_action_consumer_v1_until_0952_metric_aware_reprocess \
  --baseline-report-path docs/N5_ACTION_CONFIRMATION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_BASELINE.json \
  --expected-read-event-count 3920 \
  --allow-source-run-id trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry \
  --execute --user-confirmed \
  --report-path docs/N5_ACTION_CONFIRMATION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_EXECUTE_REPORT.json \
  --markdown-report-path docs/N5_ACTION_CONFIRMATION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N5_action_confirmation_20260608_until_0952_metric_aware_retry_rollback.sql
```
