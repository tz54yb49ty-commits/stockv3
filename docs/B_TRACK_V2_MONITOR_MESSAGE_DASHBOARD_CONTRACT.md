# B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_CONTRACT

Status: `CONTRACT_PASS`

Layer role: `runtime_control`

Date: `2026-06-14`

Scope: B轨 V2 “我的监控消息总览” contract。本 gate 只固化页面/API/数据边界/只读 dry-run 规则；不实现页面、不注册路由、不写数据库、不启动服务、不消费 outbox、不触发 projection run。

## 1. Objective

在已完成的 `effective_monitor` scoped signals 基础上，新增一个只读消息总览入口：

```text
筛选中心 -> 我的监控 -> 有效监控对象 -> N6 用户消息 -> 我的监控消息总览
```

总览只回答三个问题：

```text
当前有效监控对象有多少
当前有效监控交易日有哪些 N6 用户消息
如果没有消息，是无有效监控、无 N6 消息，还是 N6 projection 尚未覆盖
```

## 2. Route Model

Planned page route:

```text
GET /n6/app/messages
```

Planned GET-only APIs:

```text
GET /api/n6/app/v2/message-dashboard
GET /api/n6/app/v2/message-dashboard/groups
GET /api/n6/app/v2/message-dashboard/projection-status
```

Existing scoped signal APIs reused:

```text
GET /api/n6/app/v1/signals
GET /api/n6/app/v1/signals/{user_signal_projection_id}
```

Locked future write APIs:

```text
POST /api/n6/app/v2/messages/read-state      locked / not_registered
POST /api/n6/app/v2/messages/bulk-read       locked / not_registered
PATCH /api/n6/app/v2/messages/read-state     locked / not_registered
```

## 3. Principal Scope

All routes must use the current B轨 principal resolver.

Required principal fields:

```text
principal_id
principal_type
user_id
```

Failure behavior:

```text
missing principal -> 403 principal_scope_unavailable
ambiguous principal -> 403 principal_scope_unavailable
cross-principal access -> 404 or empty scoped result
```

Admin users entering B轨 are still scoped as B轨 principals; this contract does not reuse A轨 `/api/n6/ui/v1/...` adapters.

## 4. Effective Monitor Scope

Canonical effective monitor scope:

```text
effective_monitor_scope =
  user_monitor_stock
  union user_monitor_index
  union user_monitor_board
```

Effective batch rule:

```text
monitor.status = active
monitor.valid_source_trade_date = current_filter_batch.source_trade_date
monitor.valid_for_trade_date = current_filter_batch.for_trade_date
monitor.valid_source_run_id = current_filter_batch.source_run_id
```

