# B_TRACK_V2_SIGNAL_SCOPE_CONTRACT

Status: `CONTRACT_PASS`

Layer role: `runtime_control`

Date: `2026-06-07`

Scope: B轨 V2 信号范围 contract。本文档定义信号中心如何从“全量 reviewed signals”收敛到“我的监控对象 + 虚拟账户持仓对象”，不修改代码、不写数据库、不消费 outbox。

## 1. Objective

B轨 V2 信号中心默认只展示当前 principal 关心的信号：

```text
user signal scope =
  user_monitor_stock/index/board active rows
  UNION virtual account holding objects
```

信号仍然只能来自：

```text
reviewed N6 projections
reviewed signal cards
```

不得为了信号过滤直接读取 N4/N5 raw facts、condition_basis、condition_pool、minute_target_scope、raw K 或 direct live market。

## 2. Scope Inputs

允许输入：

```text
user_monitor_stock
user_monitor_index
user_monitor_board
virtual account holding projection
reviewed N6 projections
reviewed signal cards
n6_stock_display_cache
n6_index_display_cache
n6_board_display_cache
n6_index_membership_display_cache
n6_board_membership_display_cache
```

虚拟账户持仓对象为 future-proof scope，只读使用，不触发持仓更新。

## 3. Signal Scope Model

建议只读 projection：

```text
user_signal_scope_projection
```

字段草案：

```text
principal_id
principal_type
asset_kind
identity_key
scope_source
monitor_id
virtual_account_id
virtual_position_id
direction
status
quality_status
last_signal_state
last_signal_event_time
projection_run_id
source_run_id
updated_at
```

`scope_source`：

```text
monitor_object
virtual_holding
monitor_and_holding
```

## 4. API Contract

Active GET-only routes：

```text
GET /api/n6/app/v2/signal-scope
GET /api/n6/app/v2/signals
GET /api/n6/app/v2/signals/{user_signal_projection_id}
```

所有接口必须：

```text
principal scoped
GET-only
read-only
return principal_id / principal_type
只返回当前 principal 的 scope 内信号
```

默认过滤：

```text
scope=monitor_or_virtual_holding
```

## 5. UI Contract

信号中心显示：

```text
名称
代码
identity_key
资产类型
方向
scope 来源：我的监控 / 虚拟持仓 / 监控与持仓
市场动作状态
最近信号状态
条件来源
quality_status
source_run_id
projection_run_id
event_time
```

详情页显示证据链：

```text
N2 display_basis -> N3 -> N4 -> N5 -> N6
```

详情页不得显示：

```text
买入按钮
卖出按钮
一键下单
自动交易开关
真实持仓更新
真实收益
投资建议
```

安全条：

```text
只读模式 · 不下单 · 不构成投资建议 · principal scoped
```

## 6. Forbidden Sources

禁止：

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

## 7. Decision

```text
CONTRACT_PASS
next=B_TRACK_V2_FILTER_AND_MONITOR_DRY_RUN
```
