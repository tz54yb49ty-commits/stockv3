# N5 Worker Scoped Consumption Smoke Runner Alignment Report

Result: `ALIGNMENT_PASS`

## Scope

This gate aligned the N5 run-once entrypoint with a dedicated bounded consumption-only smoke path.

No N5 execute was run in this gate. No database writes were performed. No N4/N5 outbox was consumed or updated. No N6, delivery, push, voice, mobile, sim, position, PnL, proposal, order, trade, worker, or old-system path was entered.

## Modified Files

```text
scripts/run_action_consumer_once.py
src/ashare_v3/action/execute.py
tests/test_action_execute.py
docs/N5_WORKER_SCOPED_CONSUMPTION_SMOKE_RUNNER_ALIGNMENT_REPORT.md
docs/N5_WORKER_SCOPED_CONSUMPTION_SMOKE_RUNNER_ALIGNMENT_REPORT.json
```

## Runner Consumption-Only Proof

The runner now supports an explicit `--consumption-only-smoke` mode. This mode dispatches to `run_consumption_only_smoke_once()` and does not use the normal action-confirmation transaction path.

Supported smoke CLI controls:

```text
--consumption-only-smoke
--smoke-run-id
--consumer-name
--source-trigger-run-id
--source-event-type
--max-events
--max-runtime-seconds
--heartbeat-interval-seconds
--status-json
--stop-file
```

Legacy aliases remain compatible:

```text
--source-run-id
--json-report-path
--report-path
```

Missing `--execute`, missing `--user-confirmed`, missing `--smoke-run-id`, unsupported `--source-event-type`, missing bounded controls, or a pre-existing stop file blocks before DB write.

## Allowed Write Scope

When a future execute gate explicitly authorizes this mode, the transaction path only writes:

```text
common_action_run
common_action_quality_item
common_event_inbox
common_event_consumer_checkpoint
```

## Forbidden Write Proof

The dedicated transaction path does not call action candidate/fact/event/outbox generation.

Planned and tested zero-write scope:

```text
stock_action_fact=0
index_action_fact=0
board_action_fact=0
common_action_event=0
N5 common_event_outbox=0
ActionExecuted=0
ActionBlocked=0
ActionEligible=0
ActionSkipped=0
N4 outbox status update=0
N6/user refs=0
delivery/push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
worker_started=false
```

## Validation

```text
PYTHONPATH=src python3 -m unittest tests/test_action_dry_run.py tests/test_action_execute.py
PASS: 70 tests

python3 -m compileall src/ashare_v3/action scripts tests
PASS
```

```text
python3 -m json.tool docs/N5_WORKER_SCOPED_CONSUMPTION_SMOKE_RUNNER_ALIGNMENT_REPORT.json
PASS

git diff --check
PASS
```

## Decision

`ALIGNMENT_PASS`

It is allowed to return to runtime_control for `N5_WORKER_SCOPED_CONSUMPTION_SMOKE_CONTRACT_GATE`.
