# N5 Worker Scoped Consumption Smoke Contract

Result: `CONTRACT_PASS`

This gate only generated and reviewed artifacts. It did not start a worker, execute N5, write action facts/events/outbox, consume or update N4 outbox, or enter N6.

## Source Readiness Proof

```text
source_trigger_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
TriggerMatched pending=556
delivered/delivering=0/0
selected_events=50
selected_events_all_pending=true
selected distinct event_id/dedup_key/partition_key=50/50/50
invalid BUY_HINT/SELL_HINT runtime_signal_type=0
n5_entry_allowed=true=556/556
N4 outbox status update=0
```

## Runner Consumption-Only Proof

```text
runner alignment=ALIGNMENT_PASS
flag=--consumption-only-smoke
dispatch=run_consumption_only_smoke_once
normal action execute path reused=false
bounded controls=max_events/max_runtime/heartbeat/status_json/stop_file
runner plan result=READY
runner blockers=0
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
N4 outbox status update=0
N6/user/delivery/sim/trade refs=0
```

## Quality

```text
P0/P1/P2=0/0/0
```

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
