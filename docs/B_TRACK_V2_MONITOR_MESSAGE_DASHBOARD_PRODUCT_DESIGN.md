# B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_PRODUCT_DESIGN

Status: `PRODUCT_DESIGN_PASS`

Layer role: `runtime_control`

Date: `2026-06-14`

Scope: B轨 V2 “我的监控消息总览”产品设计。本 gate 只定义页面、用户旅程、信息架构、API 边界和后续路线图；不写代码、不写数据库、不启动服务、不消费 outbox、不触发交易、持仓或 PnL。

## 1. Design Brief

当前 B轨已经完成：

```text
筛选中心 -> 我的监控 -> 有效监控对象消息 scope
```

现在需要在 Signals 之上增加一个“消息总览”层，让普通用户一眼知道：

```text
今天我的有效监控对象有没有 N6 用户消息
哪些是市场动作确认成立
哪些是市场动作未确认
哪些等待行情证据或 projection
哪些消息因为 trade_date 缺失或批次不一致被排除
当前 N6 projection 是否已经覆盖当前 for_trade_date
```

设计原则：

```text
中文优先
系统事件中英双语
只展示当前 principal 的有效监控消息
message.trade_date 必须等于 monitor.valid_for_trade_date
只读 GET-only
N6 projection-only
不直接读 N5 common_event_outbox
不把未读/已读写入放进本 gate
```

## 2. Users

主要用户：

```text
B轨普通用户
```

用户目标：

```text
知道当前有效监控对象今天有没有消息
快速区分已确认、未确认、等待证据、状态变化
从总览进入单条信号详情看证据链
知道没有消息是因为“无有效监控对象”“暂无 N6 消息”还是“N6 projection 未生成”
知道旧批次监控对象不会进入今天消息 scope
```

非目标用户：

```text
A轨管理员
N4/N5 runtime operator
交易执行员
```

## 3. Page Tree

推荐页面树：

```text
/n6/app
  B轨首页
  - 我的监控消息摘要
  - projection 状态摘要

/n6/app/messages
  我的监控消息总览

/n6/app/signals
  我的监控消息列表

/n6/app/signals/{user_signal_projection_id}
  消息详情 / 证据链

/n6/app/my-monitor
  我的监控

/n6/app/my-monitor/stocks
  我的个股监控

/n6/app/my-monitor/boards
  我的板块监控

/n6/app/my-monitor/indexes
  我的指数监控
```

导航建议：

```text
首页
筛选中心
我的监控
消息
状态监控
账户
AI助手
```

说明：

```text
“消息”作为新的一级入口更清晰。
原“信号”可在 V2.1 中逐步改名为“消息”，或保留为“消息列表”的子入口。
不建议同时保留“信号”和“消息”两个同级入口，避免普通用户理解成本上升。
```

## 4. User Journey

### 4.1 有消息的旅程

1. 用户从首页看到“我的监控消息摘要”。
2. 摘要显示当前有效交易日、有效监控对象数量、今日消息数量。
3. 用户进入 `消息`。
4. 顶部显示当前批次：

```text
当前有效监控交易日：for_trade_date=YYYYMMDD
条件来源日：source_trade_date=YYYYMMDD
```

5. 用户按事件组查看：

```text
市场动作确认成立 (ActionExecuted)
市场动作未确认 (ActionBlocked)
动作待确认 (ActionEligible)
动作已跳过 (ActionSkipped)
触发成立 (TriggerMatched)
等待行情证据 (TriggerPendingMarketData)
状态变化 (TriggerStateChanged)
```

6. 用户点击一条消息进入详情页，只读查看：

```text
标的
方向
N2 -> N3 -> N4 -> N5 -> N6 证据链
condition_key
source_run_id
projection_run_id
event_time
message_trade_date
```

### 4.2 无有效监控对象

页面显示：

```text
当前没有有效监控对象，请先从筛选中心加入监控
```

提供入口：

```text
去筛选中心
去我的监控
```

