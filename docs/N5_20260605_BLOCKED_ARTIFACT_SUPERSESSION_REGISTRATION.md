# N5 20260605 Blocked Artifact Supersession Registration

- result: `SUPERSESSION_PASS`
- gate: `N5_20260605_BLOCKED_ARTIFACT_SUPERSESSION_REGISTRATION_GATE`
- layer_role: `runtime_control`
- generated_at: `2026-06-08T21:46:33+08:00`
- finding closed: `N1N5-P1-003`

## Superseded Artifacts

The following artifacts are preserved as historical evidence, but no longer represent the current N5 readiness state:

- [N5_20260605_ACTION_READINESS_DRY_RUN_GATE_REPORT.md](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_20260605_ACTION_READINESS_DRY_RUN_GATE_REPORT.md)
- [N5_20260605_action_readiness_dry_run_gate_report.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_20260605_action_readiness_dry_run_gate_report.json)

Historical blocked state:

```text
result = DRY_RUN_BLOCKED
TriggerMatched pending = 1537
metric_join_coverage = 0/1537
FULL entered TriggerMatched = 29
```

## Successor Chain

Current state must reference the corrected successor chain:

```text
N4 corrected execute report = docs/N4_20260605_V4_CORRECTED_EXECUTE_REPORT.json
N5 execute contract = docs/N5_ACTION_PIPELINE_EXECUTE_CONTRACT.json
N5 execute preflight = docs/N5_ACTION_PIPELINE_EXECUTE_PREFLIGHT.json
N5 execute report = docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json
source_trigger_run_id = trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
action_run_id = action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
successor TriggerMatched pending = 605
```

## Fresh Readonly DB Proof

- DB time: `2026-06-08 21:46:33.484505+08`
- N4 outbox `TriggerMatched:pending=605`
- `common_action_run` refs = `1`
- `common_action_event` refs = `605`
- N5 outbox pending = `605`

## Decision

The old `1537`-row blocked dry-run remains audit history. It must not be counted as current readiness in the next N1-N5 cross-layer audit.

## Boundary

This gate did not modify code, write the database, execute a runner, consume/update outbox, start workers, run rollback, enter N6 implementation, generate proposal/order/trade, update position/PnL, or submit real trade.

## Remaining Work

This closes the control-plane supersession issue for `N1N5-P1-003`. It does not resolve the current N5 execute report baseline contradiction. Next required gate:

```text
N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_GATE
```
