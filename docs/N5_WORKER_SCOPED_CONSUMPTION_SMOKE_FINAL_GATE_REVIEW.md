# N5 Worker Scoped Consumption Smoke Final Gate Review

Result: `PASS`

This gate generated and reviewed artifacts only. It did not start a worker, execute N5, write action facts/events/outbox, consume or update N4 outbox, or enter N6.

## Source Readiness Proof

```text
TriggerMatched pending=556
selected_events=50
selected_events_all_pending=true
delivered/delivering=0/0
N4 outbox status update=0
N4 outbox consumption=0
```

## Dry-Run / Contract / Preflight

```text
readiness=READINESS_PASS
runner_alignment=ALIGNMENT_PASS
dry-run=DRY_RUN_PASS
contract=CONTRACT_PASS
preflight=PREFLIGHT_PASS
P0/P1/P2=0/0/0
```

## Planned Write Scope

```text
common_action_run=1
common_action_quality_item=6
common_event_inbox=50
common_event_consumer_checkpoint=50
stock/index/board_action_fact=0/0/0
common_action_event=0
N5 common_event_outbox=0
ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped=0
N4 outbox update=0
N6/user/delivery/sim/trade refs=0
```

## Rollback Proof

Rollback draft:

```text
sql/N5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe_rollback.sql
```

The rollback draft hard-fails before the first `DELETE`/`UPDATE`, guards N4/N5 downstream refs, preserves N4 outbox status and upstream facts, and contains no `CASCADE`, `DROP`, or `TRUNCATE`.

Allowed execute command:

```bash
PYTHONPATH=src:scripts python3 scripts/run_action_consumer_once.py \
  --consumption-only-smoke \
  --smoke-run-id n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe \
  --consumer-name n5_action_worker_v1_scoped_consumption_smoke_probe \
  --source-trigger-run-id trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --source-event-type TriggerMatched \
  --max-events 50 \
  --max-runtime-seconds 120 \
  --heartbeat-interval-seconds 10 \
  --status-json docs/N5_WORKER_SCOPED_CONSUMPTION_SMOKE_STATUS.json \
  --stop-file tmp/n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe.stop \
  --json-report-path docs/N5_WORKER_SCOPED_CONSUMPTION_SMOKE_EXECUTE_REPORT.json \
  --markdown-report-path docs/N5_WORKER_SCOPED_CONSUMPTION_SMOKE_EXECUTE_REPORT.md \
  --execute \
  --user-confirmed
```

Allowed next gate: `N5_WORKER_SCOPED_CONSUMPTION_SMOKE_EXECUTE_USER_CONFIRMATION_GATE`.
