# B_TRACK_V2_FILTER_AND_MONITOR_PRODUCT_DESIGN

Status: `PRODUCT_DESIGN_PASS`

Layer role: `runtime_control`

Date: `2026-06-07`

Scope: B轨 V2 筛选中心 + 我的监控产品设计。本文档只定义页面、用户旅程、只读 API contract、数据表 contract 和后续 gate，不修改 V1 代码，不写数据库，不启动 worker，不触发交易、持仓或 PnL。

## 1. 设计结论

B轨 V2 需要新增两组用户入口：

```text
筛选中心
  个股筛选
  板块筛选
  指数筛选

我的监控
  个股监控
  板块监控
  指数监控
```

当前 V1 的 `关注池` 是只读 projection 摘要，不是用户自维护监控对象池。V2 不应继续把“关注池”承担为真正监控中心，而应新增 `我的监控`，并在后续版本逐步将 `关注池` 降级为兼容入口或摘要入口。

核心原则：

```text
全局 display cache 只读
用户监控对象 principal scoped
V2 本轮 API GET-only
本轮不提供持久化加入/移出/暂停监控
未来写入用户监控偏好必须进入独立 gate
信号中心未来默认只看：我的监控对象 + 虚拟账户持仓对象
```

## 2. 页面树与导航

V2 推荐页面树：

```text
/n6/app
  B轨首页

/n6/app/filter
  筛选中心

/n6/app/filter/stocks
  个股筛选

/n6/app/filter/boards
  板块筛选

/n6/app/filter/indexes
  指数筛选

/n6/app/filter/boards/{identity_key}/members
  板块成分股

/n6/app/filter/indexes/{identity_key}/members
  指数成分股

/n6/app/monitor
  我的监控

/n6/app/monitor/stocks
  个股监控

/n6/app/monitor/boards
  板块监控

/n6/app/monitor/indexes
  指数监控

/n6/app/signals
  信号中心
```

导航结构：

```text
首页
筛选中心
  个股筛选
  板块筛选
  指数筛选
我的监控
  个股监控
  板块监控
  指数监控
信号
状态监控
账户
AI助手
方案
组合
收益
排行榜
退出登录
```

V2 首页模块建议：

```text
只读安全条
今日概览
我的监控摘要
筛选中心入口
我的信号摘要
虚拟账户持仓观察摘要
未来功能锁定区
```

## 3. 用户旅程

### 3.1 个股筛选旅程

1. 用户进入 `筛选中心 -> 个股筛选`。
2. 页面默认展示 `买向观察` 方向，不展示卖向筛选。
3. 用户设置筛选条件：
   - 年过度分级
   - 季过度分级
   - 月过度分级
   - 周过度分级
   - 日过度分级
4. 页面通过 GET 查询 `n6_stock_display_cache` 的只读结果。
5. 结果展示名称、代码、`identity_key`、五个周期分级、质量状态、来源 run、证据摘要。
6. V2 只读状态下展示 `加入个股监控（待开放）`，按钮禁用。
7. 用户可点 `查看证据链` 进入详情，只读查看 display cache 与 N6 projection 证据。

### 3.2 板块筛选旅程

1. 用户进入 `筛选中心 -> 板块筛选`。
2. 页面默认展示 `买向观察` 方向。
3. 用户设置年/季/月/周/日过度分级。
4. 页面通过 GET 查询 `n6_board_display_cache`。
5. 用户可点击 `查看成分股`。
6. 页面通过 GET 查询 `n6_board_membership_display_cache`，展示该板块成分股。
7. 用户可点击 `带入个股筛选`，跳转到个股筛选并带入 `source_board_identity_key` 查询上下文。
8. V2 只读状态下展示 `加入板块监控（待开放）`，按钮禁用。

### 3.3 指数筛选旅程

1. 用户进入 `筛选中心 -> 指数筛选`。
2. 页面默认展示 `买向观察` 方向。
3. 用户设置年/季/月/周/日过度分级。
4. 页面通过 GET 查询 `n6_index_display_cache`。
5. 用户可点击 `查看成分股`。
6. 页面通过 GET 查询 `n6_index_membership_display_cache`，展示该指数成分股。
7. 用户可点击 `带入个股筛选`，跳转到个股筛选并带入 `source_index_identity_key` 查询上下文。
8. V2 只读状态下展示 `加入指数监控（待开放）`，按钮禁用。

### 3.4 我的监控旅程

1. 用户进入 `我的监控`。
2. 页面展示 principal scoped 的监控摘要：
   - 个股监控数量
   - 板块监控数量
   - 指数监控数量
   - 虚拟账户持仓观察数量
   - 今日相关信号数量
3. 用户进入 `个股监控` / `板块监控` / `指数监控`。
4. 页面只读展示该用户已有监控对象，不允许新增、删除、暂停、排序持久化。
5. 每个监控对象可查看：
   - 监控方向
   - 来源
   - 加入时筛选快照
   - 最新信号状态
   - 关联虚拟持仓状态
   - 质量状态

### 3.5 信号 scope 旅程

1. 用户进入 `信号中心`。
2. 默认 scope 为：

