# N2-Display-1 Schema Readiness

layer_role = N2_condition
status = schema_plan_generated

## Scope

本轮只生成 N2 condition_display_basis schema 草案，不执行 SQL、不访问数据库、不修改 Python 业务逻辑、不进入 N3/N4/N5。

新增文件：

```text
sql/014_condition_display_basis_schema.sql
sql/014_condition_display_basis_rollback.sql
sql/014b_condition_display_quality_check.sql
docs/N2_DISPLAY_1_SCHEMA_READINESS.md
```

## Migration Summary

`014_condition_display_basis_schema.sql` 只新增三张 N2 物理分表：

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
```

表粒度：

```text
one run_id + one identity_key = one display basis row
```

多条 `condition_pool` / `minute_target_scope` 来源通过 JSON 数组保留追溯：

```text
source_condition_basis_ids_json
source_condition_pool_ids_json
source_minute_target_scope_ids_json
source_row_count_json
```

## Schema Diff Summary

主 migration 只包含：

```text
CREATE TABLE IF NOT EXISTS stock_condition_display_basis
CREATE TABLE IF NOT EXISTS index_condition_display_basis
CREATE TABLE IF NOT EXISTS board_condition_display_basis
CREATE INDEX IF NOT EXISTS ...
```

主 migration 不包含：

```text
ALTER TABLE existing condition tables
DROP / RENAME
INSERT / UPDATE / DELETE
N3/N4/N5 tables
runtime/event/outbox tables
```

`014b_condition_display_quality_check.sql` 单独处理：

```text
common_condition_quality_item.layer_scope
```

该文件会重建 existing CHECK 以允许：

```text
condition_display_basis
```

因此 014b 不属于 strictly additive-only，必须单独 review 和确认。

## Table Field Groups

Lineage:

```text
run_id
for_trade_date
source_trade_date
prev_trade_date
source_version
created_at
updated_at
```

Identity:

```text
stock_identity_key / index_identity_key / board_identity_key
code / exchange / name
board_code / board_name / board_type
```

Display:

```text
display_code
display_name
display_title
display_summary
selected_directions
selected_condition_keys
selected_signal_types
selected_lanes
selected_monitor_types
condition_summary_json
target_price_summary_json
reference_period_summary_json
period_grade_summary_json
period_transition_summary_json
```

N2 static structure:

```text
period_grade_y/q/m/w/d
period_transition_y/q/m/w/d
prev_up_str
prev_dn_str
buy_target_price
sell_target_price
up_sell_reference_period
down_buy_reference_period
clear_sell_ref_period
period_trigger_baseline_json
```

Policy and audit:

```text
display_policy_name
display_policy_hash
condition_pool_policy_name
condition_pool_policy_hash
scope_policy_name
scope_policy_hash
display_scope_reason
selected_reason
excluded_reason
display_status
quality_status
quality_reason
missing_fields_json
raw_json
```

Trace:

```text
primary_source_condition_basis_id
primary_source_condition_pool_id
primary_source_minute_target_scope_id
source_condition_basis_ids_json
source_condition_pool_ids_json
source_minute_target_scope_ids_json
```

## Readiness Checklist

Before executing 014:

```text
[ ] User explicitly confirms 014 execution.
[ ] PostgreSQL schema has common_condition_run.
[ ] PostgreSQL schema has stock/index/board identity tables.
[ ] PostgreSQL schema has stock/index/board condition_basis.
[ ] PostgreSQL schema has stock/index/board condition_pool.
[ ] PostgreSQL schema has stock/index/board minute_target_scope.
[ ] No table named stock_condition_display_basis already exists with incompatible columns.
[ ] No table named index_condition_display_basis already exists with incompatible columns.
[ ] No table named board_condition_display_basis already exists with incompatible columns.
[ ] 014b quality CHECK decision is separate from 014.
```

After executing 014:

```text
[ ] Three display tables exist.
[ ] Three display table primary keys exist.
[ ] Unique keys on run_id + identity_key exist.
[ ] run_id foreign keys point to common_condition_run.
[ ] identity foreign keys point to physical identity tables.
[ ] primary source foreign keys point to same-domain N2 tables.
[ ] N3/N4/N5 tables unchanged.
[ ] common_event_outbox unchanged.
```

Before any display basis overwrite:

```text
[ ] display_basis dry-run exists.
[ ] full N2 dry-run includes basis / pool / scope / display.
[ ] display row counts are explainable by domain.
[ ] source ids JSON arrays are valid JSON arrays.
[ ] clear_sell_ref_period equals up_sell_reference_period.
[ ] selected_signal_types are inside the N2 six-type whitelist.
[ ] No N3/N4/N5 dependency reads display_basis.
```

## Risks

1. `condition_display_basis` is one object row, while `condition_pool` and `minute_target_scope` are condition-source detail rows. The display generator must aggregate carefully and preserve all source ids.
2. `014b_condition_display_quality_check.sql` modifies an existing CHECK constraint. It is intentionally separated from the additive table migration.
3. Official display rows must not be backfilled into the old active condition run. A formal display overwrite must create a new N2 run_id.
4. Display basis must not become an input to N3/N4/N5. The trading chain remains `minute_target_scope -> market_data_subscription`.
5. The schema allows nullable display fields for first migration safety; dry-run and overwrite quality gates must decide which fields are required.

## Rollback

Schema rollback draft:

```text
sql/014_condition_display_basis_rollback.sql
```

It drops only:

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
```

If 014b is executed later, rollback must separately restore the previous `common_condition_quality_item.layer_scope` CHECK.

## Decision

```text
READY_TO_EXECUTE_MIGRATION
```

Execution is still blocked until explicit user confirmation. This document does not authorize migration execution.