### 4.3 有监控但无消息

页面显示：

```text
当前有效监控对象暂无 N6 用户消息
```

辅助解释：

```text
这表示当前有效监控对象在本交易日还没有进入 N6 用户消息。
不代表 N5 没有事件，也不代表交易建议。
```

### 4.4 N6 projection 未覆盖

当存在当前有效监控对象，但最新 `user_projection_run` 不覆盖当前 `for_trade_date` 时，页面显示：

```text
等待 N6 projection 生成用户消息
```

辅助字段：

```text
latest_projection_run_id
latest_projection_status
latest_projection_trade_date
expected_for_trade_date
input_count
output_projection_count
output_card_count
```

### 4.5 消息被排除

排除原因只在“数据边界 / 诊断区”展示，不打扰普通用户主路径。

```text
message_trade_date_missing
message_trade_date_mismatch
monitor_expired
principal_mismatch
```

普通用户文案：

```text
部分消息缺少 trade_date，已从当前有效监控消息中排除
部分消息不属于当前有效交易日，已归入历史范围
```

## 5. Information Architecture

### 5.1 顶部安全条

```text
只读模式 · 不下单 · 不更新持仓 · 不构成投资建议 · principal scoped
```

### 5.2 当前批次条

字段：

```text
source_trade_date
for_trade_date
source_run_id
current_filter_batch_status
effective_monitor_count
expired_monitor_count
```

用户文案：

```text
当前有效监控交易日
条件来源日
有效监控对象
已失效对象
```

### 5.3 消息概览卡片

推荐卡片：

```text
今日消息
已确认
未确认
待确认 / 已跳过
等待行情证据
状态变化
被排除消息
```

卡片点击行为：

```text
点击卡片 -> 切换下方列表筛选
```

### 5.4 监控对象分组

分组维度：

```text
个股
板块
指数
买向观察
卖向观察
```

每组展示：

```text
有效监控对象数
今日消息数
最近消息时间
已确认 / 未确认数量
暂无消息数量
```

### 5.5 消息列表

默认排序：

```text
event_time desc
ActionExecuted 优先
ActionBlocked 次之
TriggerPendingMarketData / TriggerStateChanged 后置
```

列：

```text
类型
标的
方向
事件
动作状态
动作标记
blocked_reason
message_trade_date
event_time
projection_run_id
```

操作：

```text
查看详情
```

禁止：

```text
买入
卖出
快捷下单控件
生成方案
更新持仓
成交状态标记
```

### 5.6 Projection 状态区

目的：解释“为什么我的监控没有消息”。

字段：

```text
latest_user_projection_run_id
latest_status
source_action_run_id
trade_date
started_at
finished_at
input_count
projection_count
card_count
queue_count_optional
error_count
```

P0 不读取 `user_notification_queue`，避免把消息总览和通知队列消费语义混在一起。

V2.1 可增加只读 queue aggregate：

```text
queued
delivered
failed
```

但仍禁止 consume / update queue。

## 6. Unread State Design

本 gate 不开放“标记已读”写入。

### 6.1 MVP 只读表达

MVP 先使用：

```text
未处理
已查看能力未开放
```

页面可显示：

```text
未读状态：暂未开放
当前仅展示消息，不保存已读/未读状态
```

### 6.2 V2.1 写入 gate

未来单独进入：

```text
B_TRACK_V2_MESSAGE_READ_STATE_CONTRACT_GATE
```

候选表：

```text
user_message_read_state
```

或复用：

```text
user_signal_decision
```

写入原则：

```text
principal scoped
只写用户阅读偏好
不写 user_signal_projection / user_signal_card
不更新 user_notification_queue
不消费 outbox
不触发 proposal/order/trade/position/PnL
```

## 7. API Boundary

### 7.1 MVP GET-only API

```text
GET /api/n6/app/v2/message-dashboard
GET /api/n6/app/v2/message-dashboard/groups
GET /api/n6/app/v2/message-dashboard/projection-status
GET /api/n6/app/v1/signals
GET /api/n6/app/v1/signals/{user_signal_projection_id}
```

