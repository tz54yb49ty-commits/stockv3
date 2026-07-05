# N5 Full Metric Union Historical Metadata Repair Execute Command Contract

Status: CONTRACT_PASS

This artifact only materializes the execute command candidate. It does not authorize execution.

## Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_n5_full_metric_union_metadata_repair.py --dsn postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3 --contract-path docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_CONTRACT.json --preflight-path docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_PREFLIGHT.json --dry-run-path docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_DRY_RUN.json --payload-path docs/N5_full_metric_union_historical_metadata_repair_payload.json --rollback-sql-path sql/N5_full_metric_union_historical_metadata_repair_20260605_rollback.sql --json-report-path docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_REPORT.json --markdown-report-path docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_REPORT.md --execute --user-confirmed
```

## Inputs

```text
contract=docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_CONTRACT.json
preflight=docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_PREFLIGHT.json
dry_run=docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_DRY_RUN.json
payload=docs/N5_full_metric_union_historical_metadata_repair_payload.json
rollback_sql=sql/N5_full_metric_union_historical_metadata_repair_20260605_rollback.sql
```

## Write Scope

```text
allowed_tables=common_action_event, common_event_outbox
allowed_payload_keys=blocked_reason, action_confirmation_metric_run_refs, metric_union_policy_version, metric_union_source_runs, metric_coverage_status, metric_missing_resolved, repair_trace
forbidden_fields=event_type, action_state, confirmation_status, action_mark, event_id, source_trigger_event_id, action_run_id, source_run_id, status, delivery_status
```

## Forbidden Scope

```text
consume_outbox=false
update_outbox_status=false
write_inbox_checkpoint=false
modify_N4=false
modify_N3=false
enter_N6=false
delivery/push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
worker_started=false
```

## Post-Review Artifacts

```text
execute_report_json=docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_REPORT.json
execute_report_markdown=docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_REPORT.md
post_review_json=docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_POST_REVIEW.json
post_review_markdown=docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_POST_REVIEW.md
```

## Validation

```text
json_payload_parse=PASS
payload_rows=605
payload_allowed_keys_only=true
rollback_static_check=PASS
rollback_hard_fail_before_update=true
rollback_has_no_delete_insert_truncate_drop_cascade=true
boundary_scan.n4_outbox_rows=605
boundary_scan.common_trigger_match_rows=605
boundary_scan.n5_outbox_pending.ActionBlocked=604
boundary_scan.n5_outbox_pending.ActionExecuted=1
boundary_scan.n5_downstream_inbox_refs=0
boundary_scan.n5_downstream_checkpoint_refs=0
boundary_scan.n5_delivery_attempt_refs=0
compileall=PASS
focused_tests.test_action_metadata_repair=PASS
focused_tests.test_action_star=PASS
full_unittest=PASS
full_unittest.tests_run=1573
git_diff_check=PASS
```
