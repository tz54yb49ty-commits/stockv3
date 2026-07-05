# N4 20260617 True Full-Day Lifecycle Replay Preflight

Result: BLOCKED

Blockers:
- P0 lifecycle_state_unique_index_missing: common_trigger_state_lifecycle_key_v1 is not present.
- P0 full_day_lifecycle_dry_run_not_completed_with_current_planner_performance: full-day lifecycle distribution was not proven.

Validated proofs:
- N3 true-minute B2 rows total 491760, labels 09:31-15:00, per identity 240/240, metric_ready 491760.
- N4 context rows total 4326 and common_trigger_run status passed/bound to source_metric_run_id.
- Target execute_run_id scoped N4/N5 refs are zero.
- Focused N4 matcher/execute tests passed.

No N4 replay execute, no N5/N6, no outbox/inbox/checkpoint consumption, no market pull, no worker.
