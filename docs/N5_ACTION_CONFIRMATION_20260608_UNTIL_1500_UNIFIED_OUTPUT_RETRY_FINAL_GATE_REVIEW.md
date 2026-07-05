# N5 20260608 Until 15:00 Unified Output Retry Final Gate Review

- result: PASS
- dry_run: DRY_RUN_PASS
- contract: CONTRACT_PASS
- preflight: PREFLIGHT_PASS
- P0/P1/P2: 0/0/0
- source_trigger_run_id: `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- metric_run_id: `action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- action_run_id: `action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- consumer_name: `n5_action_consumer_v1_until_1500_unified_output_retry`

## Planned Distribution

```text
ActionExecuted=7
ActionBlocked=549
ActionEligible=0
ActionSkipped=0
```

## Metric Binding

```text
metric rows stock/index/board/total=412/60/84/556
coverage=556/556
opaque payload.action_confirmation trusted=false
```

## Planned Writes

```text
{
  "common_action_run": 1,
  "common_action_quality_item": 0,
  "stock_action_fact": 412,
  "index_action_fact": 60,
  "board_action_fact": 84,
  "common_action_event": 556,
  "common_event_outbox": 556,
  "common_event_inbox": 556,
  "common_event_consumer_checkpoint": 541,
  "accepted_event_count": 556,
  "checkpoint_plan_entry_count": 541,
  "checkpoint_physical_watermark_rows": 541,
  "common_position_state": 0,
  "common_position_event": 0
}
```

## Rollback

```text
rollback_sql=sql/N5_action_confirmation_20260608_until_1500_unified_output_retry_rollback.sql
hard_fail_before_first_delete_update=True
guards_delivered_delivering=True
guards_downstream_refs=True
```

## Allowed Execute Command

```bash
PYTHONPATH=src python3 scripts/run_action_consumer_once.py --source-trigger-run-id trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry --action-run-id action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry --consumer-name n5_action_consumer_v1_until_1500_unified_output_retry --baseline-report-path docs/N5_ACTION_CONFIRMATION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_CONTRACT.json --expected-read-event-count 556 --allow-source-run-id trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry --execute --user-confirmed --report-path docs/N5_ACTION_CONFIRMATION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_REPORT.json --markdown-report-path docs/N5_ACTION_CONFIRMATION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_REPORT.md --rollback-sql-path sql/N5_action_confirmation_20260608_until_1500_unified_output_retry_rollback.sql
```
