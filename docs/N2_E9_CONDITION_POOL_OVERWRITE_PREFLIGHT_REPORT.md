# N2-E9 Condition Pool Overwrite Preflight Report

## Summary

- stage: N2-E9 condition_pool 收口 overwrite preflight
- source_trade_date: `20260522`
- for_trade_date: `20260525`
- prev_trade_date: `20260522`
- old_active_run_id: `condition_layer_20260522_to_20260525_20260523191307_execute`
- overwrite_executed: false
- business_data_written: false
- migration_executed: false
- minute_kline_pulled: false
- downstream_layers_touched: false

N2-E9 只做 overwrite 前只读预演。`--overwrite --user-confirmed` 仅用于验证合同和 preflight 分支，不执行 SQL，不切换 active run。

## Source Reports

```text
docs/N2_E9_basis_dry_run.json
docs/N2_E9_pool_dry_run.json
docs/N2_E9_scope_dry_run.json
docs/N2_E9_readiness_plan.json
docs/N2_E9_overwrite_contract.json
docs/N2_E9_overwrite_preflight.json
docs/N2_E9_active_run_scope_audit.json
docs/N2_E9_schema_gap.json
```

## Schema Status

```text
schema_ready=true
migration_required=false
missing_column_count=0
type_mismatch_count=0
not_null_risk_count=0
constraint_deferred_count=0
```

`005` additive migration 已完成，开发库 schema 已追上 N2-E5 policy 字段。

## Current Active Run Audit

当前 active run 仍是旧口径：

```text
run_id=condition_layer_20260522_to_20260525_20260523191307_execute
status=passed
active_run_count=1
```

只读审计结果：

```text
P0=5
needs_remediation=true
```

旧 active run 越界点：

```text
index_condition_pool:
  rows=273
  objects=80
  out_of_range_rows=247
  missing_fixed_codes=000001

board_condition_pool:
  rows=1575
  objects=428
  out_of_range_rows=1110

stock_condition_pool:
  rows=20246
  objects=5501
  out_of_range_rows=12808

index_minute_target_scope:
  rows=18
  objects=9
  pool_link_violations=18
  scope_source=fixed_index_scope

board_minute_target_scope:
  rows=254
  objects=127
  pool_link_violations=254
  scope_source=industry_board_scope
```

说明：这不是 N2-E9 新 dry-run 的 P0，而是旧 active run 尚未按 N2-E5 口径 overwrite 的审计结果。

## New Dry-Run Result

condition_basis dry-run：

```text
stock_condition_basis=5504
index_condition_basis=80
board_condition_basis=428
P0=0
P1=3
P2=1
```

condition_pool 默认 policy dry-run：

```text
stock_candidate_rows=20246
stock_selected_rows=7384
stock_excluded_rows=12862
stock_selected_objects=2052

index_candidate_rows=273
index_selected_rows=26
index_excluded_rows=247
index_selected_objects=8

board_candidate_rows=1575
board_selected_rows=465
board_excluded_rows=1110
board_selected_objects=127

P0=0
P1=1
P2=1
```

policy 收口依据：

```text
index: fixed 9 universe, selected rows only from matching condition_pool candidates
board: board_code LIKE '881%'
stock: total_mv >= 1,000,000 万元, non-ST/risk, active, official daily proof, financial quality proof
```

minute_target_scope dry-run：

```text
stock_scope_rows=7384
index_scope_rows=26
board_scope_rows=465

stock_scope_source_counts={condition_pool: 7384}
index_scope_source_counts={condition_pool: 26}
board_scope_source_counts={condition_pool: 465}

previous_day_minute_date_mismatch_count=0
P0=0
P1=1
P2=1
```

## Before And After Plan

Existing active run row counts:

```text
stock_condition_basis=5504
index_condition_basis=80
board_condition_basis=428
stock_condition_pool=20246
index_condition_pool=273
board_condition_pool=1575
stock_minute_target_scope=7438
index_minute_target_scope=18
board_minute_target_scope=254
```

Overwrite dry-run expected row counts:

```text
common_condition_run=1
common_condition_quality_item=67
stock_monitor_target=5504
index_monitor_target=80
board_monitor_target=428
stock_condition_basis=5504
index_condition_basis=80
board_condition_basis=428
stock_condition_pool=7384
index_condition_pool=26
board_condition_pool=465
stock_minute_target_scope=7384
index_minute_target_scope=26
board_minute_target_scope=465
```

对比：

```text
stock_condition_pool: 20246 -> 7384
index_condition_pool: 273 -> 26
board_condition_pool: 1575 -> 465
stock_minute_target_scope: 7438 -> 7384
index_minute_target_scope: 18 -> 26
board_minute_target_scope: 254 -> 465
```

旧 active run 切换计划：

```text
previous_active_run_id=condition_layer_20260522_to_20260525_20260523191307_execute
new_execute_run_id=condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute
postcheck passed: old active -> superseded, new run -> passed
postcheck failed: keep old active passed, mark new run failed, rollback new run rows
```

## Execute Contract Dry-Run

```text
overwrite=true
user_confirmed=true
execute_request_allowed=true
execute_ready=false
execute_supported=false
dry_run_only=true
will_execute_sql=false
writes_performed=false
blocked_reasons=[]
not_ready_reasons=[n2_e1_contract_only_execute_not_supported]
```

说明：`execute_request_allowed=true` 只表示合同允许进入下一阶段讨论；N2-E9 仍不执行。

## Execute Preflight Dry-Run

```text
execute_allowed=true
schema_ready=true
active_run_exists=true
blocked_by_active_run=false
overwrite=true
user_confirmation_required=true
user_confirmed=true
will_execute_sql=false
writes_performed=false
dry_run_only=true
blocked_reasons=[]
```

quality summary：

```text
P0=0
P1=5
P2=3
```

P1 仍需要用户在真正 overwrite 阶段再次确认。

## Rollback SQL Preview

rollback strategy:

```text
delete_by_run_id_then_restore_previous_active
```

rollback SQL preview:

```sql
DELETE FROM stock_minute_target_scope WHERE run_id = :execute_run_id;
DELETE FROM board_minute_target_scope WHERE run_id = :execute_run_id;
DELETE FROM index_minute_target_scope WHERE run_id = :execute_run_id;
DELETE FROM board_condition_pool WHERE run_id = :execute_run_id;
DELETE FROM index_condition_pool WHERE run_id = :execute_run_id;
DELETE FROM stock_condition_pool WHERE run_id = :execute_run_id;
DELETE FROM board_condition_basis WHERE run_id = :execute_run_id;
DELETE FROM index_condition_basis WHERE run_id = :execute_run_id;
DELETE FROM stock_condition_basis WHERE run_id = :execute_run_id;
DELETE FROM board_monitor_target WHERE source_version = :execute_run_id;
DELETE FROM index_monitor_target WHERE source_version = :execute_run_id;
DELETE FROM stock_monitor_target WHERE source_version = :execute_run_id;
DELETE FROM common_condition_quality_item WHERE run_id = :execute_run_id;
DELETE FROM common_condition_run WHERE run_id = :execute_run_id;
```

restore previous active:

```sql
UPDATE common_condition_run
SET status = 'passed', updated_at = now()
WHERE run_id = :previous_active_run_id;
```

## Boundary Confirmation

- Only worked inside v3 project.
- Did not touch the old system.
- Did not pull market data or minute K.
- Did not enter N3 / trigger / action / mobile / voice / sim / worker.
- Did not write condition_basis / condition_pool / minute_target_scope business rows.
- Did not execute overwrite.
- Did not execute migration.
