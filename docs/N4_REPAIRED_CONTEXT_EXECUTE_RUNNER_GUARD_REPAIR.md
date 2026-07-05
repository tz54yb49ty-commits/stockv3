# N4 Repaired Context Execute Runner Guard Repair

## Result

REPAIR_PASS

## Scope

- layer_role: N4_trigger
- gate: N4_REPAIRED_CONTEXT_EXECUTE_RUNNER_GUARD_REPAIR_GATE
- execute_run_id: trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
- database_written: false
- outbox_consumed: false
- n5_n6_entered: false
- worker_started: false

## Root Cause

`scripts/run_n4_20260605_v4_corrected_execute_once.py` hard-coded `dry_run.blocked_count == 297`.
That made the runner reject the repaired-context approved artifacts where:

- dry-run blocked_count = 291
- contract blocked_candidates.total = 291
- preflight blocked_candidates.total = 291

The guard was tied to the old tainted artifact instead of the active execute contract.

## Guard Repair

The runner now uses contract-driven artifact consistency checks:

- `dry_run.blocked_count == contract.blocked_candidates.total`
- `preflight.blocked_candidates.total == contract.blocked_candidates.total`
- `dry_run.candidate_plans_before_strict_guard == contract.corrected_dry_run_baseline.candidate_plans_before_strict_guard`
- `dry_run.persisted_plans_after_strict_guard == contract.corrected_dry_run_baseline.persisted_plans_after_strict_guard`
- `contract.corrected_dry_run_baseline.persisted_plans_after_strict_guard == contract.planned_writes.TriggerMatched`
- `contract.planned_writes.common_trigger_state/common_trigger_match/common_event_outbox/TriggerMatched` must be equal
- `preflight.planned_writes` must match `contract.planned_writes`
- `TriggerPendingMarketData=0`
- `TriggerStateChanged=0`

No numeric blocked-count constant remains in the runner guard.

## Artifact Compatibility Proof

Old corrected artifacts remain accepted when paired with their matching contract/preflight:

- candidate_count = 1537
- compliant_count = 1240
- blocked_count = 297
- planned TriggerMatched/state/match/outbox = 1240

Repaired-context artifacts are accepted when paired with their matching contract/preflight:

- candidate_count = 896
- compliant_count = 605
- blocked_count = 291
- planned TriggerMatched/state/match/outbox = 605

Mismatched blocked_count, preflight blocked_count, candidate count, or planned write counts now block before any DB write.

## Modified Files

- `scripts/run_n4_20260605_v4_corrected_execute_once.py`
- `tests/test_n4_20260605_v4_corrected_execute_runner.py`
- `docs/N4_REPAIRED_CONTEXT_EXECUTE_RUNNER_GUARD_REPAIR.md`
- `docs/N4_REPAIRED_CONTEXT_EXECUTE_RUNNER_GUARD_REPAIR.json`

## Validation

- targeted runner tests: passed (`13` tests)
- old 297 artifact guard test: passed
- new 291 artifact guard test: passed
- compileall: passed
- `scripts/check_n4_contract.py`: passed
- JSON artifact parse: passed
- `git diff --check`: passed

## Forbidden Scope Proof

This gate did not:

- execute N4
- write database rows
- consume or update outbox
- start worker
- enter N5/N6
- trigger delivery, push, voice, mobile, sim, position, or real trade

Read-only DB scoped baseline proof for `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`:

- common_trigger_run / quality / state / match / outbox / inbox / checkpoint = 0 / 0 / 0 / 0 / 0 / 0 / 0
- common_action_run / common_action_event = 0 / 0
- user_projection_run / user_signal_projection / user_signal_card / user_notification_queue = 0 / 0 / 0 / 0

## Next Gate

Allowed to return to runtime_control for:

`N4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_FINAL_GATE_REVIEW`
