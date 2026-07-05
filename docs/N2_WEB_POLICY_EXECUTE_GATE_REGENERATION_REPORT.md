# N2 Web Policy Execute Gate Regeneration Report

```text
result=REGENERATION_PASS
layer_role=N2_condition
overwrite_executed=false
condition_business_rows_written=false
registry_command_executed=false
rollback_sql_executed=false
N3/N4/N5/N6 entered=false
market_data_pulled=false
worker_started=false
outbox/inbox/checkpoint touched=false
old_system_touched=false
```

## Regenerated Gate Proof

Latest gate 已刷新：

```text
gate_json_path=docs/N2_web_policy_execute_gate_draft.json
gate_markdown_path=docs/N2_WEB_POLICY_EXECUTE_GATE_DRAFT.md
gate_result=PASS
source_trade_date=20260528
for_trade_date=20260529
current_active_run_id=condition_layer_20260528_source_20260528_v5
proposed_run_id=condition_layer_20260528_source_20260528_v6
overwrite_semantics=lineage_supersede_only
policy_path=configs/n2_policy/default_policy_draft.json
policy_version=v4
policy_hash=ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576
expected_rows_present=true
expected_rows == expected_row_counts=true
execute_authorized=false
writes_performed=false
database_written=false
n3_rebuild_required=true
n3_lineage_auto_switch=false
```

Expected rows：

```text
condition_basis: stock=5506 index=83 board=428
condition_pool: stock=4271 index=169 board=875
minute_target_scope: stock=4251 index=169 board=875
condition_display_basis: stock=2011 index=83 board=428
monitor_target: stock=5506 index=83 board=428
quality_item=103
```

## Rollback Proof

Rollback SQL 已刷新：

```text
rollback_sql_path=sql/N2_condition_layer_20260528_v6_web_policy_rollback.sql
rollback_run_id=condition_layer_20260528_source_20260528_v6
restore_run_id=condition_layer_20260528_source_20260528_v5
hard_fail_before_first_DELETE_UPDATE=true
event_infra_guard=true
downstream_N3_N4_N5_N6_guard=true
no_CASCADE_DROP_TRUNCATE=true
```

Rollback 只清 proposed v6 的 N2 rows，并恢复 v5 为 `passed_active`；不清 v5/v4/v3/v2/v1 rows，不触碰 N1 facts、N3/N4/N5/N6 facts、outbox/inbox/checkpoint。

## Confirmation Proof

```text
latest_gate_exists=true
gate_result=PASS
gate_policy_hash=current_default_policy_hash
gate_source_trade_date=selected_source_trade_date
confirmation_model_enabled=true
manual input must equal proposed_run_id or policy_hash
confirmation_result=WAIT_MANUAL_CONFIRM
execute_authorized=false
writes_performed=false
database_written=false
```

## Forbidden Scope Proof

```text
common_event_outbox forbidden
common_event_inbox forbidden
common_event_consumer_checkpoint forbidden
N3/N4/N5/N6 forbidden
market_data_pull forbidden
worker forbidden
old_system forbidden
```

## Validation

验证状态见同名 JSON；最终验证完成后已回填。

## Next Gate

```text
allow_reenter_N2_WEB_POLICY_EXECUTE_FINAL_GATE_REVIEW=true
```
