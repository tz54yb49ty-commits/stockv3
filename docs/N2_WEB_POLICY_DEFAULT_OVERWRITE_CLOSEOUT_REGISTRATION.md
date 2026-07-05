# N2 Web Policy Default Overwrite Closeout Registration

```text
result=CLOSEOUT_PASS
layer_role=runtime_control
gate=RUNTIME_CONTROL_N2_WEB_POLICY_DEFAULT_OVERWRITE_CLOSEOUT_REGISTRATION_GATE
generated_at=2026-06-07
review_mode=closeout_registration_only
```

## Lifecycle Summary

The 8782 N2 Web Policy default overwrite loop is complete.

```text
Dry-run=completed
save_default_policy_draft=completed
execute_gate_generation=completed
runtime_control_final_gate=PASS
N2_condition_manual_overwrite_execute=EXECUTE_PASS
runtime_control_post_review=POST_REVIEW_PASS
active_run_v6_registered=true
```

## Active Lineage Summary

```text
new_active_run=condition_layer_20260528_source_20260528_v6
previous_active_run=condition_layer_20260528_source_20260528_v5
previous_active_status=superseded
active_passed_run_count=1
P0/P1/P2=0/3/3
```

## Policy Continuity Proof

```text
policy_path=configs/n2_policy/default_policy_draft.json
policy_id=n2_default_policy
policy_version=v4
policy_hash=ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576
daily_runner_default_policy_continuity=true
scheduler_registry_explicit_policy_override=false
```

When no explicit `--policy` is passed, the daily N2 runner continues to read `configs/n2_policy/default_policy_draft.json`.

## Row Count Summary

Rows match the regenerated execute gate and post-review proof.

```text
condition_basis: stock=5506 index=83 board=428
condition_pool: stock=4271 index=169 board=875
minute_target_scope: stock=4251 index=169 board=875
condition_display_basis: stock=2011 index=83 board=428
monitor_target: stock=5506 index=83 board=428
quality_item=103
```

## Rollback Registry Summary

```text
rollback_sql_path=sql/N2_condition_layer_20260528_v6_web_policy_rollback.sql
rollback_run_id=condition_layer_20260528_source_20260528_v6
restore_run_id=condition_layer_20260528_source_20260528_v5
hard_fail_before_DELETE_UPDATE=true
guards_outbox_inbox_checkpoint=true
guards_N3_N4_N5_N6_refs=true
no_CASCADE_DROP_TRUNCATE=true
scope_only_v6_N2_rows=true
```

## Forbidden Scope Proof

```text
runtime_control_executed_command=false
rollback_executed=false
N3/N4/N5/N6_entered=false
market_data_pulled=false
worker_started=false
outbox/inbox/checkpoint_consumed_or_updated=false
old_system_touched=false
```

## Validation Summary

```text
JSON parse PASS
execute report proof PASS
post-review proof PASS
rollback static check PASS
daily runner policy audit PASS
git diff --check PASS
```

## Closeout

```text
can_mark_N2_Web_Policy_default_overwrite_closeout_complete=true
recommended_next_gate=N3_MARKET_DATA_SUBSCRIPTION_REBUILD_READINESS_GATE_FOR_condition_layer_20260528_source_20260528_v6
```
