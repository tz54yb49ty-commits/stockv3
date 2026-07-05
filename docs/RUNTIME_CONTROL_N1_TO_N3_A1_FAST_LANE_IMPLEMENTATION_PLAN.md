# N1 to N3-A1 Fast Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement N1 -> N3-A1 Fast Lane as same-layer guarded-runner bundle wrappers, shared artifact schema, and validation helpers without weakening existing layer boundaries or execute guards.

**Architecture:** Fast Lane is a thin orchestration layer around existing guarded runners. Runtime-control gates create readiness and closeout artifacts only; actual N1/N2/N3 execution remains in the matching `layer_role`. Shared contract and validation modules define bundle reports, required artifact fields, and hard BLOCK checks.

**Tech Stack:** Python standard library, existing project scripts under `scripts/`, runtime helper modules under `src/ashare_v3/runtime/`, JSON/Markdown artifacts under `docs/fastlane/<for_trade_date>/`, unittest.

---

Gate: `RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_IMPLEMENTATION_PLAN_GATE`

Result: `PLAN_PASS`

Layer role: `runtime_control`

This gate only creates implementation plan artifacts. It does not modify business code, write the database, execute N1/N2/N3 commands, execute rollback SQL, consume or update outbox/inbox/checkpoint, start workers, enter N3-B/N3-C/N4/N5/N6, pull realtime market data, touch delivery/push/voice/mobile, touch sim/position/PnL/real trade, generate proposal/order/trade, or touch the old system.

## 1. Implementation Objective

Future Fast Lane implementation must:

- Implement bundle wrappers only around same-layer guarded runners.
- Preserve each child runner's `--execute --user-confirmed` guard.
- Never execute across `layer_role`.
- Never lower P0, rollback, downstream refs, event delta, or side-effect checks.
- Stop immediately on sub-step failure.
- Preserve original child report paths in bundle reports.

This plan does not implement code. It defines the future implementation contract, files, tasks, test plan, and rollout sequence.

## 2. Proposed Files

Future scripts:

```text
scripts/run_n1_fastlane_bundle_once.py
scripts/run_n2_fastlane_bundle_once.py
scripts/run_n3_a1_fastlane_bundle_once.py
```

Future runtime modules:

```text
src/ashare_v3/runtime/fastlane_contract.py
src/ashare_v3/runtime/fastlane_validation.py
```

Future tests:

```text
tests/test_fastlane_contract.py
tests/test_fastlane_validation.py
tests/test_n1_fastlane_bundle.py
tests/test_n2_fastlane_bundle.py
tests/test_n3_a1_fastlane_bundle.py
```

Responsibilities:

- `fastlane_contract.py`: typed step/report models, artifact schemas, side-effect flags, JSON serialization.
- `fastlane_validation.py`: hard guard helpers for layer boundaries, execute confirmation, P0, rollback, row counts, event deltas, downstream refs, old-system touch, and forbidden-scope flags.
- `run_n1_fastlane_bundle_once.py`: N1-only bundle wrapper.
- `run_n2_fastlane_bundle_once.py`: N2-only bundle wrapper.
- `run_n3_a1_fastlane_bundle_once.py`: N3-A1-only bundle wrapper.

## 3. Artifact Schema

Base directory:

```text
docs/fastlane/<for_trade_date>/
```

Files:

```text
01_runtime_readiness.md
01_runtime_readiness.json
02_n1_bundle_execute_report.md
02_n1_bundle_execute_report.json
03_n2_bundle_execute_report.md
03_n2_bundle_execute_report.json
04_n3_a1_bundle_execute_report.md
04_n3_a1_bundle_execute_report.json
05_closeout_registration.md
05_closeout_registration.json
```

Common JSON fields:

```text
gate
result
layer_role
for_trade_date
source_trade_date
prev_trade_date
run_ids
source_run_ids
expected_rows
actual_rows
p0_p1_p2
quality_summary
rollback_paths
sub_report_paths
outbox_inbox_checkpoint_delta
downstream_refs
side_effect_flags
forbidden_scope
blockers
validation
next_gate
```

Layer-specific required fields:

| artifact | layer_role | additional fields |
|---|---|---|
| `01_runtime_readiness.json` | `runtime_control` | `trade_calendar_status`, `routine_day_eligible`, `planned_bundle_ids`, `planned_handoff_commands`, `existing_run_conflicts`, `freshness_check`, `rollback_inventory`, `downstream_ref_baseline` |
| `02_n1_bundle_execute_report.json` | `N1_ingestion` | `calendar_step`, `official_daily_step`, `identity_repair_step`, `no_trade_manifest_step`, `condition_source_activation_step`, `source_versions`, `row_count_checks`, `post_review_summary` |
| `03_n2_bundle_execute_report.json` | `N2_condition` | `policy_hash_proof`, `dry_run_summary`, `preflight_summary`, `execute_summary`, `condition_run_id`, `condition_rows`, `display_rows`, `minute_target_scope_rows`, `post_review_summary` |
| `04_n3_a1_bundle_execute_report.json` | `N3_market_data` | `subscription_control_rows`, `pull_plan_rows`, `previous_day_minute_preload_rows`, `preload_status_rows`, `source_n2_run_id`, `dedup_proof`, `post_review_summary` |
| `05_closeout_registration.json` | `runtime_control` | `readiness_artifact`, `n1_bundle_artifact`, `n2_bundle_artifact`, `n3_a1_bundle_artifact`, `lineage_summary`, `rollback_registry`, `closeout_decision` |