```text
我的监控对象 OR 虚拟账户持仓对象
```

3. 用户不再查看所有 reviewed N6 signals。
4. 详情页仍只读展示证据链，不显示下单、交易、持仓更新或投资建议。

## 4. 数据表 Contract

本节是产品和 schema contract 草案，不授权 schema migration。

### 4.1 Display Cache

全局只读 display cache：

```text
n6_display_cache_run
n6_stock_display_cache
n6_index_display_cache
n6_board_display_cache
n6_index_membership_display_cache
n6_board_membership_display_cache
```

来源：

```text
N2 display_basis:
  stock_condition_display_basis
  index_condition_display_basis
  board_condition_display_basis

N1 membership_fact:
  index_membership_fact
  board_membership_fact
```

用途：

```text
筛选中心读取 display cache
监控中心读取 display cache 作为对象展示补充
信号中心读取 display cache 作为证据链说明
不得把 display cache 写成用户监控偏好
不得从 display cache 反向更新 N1/N2/N3/N4/N5
```

筛选字段建议：

```text
identity_key
code
name
asset_kind
direction
condition_key
selected_signal_types_json
year_overheat_level
quarter_overheat_level
month_overheat_level
week_overheat_level
day_overheat_level
period_summary_json
target_price_context_json
quality_status
cache_run_id
source_run_id
source_updated_at
```

说明：字段名可在后续 schema gate 统一确定；用户界面显示为“年过度分级 / 季过度分级 / 月过度分级 / 周过度分级 / 日过度分级”，内部字段保持英文。

### 4.2 User Monitor Tables

用户监控对象必须独立于全局 display cache，且必须 principal scoped。

建议表族：

```text
user_monitor_stock_object
user_monitor_index_object
user_monitor_board_object
user_monitor_stock_scope_projection
user_monitor_index_scope_projection
user_monitor_board_scope_projection
```

`user_monitor_*_object` 字段建议：

```text
monitor_object_id
principal_id
principal_type
asset_kind
identity_key
monitor_direction
monitor_status
source_type
source_filter_snapshot_json
source_parent_asset_kind
source_parent_identity_key
source_cache_run_id
source_display_cache_id
created_at
updated_at
removed_at
```

`monitor_direction` V2 默认：

```text
buy
```

用户展示：

```text
buy -> 买向观察
sell -> 卖向观察
```

`monitor_status` 建议：

```text
active -> 监控中
paused -> 已暂停
removed -> 已移出
readonly_seed -> 只读预置
```

`source_type` 建议：

```text
manual -> 手动加入
filter -> 筛选加入
board_membership -> 板块成分
index_membership -> 指数成分
virtual_holding -> 虚拟持仓
system_seed -> 系统预置
```

本轮 V2 只读 contract 不授权写入这些表。实现时只能读取已有 rows 或 mock/fixture preview。真正的新增、移出、暂停、批量加入必须进入后续 write contract gate。

### 4.3 Signal Scope Projection

未来信号中心默认 scope：

```text
user_signal_scope =
  active user_monitor_*_object
  UNION virtual account holding objects
```

建议只读 projection：

```text
user_monitor_stock_scope_projection
user_monitor_index_scope_projection
user_monitor_board_scope_projection
```

字段建议：

```text
principal_id
principal_type
asset_kind
identity_key
scope_source
monitor_object_id
virtual_account_id
virtual_position_id
monitor_direction
scope_status
latest_signal_id
latest_signal_event_time
latest_action_state
latest_quality_status
projection_run_id
updated_at
```

`scope_source`：

```text
monitor_object -> 我的监控
virtual_holding -> 虚拟持仓
monitor_and_holding -> 监控与持仓
```

## 5. API 设计

本轮 API contract 全部 GET-only，principal scoped。

### 5.1 筛选中心 API

```text
GET /api/n6/app/v2/filter/summary
GET /api/n6/app/v2/filter/stocks
GET /api/n6/app/v2/filter/boards
GET /api/n6/app/v2/filter/indexes
GET /api/n6/app/v2/filter/boards/{identity_key}/members
GET /api/n6/app/v2/filter/indexes/{identity_key}/members
```

筛选查询参数：

```text
direction=buy
year_overheat_level
quarter_overheat_level
month_overheat_level
week_overheat_level
day_overheat_level
quality_status
cache_run_id
source_board_identity_key
source_index_identity_key
page
limit
sort
```

约束：

```text
direction 仅允许 buy
limit 必须有上限
默认只读查询 active display cache
不得查询 condition_basis / condition_pool / minute_target_scope
不得查询 raw K / direct live market / N4/N5 raw facts
```

### 5.2 我的监控 API

```text
GET /api/n6/app/v2/monitor/summary
GET /api/n6/app/v2/monitor/stocks
GET /api/n6/app/v2/monitor/boards
GET /api/n6/app/v2/monitor/indexes
GET /api/n6/app/v2/monitor/stocks/{identity_key}
GET /api/n6/app/v2/monitor/boards/{identity_key}
GET /api/n6/app/v2/monitor/indexes/{identity_key}
```

约束：

