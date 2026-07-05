# B_TRACK_V2_FILTER_CACHE_CONTRACT

Status: `CONTRACT_PASS`

Layer role: `runtime_control`

Date: `2026-06-07`

Scope: B轨 V2 筛选中心 display cache contract。本文档只定义只读筛选 API、allowlist、forbidden source policy 和 UI 字段，不执行 schema，不写数据库，不改 V1 代码。

## 1. Objective

筛选中心使用本地 N6 display cache，不直接读取 N1/N2/N3/N4/N5 内部裸表。

页面：

```text
/n6/app/filter-center
```

子模块：

```text
个股筛选
指数筛选
板块筛选
板块成分股
指数成分股
```

## 2. Allowlist

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

Display cache 来源必须已经过 N6 local display cache gate：

```text
N2 display_basis:
  stock_condition_display_basis
  index_condition_display_basis
  board_condition_display_basis

N1 membership_fact:
  index_membership_fact
  board_membership_fact
```

## 3. Forbidden Sources

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

筛选中心不得绕过 display cache 直接读 N2/N1 原始表。

## 4. Filter API Contract

Active GET-only routes：

```text
GET /api/n6/app/v2/filter
GET /api/n6/app/v2/filter/stocks
GET /api/n6/app/v2/filter/indexes
GET /api/n6/app/v2/filter/boards
GET /api/n6/app/v2/filter/indexes/{identity_key}/members
GET /api/n6/app/v2/filter/boards/{identity_key}/members
```

所有接口必须：

```text
principal scoped
GET-only
read-only
return principal_id / principal_type
使用 current principal resolver
```

查询参数：

```text
asset_kind
direction
year_overheat_level
quarter_overheat_level
month_overheat_level
week_overheat_level
day_overheat_level
condition_key
quality_status
last_signal_state
source_run_id
projection_run_id
cache_run_id
source_board_identity_key
source_index_identity_key
limit
cursor
sort
```

V2 筛选默认：

```text
direction=buy
direction_label=买向观察
sell direction hidden by default
```

## 5. UI Field Contract

筛选结果展示：

```text
名称
代码
identity_key
资产类型
方向
条件来源
年过度分级
季过度分级
月过度分级
周过度分级
日过度分级
最近信号状态
quality_status
source_run_id
projection_run_id
cache_run_id
```

板块/指数成分股展示：

```text
父级名称
父级代码
parent_identity_key
成分股名称
成分股代码
stock_identity_key
membership_kind
source_version
source_batch_id
```

## 6. Button Copy

允许按钮：

```text
应用筛选
清空筛选
查看详情
查看证据链
查看成分股
带入个股筛选
查看相关信号
```

禁用按钮：

```text
加入监控（待开放）
加入个股监控（待开放）
加入指数监控（待开放）
加入板块监控（待开放）
批量加入监控（待开放）
```

安全条：

```text
只读模式 · 不下单 · 不构成投资建议 · principal scoped
```

## 7. Add-To-Monitor Flow

本轮 dry-run 流程：

```text
筛选结果 -> 点击 加入监控（待开放） -> 展示 locked 状态 -> 不发起 POST -> 不写 user_monitor_* -> 不产生任何交易/持仓/PnL
```

未来流程：

```text
筛选结果 -> POST /api/n6/app/v2/monitor/write -> 写 user_monitor_* -> 信号 scope 更新
```

未来流程必须进入 `B_TRACK_V2_USER_MONITOR_WRITE_CONTRACT_GATE`。

## 8. Decision

```text
CONTRACT_PASS
next=B_TRACK_V2_SIGNAL_SCOPE_CONTRACT
```
