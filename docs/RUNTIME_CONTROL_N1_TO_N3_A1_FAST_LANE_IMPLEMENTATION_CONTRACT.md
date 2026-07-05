# N1 to N3-A1 Fast Lane Implementation Contract

Gate: `RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_IMPLEMENTATION_CONTRACT_GATE`

Layer role: `runtime_control`

Result: `CONTRACT_PASS`

Generated at: `2026-06-09`

Source artifacts:
- `docs/RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_GOVERNANCE_CONTRACT.json` = `CONTRACT_PASS`
- `docs/RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_IMPLEMENTATION_PLAN.json` = `PLAN_PASS`

## Contract Summary

This contract scopes the future implementation of the N1 -> N3-A1 Fast Lane. Fast Lane is only a bundle wrapper over existing same-layer guarded runners. It must not bypass child runner confirmation guards, must not execute across `layer_role`, and must not weaken P0, rollback, downstream-ref, or side-effect guards.

`runtime_control` remains a control plane. It can generate and review artifacts, but it cannot execute N1/N2/N3 commands, write database state, consume outbox, execute rollback SQL, or start workers.

## Allowed Implementation Scope

Future implementation may create or modify only the scoped files below:

```text
scripts/run_n1_fastlane_bundle_once.py
scripts/run_n2_fastlane_bundle_once.py
scripts/run_n3_a1_fastlane_bundle_once.py
src/ashare_v3/runtime/fastlane_contract.py
src/ashare_v3/runtime/fastlane_validation.py
tests/test_fastlane_contract.py
tests/test_fastlane_validation.py
tests/test_n1_fastlane_bundle.py
tests/test_n2_fastlane_bundle.py
tests/test_n3_a1_fastlane_bundle.py
```

Allowed code scope:
- Fast Lane bundle contract structures.
- Pure validation helpers.
- Same-layer wrapper CLIs.
- Bundle report assembly preserving original report paths.
- Unit tests for boundary, validation, and wrapper behavior.
- Operator documentation for the Fast Lane implementation.

Forbidden code scope:
- Changing N1/N2/N3 business runner semantics.
- Implementing N3-B/C realtime pull.
- Implementing N4/N5/N6 execute or readiness behavior.
- Starting workers.
- Consuming or updating outbox/inbox/checkpoint.
- Executing rollback SQL.
- Implementing proposal/order/trade, sim, position, PnL, or real trade.
- Reading or touching old-system paths, old `monitor.db`, old LaunchAgents, or old services.

## Wrapper Boundary

Common wrapper rules:
- Wrappers only orchestrate same-layer existing guarded runners.
- Every execute child command must include `--execute --user-confirmed`.
- Dry-run and preflight child steps may omit `--execute`.
- A failed sub-step must stop the bundle immediately.
- Wrappers must not swallow or replace original report paths.
- Bundle reports must include `sub_report_paths`.
- Bundle reports must include `side_effect_flags`.
- Wrappers must not execute commands for any other `layer_role`.
- Wrappers must not execute rollback SQL.
- Wrappers must not consume or update outbox, inbox, or checkpoint tables.
- Wrappers must not start worker processes.

N1 bundle:
- `layer_role=N1_ingestion`
- Allows trade calendar check or scoped patch when pre-authorized, official daily ingestion, scoped identity repair, no-trade manifest validation, condition source activation, and N1 post-review summary.
- Forbids N2 condition execute, N3 subscription/preload, trigger/action/user commands, and Parquet archive unless separately authorized.

N2 bundle:
- `layer_role=N2_condition`
- Allows policy hash proof, dry-run/preflight, condition execute/overwrite only through existing child runner contract, and N2 post-review summary.
- Forbids N3 subscription, market data pull, and N4/N5/N6 commands.

