# N4->N5 Chained Bounded Smoke Contract

Result: `CONTRACT_PASS`

Generated at: `2026-06-10T18:07:12+08:00`

Layer role: `runtime_control`

This gate only generated and reviewed artifacts. It did not execute N4 or N5, write the database, consume or update N4/N5 outbox, enter N6, or start a worker.

## Prerequisite Proof

```text
readiness=READINESS_PASS
N5 rollback readiness=READINESS_PASS
N5 rollout registration=REGISTRATION_PASS
N4 rollout registration refresh=REGISTRATION_PASS
N5 scoped consumption smoke=POST_REVIEW_PASS
N5 semantic action smoke=POST_REVIEW_PASS
```

## Source Readiness Proof

```text
source_trigger_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
TriggerMatched pending=556
delivered/delivering=0/0
selected_events=50
selected_events_all_pending=true
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
opaque payload.action_confirmation trusted=false
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
N5 common_event_outbox=50
common_event_inbox=50
common_event_consumer_checkpoint=50
common_position_state=0
common_position_event=0
N4 outbox status update=0
N5 outbox consumption/update=0
N6/user/delivery/sim/trade refs=0
```

## Runner Proof

```text
runner=scripts/run_action_consumer_once.py
mode=--semantic-action-smoke
requires --execute=true and --user-confirmed=true before write path
requires --smoke-run-id
requires --metric-run-id
bounded controls required=max_events,max_runtime_seconds,heartbeat_interval_seconds,status_json,stop_file
source_event_type_guard=TriggerMatched only
N4 outbox status update path=false
N5 outbox consumption path=false
N6 path=false
```

## Rollback Proof

```text
rollback SQL=sql/N4_N5_chained_bounded_smoke_20260608_unified_output_retry_probe_rollback.sql
hard-fail before DELETE/UPDATE=true
guards N4 source outbox delivered/delivering=true
guards N5 outbox delivered/delivering=true
guards N6/user/sim/order/trade/position refs=true
preserves N4/N3/N2/N1 facts and existing N5 lineages=true
no CASCADE/DROP/TRUNCATE=true
rollback executed=false
```

## Forbidden Scope Proof

```text
worker_started=false
long_running_worker_started=false
N4_execute_entered=false
N5_execute_entered=false
database_written=false
N4_outbox_updated_or_consumed=false
N5_outbox_consumed=false
N6_entered=false
delivery_push_voice_mobile=false
sim_position_pnl_real_trade=false
proposal_order_trade=false
old_system_touched=false
```

Allowed execute command:

```bash
PYTHONPATH=src:scripts python3 scripts/run_action_consumer_once.py \
  --semantic-action-smoke \
  --smoke-run-id n4_n5_chained_bounded_smoke_20260608_unified_output_retry_probe \
  --consumer-name n5_action_worker_v1_n4_n5_chained_bounded_smoke_probe \
  --source-trigger-run-id trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --source-event-type TriggerMatched \
  --metric-run-id action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --max-events 50 \
  --max-runtime-seconds 120 \
  --heartbeat-interval-seconds 10 \
  --status-json docs/N4_N5_CHAINED_BOUNDED_SMOKE_STATUS.json \
  --stop-file tmp/n4_n5_chained_bounded_smoke_20260608_unified_output_retry_probe.stop \
  --json-report-path docs/N4_N5_CHAINED_BOUNDED_SMOKE_EXECUTE_REPORT.json \
  --markdown-report-path docs/N4_N5_CHAINED_BOUNDED_SMOKE_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_N5_chained_bounded_smoke_20260608_unified_output_retry_probe_rollback.sql \
  --execute \
  --user-confirmed
```