## 4. Runner Wrapper Design

Wrappers must:

- Call only existing guarded runners from the same layer.
- Require `--execute --user-confirmed` for every execute child command.
- Allow dry-run/preflight child steps without execute flags.
- Stop immediately on any sub-step failure.
- Preserve original child report paths.
- Emit bundle report with `sub_report_paths`.
- Record `side_effect_flags` and `forbidden_scope`.
- Reject cross-layer commands before execution.
- Never execute rollback.
- Never consume outbox or start workers.

Step model:

```text
step_id
layer_role
mode = dry_run | preflight | execute | post_review
command_argv
requires_execute_confirmation
expected_report_paths
allowed_write_scope
forbidden_scope
on_failure = stop bundle and emit BLOCKED report
```

## 5. Validation Helper Design

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

Helper behavior:

- `assert_no_cross_layer_execute`: blocks execute steps whose `layer_role` differs from the wrapper layer.
- `assert_execute_command_confirmed`: blocks execute child commands missing `--execute` or `--user-confirmed`.
- `assert_p0_zero`: blocks when P0 count is greater than zero or any P0 item failed.
- `assert_rollback_static_safe`: blocks missing rollback SQL, missing hard-fail guard, forbidden destructive statements, or out-of-scope table mutation.
- `assert_expected_actual_rows_match`: blocks expected/actual row mismatches unless an explicit contract permits variance.
- `assert_no_unexpected_event_delta`: blocks unexpected outbox/inbox/checkpoint deltas.
- `assert_downstream_refs_zero`: blocks nonzero N4/N5/N6 refs.
- `assert_no_old_system_touch`: blocks old system paths, old `monitor.db`, old LaunchAgents, or old service ports.
- `assert_forbidden_scope_false`: blocks any true forbidden side-effect flag.

## 6. Implementation Tasks

### Task 1: Fast Lane Contract Model

**Files:**

- Create: `src/ashare_v3/runtime/fastlane_contract.py`
- Create: `tests/test_fastlane_contract.py`

- [ ] **Step 1: Define model fields**

Create models for `FastLaneStep`, `FastLaneReport`, `FastLaneArtifactSchema`, `FastLaneSideEffectFlags`, and `FastLaneValidationResult`. Include the common artifact fields listed in this plan.

- [ ] **Step 2: Add JSON serializer**

Add a serializer that emits stable JSON dictionaries with `gate`, `result`, `layer_role`, `for_trade_date`, `run_ids`, `sub_report_paths`, `forbidden_scope`, and `validation`.

- [ ] **Step 3: Add schema tests**

In `tests/test_fastlane_contract.py`, assert all five artifact schemas include the common fields and their layer-specific fields.

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests/test_fastlane_contract.py
```

Expected: all tests pass.

### Task 2: Fast Lane Validation Helpers

**Files:**

- Create: `src/ashare_v3/runtime/fastlane_validation.py`
- Create: `tests/test_fastlane_validation.py`

- [ ] **Step 1: Implement helper functions**

Implement the nine `assert_*` helpers listed above. Return structured validation errors or raise a typed project exception already used by nearby runtime code.

- [ ] **Step 2: Cover BLOCK cases**

Add tests for cross-layer execute, missing confirmation flags, P0 > 0, unsafe rollback SQL, row mismatch, unexpected event delta, downstream refs, old-system touch, and forbidden-scope true flags.

- [ ] **Step 3: Run tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests/test_fastlane_validation.py
```

Expected: all tests pass.

### Task 3: N1 Bundle Wrapper

**Files:**

- Create: `scripts/run_n1_fastlane_bundle_once.py`
- Create: `tests/test_n1_fastlane_bundle.py`

- [ ] **Step 1: Parse inputs**

Parse `--for-trade-date`, `--source-trade-date`, `--artifact-dir`, dry-run/preflight/execute mode, `--execute`, and `--user-confirmed`.

- [ ] **Step 2: Compose N1-only steps**

Compose calendar, official daily, optional scoped identity repair, no-trade manifest, condition source activation, and post-review child steps. Reject N2/N3/N4/N5/N6 child commands.

- [ ] **Step 3: Apply validation**

Call `assert_no_cross_layer_execute`, `assert_execute_command_confirmed`, `assert_p0_zero`, `assert_rollback_static_safe`, `assert_no_unexpected_event_delta`, `assert_downstream_refs_zero`, and `assert_forbidden_scope_false`.

- [ ] **Step 4: Add tests**

