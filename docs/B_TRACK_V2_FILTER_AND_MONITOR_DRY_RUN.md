# B_TRACK_V2_FILTER_AND_MONITOR_DRY_RUN

Status: `DRY_RUN_PASS`

Layer role: `runtime_control`

Date: `2026-06-07`

Scope: B轨 V2 筛选中心 + 我的监控 dry-run。本文档汇总 schema、allowlist、forbidden sources、API route、UI 文案、加入监控流程和 implementation gate 建议。不改 V1 代码，不写数据库，不启动 worker。

## 1. Inputs

```text
B_TRACK_V2_FILTER_AND_MONITOR_PRODUCT_DESIGN = PRODUCT_DESIGN_PASS
B_TRACK_V2_USER_MONITOR_CONTRACT = CONTRACT_PASS
B_TRACK_V2_FILTER_CACHE_CONTRACT = CONTRACT_PASS
B_TRACK_V2_SIGNAL_SCOPE_CONTRACT = CONTRACT_PASS
```

## 2. Schema Dry-run

将来需要的用户监控表：

```text
user_monitor_stock
user_monitor_index
user_monitor_board
```

Dry-run 结论：

```text
principal scoped = true
read contract = GET-only
write contract = locked / disabled
schema migration executed = false
database written = false
```

必要字段：

```text
principal_id
principal_type
identity_key
stock_identity_key / index_identity_key / board_identity_key
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

必要索引：

```text
principal_id
identity_key
source_run_id
asset_kind
principal_id + principal_type + identity_key + direction
```

## 3. Allowlist / Forbidden Source Dry-run

允许读取：

```text
reviewed N6 projections
reviewed signal cards
n6_stock_display_cache
n6_index_display_cache
n6_board_display_cache
n6_index_membership_display_cache
n6_board_membership_display_cache
```

禁止读取：

```text
raw K
N1 raw facts
N4 raw bypass
N5 raw bypass
condition_basis
condition_pool
minute_target_scope
direct live market
unreviewed outbox
```

Dry-run proof:

```text
display_cache_only=true
reviewed_projection_only=true
raw_source_bypass=false
```

## 4. API Route Dry-run

Active GET-only routes：

```text
GET /api/n6/app/v2/filter
GET /api/n6/app/v2/filter/stocks
GET /api/n6/app/v2/filter/indexes
GET /api/n6/app/v2/filter/boards
GET /api/n6/app/v2/filter/indexes/{identity_key}/members
GET /api/n6/app/v2/filter/boards/{identity_key}/members
GET /api/n6/app/v2/monitor
GET /api/n6/app/v2/monitor/stocks
GET /api/n6/app/v2/monitor/indexes
GET /api/n6/app/v2/monitor/boards
GET /api/n6/app/v2/monitor/stocks/{identity_key}
GET /api/n6/app/v2/monitor/indexes/{identity_key}
GET /api/n6/app/v2/monitor/boards/{identity_key}
GET /api/n6/app/v2/signal-scope
GET /api/n6/app/v2/signals
GET /api/n6/app/v2/signals/{user_signal_projection_id}
```

Locked future routes：

```text
POST /api/n6/app/v2/monitor/write
PATCH /api/n6/app/v2/monitor/write
DELETE /api/n6/app/v2/monitor/write
```

Dry-run status：

```text
active_non_get_routes=0
write_routes_registered=false
write_routes_enabled=false
write_routes_locked=true
route_scan_get_only=PASS
```

## 5. UI Dry-run

页面：

```text
/n6/app/filter-center
/n6/app/my-monitor
```

筛选中心字段：

```text
名称
代码
方向
条件来源
最近信号状态
年过度分级
季过度分级
月过度分级
周过度分级
日过度分级
quality_status
source_run_id
projection_run_id
```

我的监控字段：

```text
名称
代码
状态
最近信号
加入来源
direction
condition_key
quality_status
created_at
updated_at
```

按钮：

```text
应用筛选
清空筛选
查看详情
查看证据链
查看成分股
加入监控（待开放） disabled
暂停监控（待开放） disabled
移除监控（待开放） disabled
```

安全文案：

```text
只读模式 · 不下单 · 不构成投资建议 · principal scoped
```

## 6. Add Monitor Flow Dry-run

本轮流程：

```text
1. 用户在筛选中心看到候选标的
2. 页面展示“加入监控（待开放）”
3. 按钮 disabled
4. 不调用 POST / PATCH / DELETE
5. 不写 user_monitor_*
6. 不改变 signal scope
7. 不生成 proposal/order/trade/position/PnL
```

未来流程：

```text
1. 用户点击加入监控
2. POST /api/n6/app/v2/monitor/write
3. current principal resolver 解析 principal_id / principal_type
4. 写入当前 principal 的 user_monitor_* row
5. signal scope projection 增加对象
6. 信号中心只读展示新 scope
```

未来流程必须另开：

```text
B_TRACK_V2_USER_MONITOR_WRITE_CONTRACT_GATE
```

## 7. Forbidden Operation Proof

本 dry-run 未执行：

```text
code modification
schema migration
database write
outbox consume/update
worker start
N4/N5/N6 execute
proposal generation
order generation
trade generation
position update
PnL generation
real trade submission
direct live market read
raw K read
N1/N2 raw/internal source read
N4/N5 raw bypass
```

## 8. Validation Summary

Expected validation:

```text
JSON parse PASS
schema assertion PASS
allowlist assertion PASS
forbidden source proof PASS
route scan GET-only PASS
git diff --check PASS
```

## 9. Next Gate

```text
B_TRACK_V2_FILTER_AND_MONITOR_IMPLEMENTATION_GATE
```

Implementation gate 必须保持：

```text
GET-only active routes
principal scoped
write routes locked
display cache only
reviewed N6 projection/signal card only
no raw sources
no transaction/position/PnL side effects
```

若要开放加入/移出/暂停监控，必须先进入：

```text
B_TRACK_V2_USER_MONITOR_WRITE_CONTRACT_GATE
```

## 10. Decision

```text
DRY_RUN_PASS
next=B_TRACK_V2_FILTER_AND_MONITOR_IMPLEMENTATION_GATE
```