```text
必须使用 current principal resolver
必须返回 principal_id / principal_type
只能读取当前 principal 的监控对象
不得返回其他用户监控对象
不得提供 POST / PUT / PATCH / DELETE
不得持久化排序、筛选、加入、移出、暂停
```

### 5.3 信号 Scope API

```text
GET /api/n6/app/v2/signal-scope
GET /api/n6/app/v2/signals
GET /api/n6/app/v2/signals/{user_signal_projection_id}
```

默认规则：

```text
signals scope = 我的监控对象 + 虚拟账户持仓对象
```

约束：

```text
只读 reviewed N6 projections / signal cards
只读 user_monitor_* scope projection
只读 virtual holding projection
不生成 proposal/order/trade/position/PnL
不消费 outbox
不改变 N5 outbox 状态
```

## 6. 按钮文案

允许的只读按钮：

```text
应用筛选
清空筛选
查看详情
查看证据链
查看成分股
带入个股筛选
查看相关信号
查看监控状态
返回筛选中心
返回我的监控
```

V2 只读预留按钮，必须禁用：

```text
加入个股监控（待开放）
加入板块监控（待开放）
加入指数监控（待开放）
批量加入监控（待开放）
暂停监控（待开放）
移出监控（待开放）
保存筛选条件（待开放）
```

推荐替代表达：

```text
不要说“买入到监控”
使用“加入监控”
方向展示使用“买向观察”
```

安全提示：

```text
只读模式 · 不下单 · 不更新持仓 · 不构成投资建议
本页仅展示已审核的系统缓存、监控范围和证据链，不代表交易建议
当前入口不会生成方案、订单、交易或持仓变化
```

空状态文案：

```text
暂无符合条件的对象
暂无监控对象
暂无相关信号
暂无成分股数据
当前筛选仅展示买向观察对象
```

错误状态文案：

```text
读取失败，请稍后重试
当前用户范围不可用
展示缓存尚未就绪
该对象不在当前用户范围内
```

## 7. 禁止操作清单

本 gate 禁止：

```text
修改现有 V1 代码
写数据库
执行 schema migration
启动 worker
消费或更新 outbox
触发 N4/N5/N6 execute
生成 proposal
生成 order
生成 trade
更新 position
生成 PnL
提交真实交易
拉取 direct live market
读取 raw K
读取 N1 raw facts
绕过 reviewed N6 projections / signal cards
读取 N4/N5 raw facts bypass
读取 condition_basis
读取 condition_pool
读取 minute_target_scope
提供 POST / PUT / PATCH / DELETE API
提供一键下单或自动交易控件
把 BUY_HINT / SELL_HINT 渲染为投资建议
```

禁止用户文案：

```text
建议买入
建议卖出
买入机会
卖出提醒
一键下单
已买入
已卖出
已成交
实盘账户
可用下单资金
真实收益
稳赚
高胜率
低风险
高收益
```

## 8. MVP / V2 / V3 拆分

### MVP for V2 Readonly

```text
筛选中心页面树
个股/板块/指数筛选 GET API contract
成分股 drilldown GET API contract
我的监控只读页面树
我的信号 scope contract
禁用态加入监控按钮
中文化词表和安全提示
```

### V2 Write Extension

必须单独进入 contract gate 后才允许：

```text
加入监控
移出监控
暂停/恢复监控
保存筛选条件
批量加入监控
用户自定义排序持久化
```

### V3

```text
监控策略模板
AI助手解释筛选结果
虚拟持仓与监控对象联动策略
用户级信号通知偏好
批量成分股监控风险提示
移动端卡片
```

V3 仍不得默认为真实交易入口。任何真实交易、真实持仓、真实 PnL 必须另开明确 gate。

## 9. 下一步 Gate Recommendation

建议下一步：

```text
B_TRACK_V2_FILTER_AND_MONITOR_CONTRACT_GATE
```

该 gate 输出：

```text
docs/B_TRACK_V2_FILTER_AND_MONITOR_CONTRACT.md
docs/B_TRACK_V2_FILTER_AND_MONITOR_CONTRACT.json
docs/B_TRACK_V2_FILTER_AND_MONITOR_DRY_RUN.md
docs/B_TRACK_V2_FILTER_AND_MONITOR_DRY_RUN.json
```

该 gate 应验证：

```text
GET-only route model
principal scope model
display cache allowlist
user_monitor_* readonly scope
virtual holding scope compatibility
forbidden source policy
forbidden wording policy
no database write
no worker
no outbox consumption
no proposal/order/trade/position/PnL
```

如果用户确认要真正“加入监控”，则后续必须另开：

```text
B_TRACK_V2_USER_MONITOR_WRITE_CONTRACT_GATE
```

该 gate 不属于本轮只读设计范围。

## 10. Boundary Proof

本 artifact 只登记产品设计：

```text
code_modified=false
database_written=false
schema_executed=false
worker_started=false
outbox_consumed=false
proposal_generated=false
order_generated=false
trade_generated=false
position_updated=false
pnl_generated=false
real_trade_submitted=false
```

Decision:

```text
PRODUCT_DESIGN_PASS
next_gate=B_TRACK_V2_FILTER_AND_MONITOR_CONTRACT_GATE
```