Assert N2/N3 commands are rejected, missing execute confirmation blocks, child failure stops the bundle, and `sub_report_paths` preserves original reports.

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=src:scripts python3 -m unittest tests/test_n1_fastlane_bundle.py
```

Expected: all tests pass.

### Task 4: N2 Bundle Wrapper

**Files:**

- Create: `scripts/run_n2_fastlane_bundle_once.py`
- Create: `tests/test_n2_fastlane_bundle.py`

- [ ] **Step 1: Parse inputs**

Parse source N1 artifact paths, `--for-trade-date`, `--source-trade-date`, `--artifact-dir`, mode, `--execute`, and `--user-confirmed`.

- [ ] **Step 2: Compose N2-only steps**

Compose policy hash proof, dry-run/preflight, execute or overwrite if needed, and post-review. Reject N3 commands and any market data pull.

- [ ] **Step 3: Apply validation**

Call the shared helpers for layer boundary, execute confirmation, P0, row counts, rollback safety, event deltas, downstream refs, and forbidden scope.

- [ ] **Step 4: Add tests**

Assert N3 command, market data pull, P0 > 0, row mismatch, and unsafe rollback all block.

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=src:scripts python3 -m unittest tests/test_n2_fastlane_bundle.py
```

Expected: all tests pass.

### Task 5: N3-A1 Bundle Wrapper

**Files:**

- Create: `scripts/run_n3_a1_fastlane_bundle_once.py`
- Create: `tests/test_n3_a1_fastlane_bundle.py`

- [ ] **Step 1: Parse inputs**

Parse source N2 artifact paths, `--for-trade-date`, `--source-trade-date`, `--previous-day-minute-date`, `--artifact-dir`, mode, `--execute`, and `--user-confirmed`.

- [ ] **Step 2: Compose N3-A1-only steps**

Compose market-data subscription control rows and previous-day minute preload only. Reject B1 realtime snapshot, C1 today minute, B2 projection, action-confirmation metric, N4, N5, and N6.

- [ ] **Step 3: Apply validation**

Call shared helpers for confirmation flags, P0, row counts, rollback safety, event deltas, downstream refs, old-system touch, and forbidden scope.

- [ ] **Step 4: Add tests**

Assert forbidden N3-B/C/N4/N5/N6 commands, downstream refs, unexpected event deltas, and missing confirmation all block.

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=src:scripts python3 -m unittest tests/test_n3_a1_fastlane_bundle.py
```

Expected: all tests pass.

### Task 6: Integration Artifact Checks

**Files:**

- Modify: `tests/test_fastlane_contract.py`
- Modify: `tests/test_fastlane_validation.py`

- [ ] **Step 1: Add artifact name checks**

Assert the five `docs/fastlane/<for_trade_date>/` JSON/MD artifact pairs are generated with the expected names.

- [ ] **Step 2: Add report path preservation checks**

Assert `sub_report_paths` includes every original child report path.

- [ ] **Step 3: Add side-effect flag checks**

Assert all forbidden-scope flags exist and default to false.

- [ ] **Step 4: Run integration tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests/test_fastlane_contract.py tests/test_fastlane_validation.py
```

Expected: all tests pass.

## 7. Test Plan

Minimum coverage:

- Runtime-control readiness cannot execute N1/N2/N3.
- N1 bundle rejects N2/N3 commands.
- N2 bundle rejects N3 commands and market data pull.
- N3-A1 bundle rejects B1/C1/B2/N4/N5/N6.
- Missing `--execute --user-confirmed` blocks execute child commands.
- `P0 > 0` blocks.
- Unsafe rollback blocks.
- Downstream refs nonzero blocks.
- Unexpected outbox/inbox/checkpoint delta blocks.
- Sub-step failure stops bundle.
- Original report paths are preserved.
- JSON schema validation covers all five artifacts.

## 8. Rollout Plan

```text
Phase 0: contract artifact only, completed
Phase 1: schema/helper implementation
Phase 2: runner wrappers dry-run mode only
Phase 3: layer-specific final gate review
Phase 4: first routine-day pilot with expanded audit
Phase 5: closeout and daily use policy
```

## 9. Non-Goals

- N3-B/C realtime pull.
- N4/N5/N6.
- Worker implementation or start.
- Outbox consumption.
- Rollback execute.
- Real trade.
- Sim.
- Position.
- Proposal.
- Order.
- Trade.
- Old system touch.

## 10. Forbidden Scope Proof

```text
business_code_modified=false
database_written=false
n1_n2_n3_execute_performed=false
rollback_sql_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
worker_started=false
n3_b_or_n3_c_entered=false
n4_n5_n6_entered=false
realtime_market_data_pulled=false
delivery_push_voice_mobile_touched=false
sim_position_pnl_real_trade_touched=false
proposal_order_trade_touched=false
old_system_touched=false
```

## 11. Validation

```text
JSON parse=PASS
plan consistency=PASS
forbidden scope proof=PASS
git diff --check=PASS
```

## Next Gate Recommendation

```text
RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_IMPLEMENTATION_CONTRACT_GATE
```
