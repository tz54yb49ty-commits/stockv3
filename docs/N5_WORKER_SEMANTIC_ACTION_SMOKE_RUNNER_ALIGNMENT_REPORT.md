# N5 Worker Semantic Action Smoke Runner Alignment Report

Result: `ALIGNMENT_PASS`

## Scope

This gate aligned a bounded semantic action-confirmation smoke runner path for N5.

No N5 smoke was executed in this gate. No database writes were performed. No N4 outbox was consumed or updated. No N5 outbox was consumed. No N6, delivery, push, voice, mobile, sim, position, PnL, proposal, order, trade, real-trade, worker, or old-system path was entered.

## Root Cause

`N5_WORKER_SEMANTIC_ACTION_SMOKE_READINESS_GATE` was blocked because the normal action-confirmation runner read all pending `TriggerMatched` rows for the source run and did not enforce bounded worker smoke controls. The existing bounded controls were only wired to `--consumption-only-smoke`, which writes no action facts/events/outbox.

## Code Repair Summary

Updated `scripts/run_action_consumer_once.py`:

```text
--semantic-action-smoke
--metric-run-id
```

The runner now dispatches explicit semantic smoke requests to `run_semantic_action_smoke_once()`.

Updated `src/ashare_v3/action/execute.py`:

```text
run_semantic_action_smoke_once
fetch_semantic_action_smoke_outbox_rows
build_semantic_action_smoke_contract_from_rows
semantic_action_smoke_baseline_report
build_semantic_action_smoke_quality_items
build_semantic_action_smoke_status
```

## Bounded Semantic Runner Proof

The semantic smoke path requires:

```text
--semantic-action-smoke
--smoke-run-id
--consumer-name
--source-trigger-run-id
--source-event-type TriggerMatched
--metric-run-id
--max-events
--max-runtime-seconds
--heartbeat-interval-seconds
--status-json
--stop-file
--execute
--user-confirmed
```

The N4 source query is bounded:

```text
source_layer='N4_trigger'
source_run_id=<source-trigger-run-id>
status='pending'
event_type=ANY(<source-event-type>)
ORDER BY partition_key, event_time, outbox_id, event_id
LIMIT <max-events>
```

Missing `--execute`, missing `--user-confirmed`, missing `--smoke-run-id`, missing `--metric-run-id`, non-`TriggerMatched` source event types, missing bounded controls, or a pre-existing stop file blocks before DB write.

## Metric Binding Proof

The semantic smoke path requires the metric run id:

```text
action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
```

The path binds that run through deterministic N3 action-confirmation metric join and sets:

```text
opaque_action_confirmation_payload_trusted=false
deterministic_join_required=true
```

The dedicated semantic smoke consumer is only allowed through an internal baseline strategy that binds the source trigger run and metric run id.

## Planned Future Write Scope

Only a later execute final gate may authorize writes. When authorized, the semantic smoke path uses normal N5 action-confirmation writes, scoped to the smoke run id and consumer:

```text
common_action_run
common_action_quality_item
stock_action_fact
index_action_fact
board_action_fact
common_action_event
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
```

## Forbidden Scope Proof

This alignment gate did not execute the runner and did not write the database.

The semantic smoke runner does not update N4 outbox status and does not enter downstream layers:

```text
N4 outbox status update=0
N5 outbox consumption=0
N6/user refs=0
delivery/push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
worker_started=false
old_system_touched=false
```

The existing consumption-only smoke path remains unchanged and tested.

## Validation

```text
PYTHONPATH=src python3 -m unittest tests.test_action_execute.ActionExecuteRunnerContractTest.test_semantic_action_smoke_cli_aliases_parse tests.test_action_execute.ActionExecuteRunnerContractTest.test_semantic_action_smoke_blocks_without_metric_run_id_or_double_confirmation tests.test_action_execute.ActionExecuteRunnerContractTest.test_semantic_action_smoke_respects_max_events_and_binds_metric_run_id tests.test_action_execute.ActionExecuteRunnerContractTest.test_consumption_only_smoke_plans_only_run_quality_inbox_checkpoint
PASS
```

Full validation is recorded in the JSON report.

```text
PYTHONPATH=src python3 -m unittest tests/test_action_dry_run.py tests/test_action_execute.py
PASS: 73 tests

python3 -m compileall src/ashare_v3/action scripts tests
PASS

python3 -m json.tool docs/N5_WORKER_SEMANTIC_ACTION_SMOKE_RUNNER_ALIGNMENT_REPORT.json
PASS

git diff --check
PASS
```

## Decision

`ALIGNMENT_PASS`

It is allowed to return to runtime_control and re-enter:

```text
N5_WORKER_SEMANTIC_ACTION_SMOKE_CONTRACT_GATE
```