N3-A1 bundle:
- `layer_role=N3_market_data`
- Allows market_data_subscription control-row registration, A1 previous-day minute preload, and N3-A1 post-review summary.
- Forbids B1 realtime snapshot, C1 today minute, B2 realtime projection, action-confirmation metric, N4/N5/N6 commands, worker, and outbox consumption.

## Validation Helper Contract

Required helpers:

```text
assert_no_cross_layer_execute
assert_execute_command_confirmed
assert_p0_zero
assert_rollback_static_safe
assert_expected_actual_rows_match
assert_no_unexpected_event_delta
assert_downstream_refs_zero
assert_no_old_system_touch
assert_forbidden_scope_false
```

Helper responsibilities:
- `assert_no_cross_layer_execute`: block execute steps whose child `layer_role` differs from the wrapper layer.
- `assert_execute_command_confirmed`: block execute child commands missing `--execute` or `--user-confirmed`.
- `assert_p0_zero`: block when `P0 > 0`.
- `assert_rollback_static_safe`: block when rollback SQL is missing, lacks a hard-fail before destructive statements, or touches unexpected scope.
- `assert_expected_actual_rows_match`: block when any expected row count differs from actual rows.
- `assert_no_unexpected_event_delta`: block unexpected outbox/inbox/checkpoint delta.
- `assert_downstream_refs_zero`: block when N4/N5/N6 refs are nonzero for gates requiring zero downstream refs.
- `assert_no_old_system_touch`: block old-system path, old database, old LaunchAgent, or old service touch.
- `assert_forbidden_scope_false`: block if any forbidden side-effect flag is true.

## Artifact Schema Contract

Base directory:

```text
docs/fastlane/<for_trade_date>/
```

Required artifacts:

```text
01_runtime_readiness.md/json
02_n1_bundle_execute_report.md/json
03_n2_bundle_execute_report.md/json
04_n3_a1_bundle_execute_report.md/json
05_closeout_registration.md/json
```

All bundle reports must include:
- `bundle_run_id`
- `layer_role`
- `status`
- `sub_steps`
- `sub_report_paths`
- `quality_summary`
- `rollback_paths`
- `side_effect_flags`
- `blockers`
- `next_gate`

The closeout registration must include:
- registered run ids
- bundle artifact paths
- rollback registry
- downstream ref proof
- forbidden scope flags
- remaining blockers
- next recommended gate

## Required Tests

Future implementation must add tests proving:
- runtime_control readiness cannot execute N1/N2/N3 commands.
- N1 bundle rejects N2/N3 child commands.
- N2 bundle rejects N3 child commands and market data pull commands.
- N3-A1 bundle rejects B1/C1/B2/N4/N5/N6 child commands.
- Missing `--execute` or `--user-confirmed` blocks execute child commands.
- `P0 > 0` blocks bundle continuation.
- Unsafe rollback SQL blocks bundle continuation.
- Downstream refs nonzero blocks bundle continuation.
- Unexpected outbox/inbox/checkpoint delta blocks bundle continuation.
- Sub-step failure stops the bundle immediately.
- Original child report paths are preserved.
- Bundle artifact JSON schema validation passes.

## Preflight Readiness

The paired preflight artifact is:

```text
docs/RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_IMPLEMENTATION_PREFLIGHT.json
```

Preflight expected result: `PREFLIGHT_PASS`

Ready for implementation gate: `true`

Blockers: none

## Forbidden Scope Proof

This contract gate did not:
- modify business code
- write database rows
- execute N1/N2/N3 commands
- execute rollback SQL
- consume or update outbox/inbox/checkpoint
- start workers
- enter N3-B/C, N4, N5, or N6
- pull realtime market data
- touch delivery, push, voice, or mobile
- touch sim, position, PnL, or real trade
- touch proposal, order, or trade
- touch the old system

## Validation

JSON parse=PASS

contract/preflight consistency=PASS

forbidden scope proof=PASS

git diff --check=PASS

## Next Gate

```text
RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_IMPLEMENTATION_GATE
```
