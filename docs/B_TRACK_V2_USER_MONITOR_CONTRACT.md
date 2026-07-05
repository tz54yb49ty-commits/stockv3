# B_TRACK_V2_USER_MONITOR_CONTRACT

Status: `CONTRACT_PASS`

Layer role: `runtime_control`

Date: `2026-06-07`

Scope: B轨 V2 用户监控对象 contract。本文档只定义 schema 草案、权限边界和未来写入路线，不执行 schema migration，不写数据库，不修改 V1 代码。

## 1. Contract Objective

B轨 V2 需要把“我的监控”从全局 display cache 中剥离出来，建立 principal scoped 的用户监控对象表族：

```text
user_monitor_stock
user_monitor_index
user_monitor_board
```

设计原则：

```text
display cache = 全局只读筛选/解释数据
user_monitor_* = 用户自己的监控对象范围
每条监控对象必须 principal scoped
本轮只定义 contract，不允许写入
未来写入必须进入 B_TRACK_V2_USER_MONITOR_WRITE_CONTRACT_GATE
```

## 2. Table Schema Draft

### 2.1 `user_monitor_stock`

字段草案：

```text
monitor_id                 bigserial primary key
principal_id               text not null
principal_type             text not null
user_id                    text null
asset_kind                 text not null default 'stock'
identity_key               text not null
stock_identity_key         text not null
direction                  text not null
source_run_id              text null
projection_run_id          text null
condition_key              text null
source_cache_run_id        text null
source_display_cache_id    text null
source_type                text not null
source_snapshot_json       jsonb null
status                     text not null
quality_status             text not null
last_signal_state          text null
last_signal_event_time     timestamptz null
created_at                 timestamptz not null
updated_at                 timestamptz not null
removed_at                 timestamptz null
```

Checks:

```text
asset_kind = 'stock'
direction in ('buy', 'sell')
status in ('active', 'paused', 'removed', 'readonly_seed')
principal_id is not null
principal_type is not null
```

### 2.2 `user_monitor_index`

字段草案：

```text
monitor_id                 bigserial primary key
principal_id               text not null
principal_type             text not null
user_id                    text null
asset_kind                 text not null default 'index'
identity_key               text not null
index_identity_key         text not null
direction                  text not null
source_run_id              text null
projection_run_id          text null
condition_key              text null
source_cache_run_id        text null
source_display_cache_id    text null
source_type                text not null
source_snapshot_json       jsonb null
status                     text not null
quality_status             text not null
last_signal_state          text null
last_signal_event_time     timestamptz null
created_at                 timestamptz not null
updated_at                 timestamptz not null
removed_at                 timestamptz null
```

Checks:

```text
asset_kind = 'index'
direction in ('buy', 'sell')
status in ('active', 'paused', 'removed', 'readonly_seed')
principal_id is not null
principal_type is not null
```

### 2.3 `user_monitor_board`

字段草案：

```text
monitor_id                 bigserial primary key
principal_id               text not null
principal_type             text not null
user_id                    text null
asset_kind                 text not null default 'board'
identity_key               text not null
board_identity_key         text not null
direction                  text not null
source_run_id              text null
projection_run_id          text null
condition_key              text null
source_cache_run_id        text null
source_display_cache_id    text null
source_type                text not null
source_snapshot_json       jsonb null
status                     text not null
quality_status             text not null
last_signal_state          text null
last_signal_event_time     timestamptz null
created_at                 timestamptz not null
updated_at                 timestamptz not null
removed_at                 timestamptz null
```

Checks:

```text
asset_kind = 'board'
direction in ('buy', 'sell')
status in ('active', 'paused', 'removed', 'readonly_seed')
principal_id is not null
principal_type is not null
```

## 3. Required Fields

所有 `user_monitor_*` 表必须包含：

```text
principal_id
principal_type
identity_key
asset_kind
direction
source_run_id
projection_run_id
condition_key
status
quality_status
last_signal_state
created_at
updated_at
```

资产专属 identity 字段：

```text
user_monitor_stock.stock_identity_key
user_monitor_index.index_identity_key
user_monitor_board.board_identity_key
```

## 4. Index Contract

每张表必须具备以下索引策略：

```text
(principal_id, principal_type, status)
(principal_id, principal_type, identity_key)
(principal_id, principal_type, source_run_id)
(asset_kind, identity_key)
(principal_id, principal_type, asset_kind, identity_key, direction)
```

推荐唯一约束：

```text
unique active monitor:
  principal_id + principal_type + identity_key + direction
  where status in ('active', 'paused', 'readonly_seed')
```

## 5. Permission Boundary

本轮权限：

```text
GET user_monitor_* = planned readonly
POST user_monitor_* = locked
PATCH user_monitor_* = locked
DELETE user_monitor_* = locked
schema migration = not authorized
database write = false
```

未来写权限必须满足：

```text
current principal resolver
principal_id / principal_type required
write only current principal rows
idempotent add
soft remove by status='removed'
no trigger/action/proposal/order/trade/position/PnL side effects
no outbox consumption/update
```

## 6. API Contract

Active GET-only routes:

```text
GET /api/n6/app/v2/monitor
GET /api/n6/app/v2/monitor/stocks
GET /api/n6/app/v2/monitor/indexes
GET /api/n6/app/v2/monitor/boards
GET /api/n6/app/v2/monitor/stocks/{identity_key}
GET /api/n6/app/v2/monitor/indexes/{identity_key}
GET /api/n6/app/v2/monitor/boards/{identity_key}
```

Planned locked write routes:

```text
POST /api/n6/app/v2/monitor/write
PATCH /api/n6/app/v2/monitor/write
DELETE /api/n6/app/v2/monitor/write
```

Dry-run status:

```text
write_routes_registered=false
write_routes_enabled=false
write_routes_locked=true
```

## 7. UI Contract

页面：

```text
/n6/app/my-monitor
```

展示：

```text
名称
代码
identity_key
资产类型
方向：买向观察 / 卖向观察
状态
质量状态
最近信号状态
条件来源
加入来源
source_run_id
projection_run_id
created_at
updated_at
```

按钮：

```text
查看详情
查看相关信号
暂停监控（待开放） disabled
移除监控（待开放） disabled
```

安全条：

```text
只读模式 · 不下单 · 不构成投资建议 · principal scoped
```

## 8. Safety Boundary

Forbidden:

```text
read raw K
read N1 raw facts
read N4/N5 raw bypass
read condition_basis / condition_pool / minute_target_scope
read direct live market
read unreviewed outbox
write database in this gate
start worker
consume/update outbox
generate proposal/order/trade
update position
generate PnL
submit real trade
```

## 9. Decision

```text
CONTRACT_PASS
next=B_TRACK_V2_FILTER_CACHE_CONTRACT
write_extension_gate=B_TRACK_V2_USER_MONITOR_WRITE_CONTRACT_GATE
```
