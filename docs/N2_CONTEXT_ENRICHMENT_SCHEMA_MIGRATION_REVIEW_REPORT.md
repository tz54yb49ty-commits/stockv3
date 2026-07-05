# N2 Context Enrichment Schema Migration Review

- review_result: SCHEMA_REVIEW_PASS
- layer_role: N2_condition
- migration_sql: `sql/033_condition_context_enrichment_materialization_schema.sql`
- rollback_sql: `sql/033_condition_context_enrichment_materialization_schema_rollback.sql`
- execute_performed: false
- database_written: false
- downstream_layers_entered: false
- outbox_consumed: false
- worker_started: false

## Background

`N2_CONTEXT_ENRICHMENT_ROW_LEVEL_MATERIALIZATION_GATE` 已生成 5222 行 row-level payload，但未来 DB execute 被阻断：

```text
blocked_reason = materialization_tables_missing
```

缺少四张 N2-owned 表：

```text
common_condition_context_enrichment_run
stock_condition_context_enrichment
index_condition_context_enrichment
board_condition_context_enrichment
```

## DDL Scope

本次 033 草案只创建上述四张表和索引：

```text
CREATE TABLE IF NOT EXISTS common_condition_context_enrichment_run
CREATE TABLE IF NOT EXISTS stock_condition_context_enrichment
CREATE TABLE IF NOT EXISTS index_condition_context_enrichment
CREATE TABLE IF NOT EXISTS board_condition_context_enrichment
```

不修改现有 `condition_basis / condition_pool / minute_target_scope / condition_display_basis`，不触碰 N3/N4/N5/N6 表，不触碰 event infra。

## Keys

`common_condition_context_enrichment_run`:

```text
PRIMARY KEY(run_id)
```

三张物理分表：

```text
PRIMARY KEY(<domain>_condition_context_enrichment_id)
UNIQUE(materialization_run_id, context_materialization_row_key)
UNIQUE(materialization_run_id, source_minute_target_scope_id)
```

## Indexes

Run 表：

```text
idx_common_condition_context_enrichment_run_source
idx_common_condition_context_enrichment_run_status
idx_common_condition_context_enrichment_run_policy
```

三张物理分表均有：

```text
idx_<domain>_condition_context_enrichment_run
idx_<domain>_condition_context_enrichment_source_run
idx_<domain>_condition_context_enrichment_identity
idx_<domain>_condition_context_enrichment_condition
idx_<domain>_condition_context_enrichment_hash
idx_<domain>_condition_context_enrichment_payload USING GIN(payload_json)
```

## JSONB Fields

三张 row-level 表保留：

```text
period_trigger_baseline_json
trigger_amount_chain_baseline_json
FULL_prerequisite_trace_json
HINT_prerequisite_trace_json
period_baseline_ready_json
payload_json
```

Run 表保留：

```text
policy_json
raw_json
```

## Spec / Policy / Run Fields

Run 表：

```text
run_id
source_condition_run_id
spec_version
policy_hash
policy_json
materialization_status
```

三张 row-level 表：

```text
materialization_run_id
source_condition_run_id
spec_version
policy_hash
context_materialization_row_key
context_enrichment_version
context_enrichment_hash
```

## References

Hard references:

```text
common_condition_context_enrichment_run.source_condition_run_id -> common_condition_run(run_id)
stock_condition_context_enrichment.materialization_run_id -> common_condition_context_enrichment_run(run_id)
index_condition_context_enrichment.materialization_run_id -> common_condition_context_enrichment_run(run_id)
board_condition_context_enrichment.materialization_run_id -> common_condition_context_enrichment_run(run_id)
stock/index/board_condition_context_enrichment.source_condition_run_id -> common_condition_run(run_id)
stock/index/board identity columns -> stock/index/board_identity
source_minute_target_scope_id -> matching domain minute_target_scope table
```

Soft references / trace:

```text
source_scope_table
context_materialization_row_key
payload_json.source metadata
```

N3/N4/N5/N6 不作为 FK 目标；后续消费只应通过明确 materialization run_id 和 payload contract。

## Rollback Migration

Rollback 草案：

```text
sql/033_condition_context_enrichment_materialization_schema_rollback.sql
```

策略：

```text
1. 若四张新表任一存在 rows，则 RAISE EXCEPTION 阻断 schema rollback。
2. 无 rows 时才按依赖顺序 DROP TABLE。
3. 不清理业务 run，不触碰 N2 原有 condition 表，不触碰 outbox/inbox/checkpoint。
```

## Review Result

```text
additive_schema_only = true
if_not_exists = true
business_row_changes = false
downstream_tables_touched = false
event_infra_touched = false
rollback_guarded = true
```

结论：

```text
SCHEMA_REVIEW_PASS
allow_enter_schema_migration_execute_final_gate = true
```

下一步只能进入 `033 schema migration execute final gate`，等待用户确认后执行 DDL；不得直接进入 row-level materialization execute。