`/api/n6/app/v2/message-dashboard` 返回：

```json
{
  "scope_mode": "effective_monitor",
  "current_filter_batch": {},
  "effective_monitor_count": 0,
  "expired_monitor_count": 0,
  "matched_signal_count": 0,
  "event_counts": {},
  "asset_kind_counts": {},
  "direction_counts": {},
  "excluded_reason_counts": {},
  "projection_status": {},
  "groups": [],
  "items_preview": []
}
```

### 7.2 Locked Future Write API

```text
POST /api/n6/app/v2/messages/read-state     locked
POST /api/n6/app/v2/messages/bulk-read      locked
PATCH /api/n6/app/v2/messages/read-state    locked
```

锁定原因：

```text
需要单独 read-state contract
需要 principal scoped 幂等写
需要和 user_signal_decision / read-state table 边界确认
```

## 8. Data Boundary

允许读取：

```text
user_signal_projection
user_signal_card
user_projection_run
user_monitor_stock
user_monitor_index
user_monitor_board
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
```

P0 不读取：

```text
user_notification_queue
```

未来只读 queue aggregate 必须单独 gate。

禁止读取：

```text
common_event_outbox
condition_basis
condition_pool
minute_target_scope
raw K
direct live market
N4 raw facts bypass
N5 raw facts bypass
unreviewed outbox
```

禁止写入：

```text
user_signal_projection
user_signal_card
user_projection_run
user_notification_queue
N4/N5 facts
proposal/order/trade
position/PnL
```

## 9. Permission Boundary

所有 API 必须：

```text
current principal resolver
principal_id required
principal_type required
missing / ambiguous principal -> 403 principal_scope_unavailable
only current principal monitor scope
```

权限：

```text
普通用户：只能看自己的消息总览
管理员：在 B轨入口也按当前 principal scope 展示，不自动看全用户
A轨管理员跨用户排查必须留在 A轨或单独 admin tool
```

## 10. Empty / Error States

空状态：

```text
当前没有有效监控对象，请先从筛选中心加入监控
当前有效监控对象暂无 N6 用户消息
等待 N6 projection 生成用户消息
部分消息缺少 trade_date，已从当前有效监控消息中排除
当前筛选批次尚未准备完成
```

错误状态：

```text
principal_scope_unavailable -> 当前账号范围不可用，请重新登录
projection_status_unavailable -> N6 projection 状态暂不可用
message_scope_unavailable -> 当前监控消息范围暂不可用
```

## 11. MVP / V2 / V3 Roadmap

### MVP

```text
新增消息总览页面 /n6/app/messages
新增 GET-only message-dashboard API
复用 effective monitor scoped signals
展示 current batch、event counts、asset/direction counts、projection status
不做已读写入
不读 notification queue
```

### V2.1

```text
加入 user_message_read_state 或 user_signal_decision read-state contract
开放标记已读 / 全部已读
增加“未读 / 已读 / 全部”筛选
增加用户最近查看时间
可选只读读取 user_notification_queue aggregate
```

### V3

```text
AI助手解释消息摘要
消息按策略主题聚合
通知队列、mobile、voice 仍由独立 gate 控制
虚拟持仓对象消息与监控对象消息合并展示
历史批次归档查询
```

## 12. Absolutely Not Now

当前不要做：

```text
标记已读写入
通知队列 consume/update
直接读 N5 common_event_outbox
推送通知
语音播报
生成方案
下单
真实交易
更新持仓
计算实际账户收益
跨 principal 查看
自动归档旧消息
自动触发 N6 projection
```

## 13. Next Gate Recommendation

```text
B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_CONTRACT_GATE
```

目标：

```text
固化 GET-only API contract
固化 message-dashboard response schema
固化 projection-status schema
固化 read-state locked boundary
生成 dry-run artifacts
```
