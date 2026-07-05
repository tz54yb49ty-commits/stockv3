# N5 Worker Larger Scope Semantic Smoke Final Gate Review

Result: `PASS`

Generated at: `2026-06-10T19:22:10+08:00`

Layer role: `runtime_control`

This final gate review only authorizes moving to the execute user-confirmation gate. It did not execute N5, did not write the database, did not consume or update N4/N5 outbox, did not enter N6, and did not start a worker.

## Gate Summary

```text
dry-run=DRY_RUN_PASS
contract=CONTRACT_PASS
preflight=PREFLIGHT_PASS
rollback_sql_exists=true
rollback_disabled_by_default=true
P0/P1/P2=0/0/0
```

## Planned Execution Boundary

```text
semantic_action_smoke=true
source_event_type=TriggerMatched
max_events=200
max_runtime_seconds=300
heartbeat_interval_seconds=10
N4 outbox status update=0
N5 outbox consumption/update=0
N6 entry=0
worker_started=false
long_running_worker_started=false
```

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_action_consumer_once.py \
  --semantic-action-smoke \
  --smoke-run-id n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe \
  --consumer-name n5_action_worker_v1_larger_scope_semantic_action_smoke_probe \
  --source-trigger-run-id trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --source-event-type TriggerMatched \
  --metric-run-id action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --max-events 200 \
  --max-runtime-seconds 300 \
  --heartbeat-interval-seconds 10 \
  --status-json docs/N5_WORKER_LARGER_SCOPE_SEMANTIC_SMOKE_STATUS.json \
  --stop-file tmp/n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe.stop \
  --json-report-path docs/N5_WORKER_LARGER_SCOPE_SEMANTIC_SMOKE_EXECUTE_REPORT.json \
  --markdown-report-path docs/N5_WORKER_LARGER_SCOPE_SEMANTIC_SMOKE_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe_rollback.sql \
  --execute \
  --user-confirmed
```

## Decision

Allowed next gate:

```text
N5_WORKER_LARGER_SCOPE_SEMANTIC_SMOKE_EXECUTE_USER_CONFIRMATION_GATE
```

This final gate review does not itself execute the command.
