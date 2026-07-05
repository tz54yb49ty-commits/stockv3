# N3-P1 Realtime Projection Metric Schema Readiness

## Summary

```text
stage=N3-P1
layer_role=N3_market_data
result=SCHEMA_READINESS_PASS
business_data_written=false
database_changed=false
migration_executed=false
market_data_pulled=false
pending_market_snapshot_outbox_modified=false
outbox_consumed=false
downstream_layers_touched=false
worker_started=false
old_system_touched=false
```

N3 realtime projection preflight 已通过。本阶段只生成 additive schema 草案、schema rollback 草案和 readiness 结论，不执行 migration。

## Current Metadata Readiness

Runtime metadata 只读检查结果：

```text
stock_realtime_projection_metric exists=false
index_realtime_projection_metric exists=false
board_realtime_projection_metric exists=false
```

现有 `common_market_data_quality_item` 字段足够承载 projection quality：

```text
layer_scope=market_data_run
table_name=stock/index/board_realtime_projection_metric
gate_code=n3_projection_*
details.metric_scope=realtime_projection_metric
```

本轮不建议 ALTER 旧表增加 `layer_scope` 枚举或新增 `metric_scope` 列，因为这会触碰既有 quality 表约束，且不是 N3-P1 最小必要条件。

## Migration Files

新增草案：

```text
sql/015_market_realtime_projection_metric_schema.sql
sql/015_market_realtime_projection_metric_rollback.sql
```

015 schema 只包含：

```text
CREATE TABLE IF NOT EXISTS stock_realtime_projection_metric
CREATE TABLE IF NOT EXISTS index_realtime_projection_metric
CREATE TABLE IF NOT EXISTS board_realtime_projection_metric
CREATE INDEX IF NOT EXISTS ...
```

不包含：

```text
ALTER TABLE stock/index/board_realtime_daily_snapshot
ALTER TABLE common_event_outbox
ALTER TABLE common_market_data_quality_item
INSERT / UPDATE / DELETE business data
DROP / TRUNCATE
trigger/action/user/voice/mobile/sim/position 表
```

## Table Contract

三张表保持 stock/index/board 物理隔离。

主键：

```text
projection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
```

唯一键：

```text
projection_run_id
trade_date
identity_key
projection_window_id
snapshot_time
source_adapter
projection_schema_version
```

其中 `identity_key` 在三张物理表中分别为：

```text
stock_identity_key
index_identity_key
board_identity_key
```

核心索引：

```text
lookup: trade_date + identity_key + projection_window_id + snapshot_time desc
run: projection_run_id + projection_quality_status + projection_status
snapshot: source_snapshot_run_id + snapshot_id
signal: for_trade_date + projection_signal_status + projection_quality_status
```

## Required Fields

Lineage 字段：

```text
projection_run_id
source_snapshot_run_id
source_condition_run_id
snapshot_id
snapshot_event_id
subscription_id
pull_plan_id
for_trade_date
trade_date
identity_key
```

Projection 字段：

```text
projection_schema_version
projection_window_id
projection_window_kind
window_start
window_end
snapshot_time
completion_ratio
elapsed_seconds
window_total_seconds
is_window_closed
session_id
rolling_5m_amount_avg
elapsed_amount
projected_30m_amount
previous_day_same_window_amount
previous_day_same_elapsed_amount
amount_projection_ratio
elapsed_amount_ratio
latest_price
window_open_price
window_high_price
window_low_price
price_change_pct
price_direction_status
projection_status
projection_signal_status
projection_quality_status
trace_status
amount_basis_kind
source_fact_kind
```

Trace 字段：

```text
source_fact_ids
minute_bar_ids_used
previous_day_minute_bar_ids_used
quality_item_ids
source_adapter
calculation_method
calculation_config_hash
raw_json
created_at
updated_at
```

## Enum / Check Constraints

`price_direction_status`：

```text
up
down
flat
unknown
```

`projection_status`：

```text
ready
not_ready
quality_blocked
```

`projection_signal_status`：

```text
up_volume_expanding
down_volume_shrinking
up_volume_flat
down_volume_flat
up_volume_shrinking
down_volume_expanding
flat
unknown
```

`projection_quality_status` / `trace_status`：

```text
passed
pending
warning
failed
blocked
```

`amount_basis_kind`：

```text
previous_day_same_window
previous_day_same_elapsed
snapshot_delta_anchor
minute_bar_elapsed
adapter_projection
not_available
```

`source_fact_kind`：

```text
realtime_daily_snapshot
minute_bar_1m_elapsed
snapshot_delta_anchor
previous_day_minute_bar_1m
adapter_projection
mixed
```

## Event Type Decision

本轮不新增 event type。

N3-P1 只提供 canonical projection fact schema。后续 N3-B2 可以：

```text
1. 写 projection fact；
2. 保持既有 pending MarketSnapshotUpdated outbox payload 不变；
3. 让 N4 通过 MarketSnapshotUpdated.payload_json.snapshot_id 精确读取 projection fact。
```

若未来需要高频独立事件，必须另行审查 `MarketProjectionUpdated`，不得在 015 中隐式加入。

## Forbidden Field Scan

015 schema 未引入以下业务字段族：

```text
trigger
action
user
voice
mobile
sim
position
```

说明：字段名 `projection_*` 只表达 N3 market projection metric，不是 N6 user projection。

## Rollback Plan

Schema rollback 草案：

```text
sql/015_market_realtime_projection_metric_rollback.sql
```

Rollback 特性：

```text
只 drop 三张 projection 表
drop 前检查三张表是否已有 projection 业务行
若存在业务行则 raise exception，防止误删
不触碰 realtime_daily_snapshot
不触碰 common_event_outbox / common_event_inbox / checkpoint
不触碰 N2 condition / N4 / N5 / N6 / old system
```

未来 N3-B2 execute 后的业务数据 rollback 必须按 `projection_run_id` 单独设计，不使用本 schema rollback 直接删表。

## Schema Readiness Checklist

```text
P0 projection physical tables missing in current DB: expected before migration
P0 migration additive-only: passed
P0 no ALTER existing pending outbox payload: passed
P0 no common_event_outbox DML: passed
P0 no common_event_inbox/checkpoint DML: passed
P0 no trigger/action/user/voice/mobile/sim/position tables: passed
P0 stock/index/board physical isolation: passed
P0 unique dedup key present: passed
P0 lineage fields present: passed
P0 trace fields present: passed
P0 no new event type: passed
P1 common_market_data_quality_item layer_scope not expanded: accepted; use market_data_run + details.metric_scope
P2 future MarketProjectionUpdated requires separate review: noted
```

## Decision

```text
SCHEMA_READINESS_PASS
P0/P1/P2=0/1/1
```

总控复核：需要。原因是 015 新增 canonical N3 fact 表，后续 N4 projection matcher 将依赖该表。

允许进入下一步：

```text
N3-P2 market realtime projection metric migration review / execute confirmation point
```

不允许直接进入：

```text
N3-B2 projection execute
N4 outbox consumption
N4 TriggerMatched execute
N5/N6
worker
```
