# N5 Worker Semantic Action Smoke Final Gate Review

Result: `PASS`

This gate only generated and reviewed artifacts. It did not execute N5, write the database, consume or update N4 outbox, enter N6, or start a worker.

## Source Readiness Proof

```text
source_trigger_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
TriggerMatched pending=556
delivered/delivering=0/0
selected_events=50
selected_events_all_pending=True
selected asset_kind distribution={"board": 50}
N4 outbox status update=0
```

## Metric Binding Proof

```text
metric_run_id=action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
metric_run status=passed
metric rows stock/index/board/total=412/60/84/556
selected deterministic join coverage=50/50
duplicate join key count=0
opaque payload.action_confirmation trusted=False
```

## Semantic Dry-Run Summary

```text
dry-run=DRY_RUN_PASS
contract=CONTRACT_PASS
preflight=PREFLIGHT_PASS
P0/P1/P2=0/0/0
ActionExecuted=0
ActionBlocked=50
ActionEligible=0
ActionSkipped=0
blocked_reason distribution={"price_confirmation_failed": 50}
```

## Planned Write Scope

```text
common_action_run=1
common_action_quality_item=0
stock_action_fact=0
index_action_fact=0
board_action_fact=50
stock_index_board_action_fact_total=50
common_action_event=50
n5_common_event_outbox=50
common_event_inbox=50
common_event_consumer_checkpoint=50
common_position_state=0
common_position_event=0
```

## Rollback Proof

```text
rollback SQL=sql/N5_worker_semantic_action_smoke_20260608_unified_output_retry_probe_rollback.sql
hard-fail before DELETE/UPDATE=True
guards N4/N5 delivered/delivering=True
guards N6/user/sim/order/trade/position refs=True
no CASCADE/DROP/TRUNCATE=True
rollback executed=False
```

## Forbidden Scope Proof

```text
worker_started=False
long_running_worker_started=False
N5_execute_entered=False
database_written=False
N4_outbox_updated_or_consumed=False
N5_outbox_consumed=False
N6_entered=False
delivery_push_voice_mobile=False
sim_position_pnl_real_trade=False
proposal_order_trade=False
old_system_touched=False
```

Allowed execute command:

```bash
PYTHONPATH=src:scripts python3 scripts/run_action_consumer_once.py \
  --semantic-action-smoke \
  --smoke-run-id n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe \
  --consumer-name n5_action_worker_v1_semantic_action_smoke_probe \
  --source-trigger-run-id trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --source-event-type TriggerMatched \
  --metric-run-id action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --max-events 50 \
  --max-runtime-seconds 120 \
  --heartbeat-interval-seconds 10 \
  --status-json docs/N5_WORKER_SEMANTIC_ACTION_SMOKE_STATUS.json \
  --stop-file tmp/n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe.stop \
  --json-report-path docs/N5_WORKER_SEMANTIC_ACTION_SMOKE_EXECUTE_REPORT.json \
  --markdown-report-path docs/N5_WORKER_SEMANTIC_ACTION_SMOKE_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N5_worker_semantic_action_smoke_20260608_unified_output_retry_probe_rollback.sql \
  --execute \
  --user-confirmed
```