Current filter batch sources:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
```

Message match rule:

```text
message.principal = current principal
message.asset_kind = monitor.asset_kind
message.identity_key = monitor.identity_key
message.direction = monitor.direction
message.trade_date = monitor.valid_for_trade_date
```

Message trade_date expression:

```text
COALESCE(
  user_signal_projection.display_payload_json->>'trade_date',
  user_signal_projection.source_payload_json->>'trade_date',
  user_signal_card.card_payload_json->>'trade_date',
  user_signal_projection.trace_json->>'trade_date'
)
```

Rows missing message trade_date are excluded from the effective message list and counted under `message_trade_date_missing`.

## 5. Allowed Sources

Allowed reads:

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

Explicitly out of MVP:

```text
user_notification_queue
```

Reason:

```text
消息总览的 MVP 只展示 N6 projection/card facts。
通知队列只可在后续 queue aggregate gate 中只读汇总，不得在本 gate 消费或更新。
```

## 6. Forbidden Sources And Side Effects

Forbidden reads:

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

Forbidden writes / effects:

```text
database business facts
user_signal_projection
user_signal_card
user_projection_run
user_notification_queue
N4/N5 facts
proposal/order/trade
position/PnL
real trade
outbox consume/update
worker start
projection run start
```

## 7. Dashboard API Contract

`GET /api/n6/app/v2/message-dashboard` response:

```json
{
  "component": "b_track_monitor_message_dashboard_v2",
  "component_label": "我的监控消息总览",
  "scope_mode": "effective_monitor",
  "principal": {
    "principal_id": 0,
    "principal_type": "human_user",
    "user_id": 0
  },
  "current_filter_batch": {
    "source_trade_date": null,
    "for_trade_date": null,
    "source_run_id": null,
    "status": "not_ready"
  },
  "summary": {
    "effective_monitor_count": 0,
    "expired_monitor_count": 0,
    "matched_signal_count": 0,
    "action_executed_count": 0,
    "action_blocked_count": 0,
    "action_eligible_count": 0,
    "action_skipped_count": 0,
    "pending_market_data_count": 0,
    "state_changed_count": 0,
    "excluded_message_count": 0
  },
  "event_counts": {},
  "asset_kind_counts": {},
  "direction_counts": {},
  "excluded_reason_counts": {
    "message_trade_date_missing": 0,
    "message_trade_date_mismatch": 0,
    "monitor_expired": 0
  },
  "projection_status": {},
  "groups": [],
  "items_preview": [],
  "empty_state": null,
  "safety": {
    "readonly": true,
    "get_only": true,
    "principal_scoped": true,
    "n6_projection_only": true
  }
}
```

Event count mapping:

```text
ActionExecuted -> 市场动作确认成立 (ActionExecuted)
ActionBlocked -> 市场动作未确认 (ActionBlocked)
ActionEligible -> 动作待确认 (ActionEligible)
ActionSkipped -> 动作已跳过 (ActionSkipped)
TriggerPendingMarketData -> 等待行情证据 (TriggerPendingMarketData)
TriggerStateChanged -> 状态变化 (TriggerStateChanged)
TriggerMatched -> 触发成立 (TriggerMatched)
```

## 8. Groups API Contract

`GET /api/n6/app/v2/message-dashboard/groups` response:

```json
{
  "component": "b_track_monitor_message_groups_v2",
  "scope_mode": "effective_monitor",
  "group_by": ["asset_kind", "direction", "event_type"],
  "current_filter_batch": {},
  "groups": [
    {
      "asset_kind": "stock",
      "asset_kind_label": "个股",
      "direction": "buy",
      "direction_label": "买向观察",
      "event_type": "ActionExecuted",
      "event_label": "市场动作确认成立 (ActionExecuted)",
      "effective_monitor_count": 0,
      "matched_signal_count": 0,
      "latest_event_time": null,
      "items_preview": []
    }
  ]
}
```

Default sorting:

```text
asset_kind: stock, board, index
direction: buy, sell
event priority: ActionExecuted, ActionBlocked, ActionEligible, ActionSkipped, TriggerPendingMarketData, TriggerStateChanged, TriggerMatched
latest_event_time desc
```

## 9. Projection Status API Contract

`GET /api/n6/app/v2/message-dashboard/projection-status` response:

```json
{
  "component": "b_track_monitor_projection_status_v2",
  "scope_mode": "effective_monitor",
  "current_filter_batch": {},
  "latest_user_projection_run_id": null,
  "latest_status": "not_ready",
  "latest_projection_trade_date": null,
  "expected_for_trade_date": null,
  "source_action_run_id": null,
  "started_at": null,
  "finished_at": null,
  "input_count": 0,
  "projection_count": 0,
  "card_count": 0,
  "error_count": 0,
  "status_reason": "current_filter_batch_not_ready"
}
```

Status reasons:

```text
current_filter_batch_not_ready
no_effective_monitor
projection_covers_for_trade_date
projection_not_covering_for_trade_date
no_projection_run
projection_error
```

## 10. UI Contract

Page title:

```text
我的监控消息总览
```

Top safety text:

```text
只读模式 · 不下单 · 不更新持仓 · 不构成投资建议 · principal scoped
```

Batch text:

```text
当前有效监控交易日：for_trade_date=YYYYMMDD
条件来源日：source_trade_date=YYYYMMDD
```

Summary cards:

```text
今日消息
已确认
未确认
待确认
等待行情证据
状态变化
被排除消息
```

List action:

```text
查看详情
```

Read-state MVP text:

```text
未读状态：暂未开放
当前仅展示消息，不保存已读/未读状态
```

## 11. Empty And Error States

Empty states:

```text
当前没有有效监控对象，请先从筛选中心加入监控
当前有效监控对象暂无 N6 用户消息
等待 N6 projection 生成用户消息
存在消息缺少 trade_date，已从有效监控消息中排除
当前筛选批次尚未准备完成
```

Error states:

```text
principal_scope_unavailable
message_dashboard_source_not_ready
projection_status_unavailable
```

Error pages must keep the same safety text and must not expose stack traces.

## 12. Read State Boundary

This gate does not implement read/unread writes.

Future read-state gate:

```text
B_TRACK_V2_MESSAGE_READ_STATE_CONTRACT_GATE
```

Future write scope must be limited to a principal-scoped read-state/preference table and must not update:

```text
user_signal_projection
user_signal_card
user_projection_run
user_notification_queue
N4/N5 facts
```

## 13. Implementation Gate Recommendation

Next gate:

```text
B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_IMPLEMENTATION_GATE
```

Implementation requirements:

```text
GET-only routes
principal scoped
reuse effective_monitor scope boundary
N6 projection/card only
no N5 outbox
no notification queue consume/update
no proposal/order/trade/position/PnL
targeted tests for metadata, empty states, projection status, and forbidden source scan
```
