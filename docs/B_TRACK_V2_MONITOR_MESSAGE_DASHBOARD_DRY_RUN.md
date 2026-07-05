# B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_DRY_RUN

Status: `DRY_RUN_PASS`

Layer role: `runtime_control`

Date: `2026-06-14`

Scope: B轨 V2 “我的监控消息总览” dry-run。本 dry-run 只验证 contract 语义、路由模型、scope 模型和安全边界；不注册路由、不执行 SQL、不写数据库、不启动服务。

## 1. Dry-run Inputs

Reference contract:

```text
docs/B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_CONTRACT.md
docs/B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_CONTRACT.json
```

Upstream closeout:

```text
B_TRACK_V2_MONITOR_SCOPED_SIGNALS_COMPLETE = true
```

Example current filter batch:

```text
source_trade_date = 20260612
for_trade_date = 20260615
source_run_id = condition_layer_20260612_source_20260612_for_20260615_v1
```

## 2. Route Dry-run

Planned active routes are GET-only:

```text
GET /n6/app/messages
GET /api/n6/app/v2/message-dashboard
GET /api/n6/app/v2/message-dashboard/groups
GET /api/n6/app/v2/message-dashboard/projection-status
```

Existing reused routes:

```text
GET /api/n6/app/v1/signals
GET /api/n6/app/v1/signals/{user_signal_projection_id}
```

Locked future routes remain unregistered:

```text
POST /api/n6/app/v2/messages/read-state
POST /api/n6/app/v2/messages/bulk-read
PATCH /api/n6/app/v2/messages/read-state
```

Dry-run result:

```text
route_model = PASS
active_mutating_route_count = 0
```

## 3. Scope Dry-run

Effective monitor object:

```json
{
  "monitor_id": 101,
  "principal_id": 3,
  "principal_type": "human_user",
  "asset_kind": "stock",
  "identity_key": "stock:SH:600000",
  "direction": "buy",
  "valid_source_trade_date": "20260612",
  "valid_for_trade_date": "20260615",
  "valid_source_run_id": "condition_layer_20260612_source_20260612_for_20260615_v1",
  "status": "active"
}
```

Matching N6 message:

```json
{
  "principal_id": 3,
  "principal_type": "human_user",
  "asset_kind": "stock",
  "identity_key": "stock:SH:600000",
  "direction": "buy",
  "message_trade_date": "20260615",
  "event_type": "ActionExecuted"
}
```

Expected result:

```text
included = true
reason = effective_monitor_trade_date_match
```

Mismatched date message:

```json
{
  "asset_kind": "stock",
  "identity_key": "stock:SH:600000",
  "direction": "buy",
  "message_trade_date": "20260616"
}
```

Expected result:

```text
included = false
excluded_reason = message_trade_date_mismatch
```

Missing date message:

```json
{
  "asset_kind": "stock",
  "identity_key": "stock:SH:600000",
  "direction": "buy",
  "message_trade_date": null
}
```

Expected result:

```text
included = false
excluded_reason = message_trade_date_missing
```

Expired monitor:

```json
{
  "monitor_id": 102,
  "asset_kind": "stock",
  "identity_key": "stock:SH:600000",
  "direction": "buy",
  "valid_source_trade_date": "20260611",
  "valid_for_trade_date": "20260612",
  "valid_source_run_id": "old_run",
  "status": "active"
}
```

Expected result:

```text
included = false
excluded_reason = monitor_expired
```

## 4. Dashboard Response Dry-run

Example response:

```json
{
  "component": "b_track_monitor_message_dashboard_v2",
  "component_label": "我的监控消息总览",
  "scope_mode": "effective_monitor",
  "principal": {
    "principal_id": 3,
    "principal_type": "human_user",
    "user_id": 3
  },
  "current_filter_batch": {
    "source_trade_date": "20260612",
    "for_trade_date": "20260615",
    "source_run_id": "condition_layer_20260612_source_20260612_for_20260615_v1",
    "status": "ready"
  },
  "summary": {
    "effective_monitor_count": 12,
    "expired_monitor_count": 4,
    "matched_signal_count": 3,
    "action_executed_count": 1,
    "action_blocked_count": 1,
    "action_eligible_count": 0,
    "action_skipped_count": 0,
    "pending_market_data_count": 1,
    "state_changed_count": 0,
    "excluded_message_count": 2
  },
  "event_counts": {
    "ActionExecuted": 1,
    "ActionBlocked": 1,
    "TriggerPendingMarketData": 1
  },
  "asset_kind_counts": {
    "stock": 2,
    "board": 1,
    "index": 0
  },
  "direction_counts": {
    "buy": 3,
    "sell": 0
  },
  "excluded_reason_counts": {
    "message_trade_date_missing": 1,
    "message_trade_date_mismatch": 1,
    "monitor_expired": 4
  },
  "projection_status": {
    "latest_status": "passed",
    "status_reason": "projection_covers_for_trade_date"
  },
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

Dry-run result:

```text
schema_shape = PASS
scope_metadata = PASS
```

## 5. Empty State Dry-run

No effective monitor:

```text
effective_monitor_count = 0
empty_state = 当前没有有效监控对象，请先从筛选中心加入监控
```

Effective monitors but no matched N6 message:

```text
effective_monitor_count > 0
matched_signal_count = 0
empty_state = 当前有效监控对象暂无 N6 用户消息
```

Projection not covering current for_trade_date:

```text
projection_status.status_reason = projection_not_covering_for_trade_date
empty_state = 等待 N6 projection 生成用户消息
```

Current filter batch not ready:

```text
current_filter_batch.status = not_ready
empty_state = 当前筛选批次尚未准备完成
```

## 6. Projection Status Dry-run

Projection covers current for_trade_date:

```json
{
  "latest_user_projection_run_id": 9001,
  "latest_status": "passed",
  "latest_projection_trade_date": "20260615",
  "expected_for_trade_date": "20260615",
  "input_count": 128,
  "projection_count": 128,
  "card_count": 128,
  "error_count": 0,
  "status_reason": "projection_covers_for_trade_date"
}
```

Projection not covering current for_trade_date:

```json
{
  "latest_user_projection_run_id": 8999,
  "latest_status": "passed",
  "latest_projection_trade_date": "20260612",
  "expected_for_trade_date": "20260615",
  "input_count": 0,
  "projection_count": 0,
  "card_count": 0,
  "error_count": 0,
  "status_reason": "projection_not_covering_for_trade_date"
}
```

## 7. Source Boundary Dry-run

Allowed read proof:

```text
user_signal_projection = allowed
user_signal_card = allowed
user_projection_run = allowed
user_monitor_stock = allowed
user_monitor_index = allowed
user_monitor_board = allowed
v_n6_stock_condition_display_basis = allowed
v_n6_index_condition_display_basis = allowed
v_n6_board_condition_display_basis = allowed
```

Forbidden source proof:

```text
common_event_outbox = forbidden
condition_basis = forbidden
condition_pool = forbidden
minute_target_scope = forbidden
raw K = forbidden
direct live market = forbidden
N4/N5 raw facts bypass = forbidden
unreviewed outbox = forbidden
```

Out of MVP proof:

```text
user_notification_queue = not read in MVP
```

## 8. Forbidden Scope Proof

Dry-run side effects:

```text
database_write = false
outbox_consume_or_update = false
worker_started = false
projection_run_started = false
proposal_created = false
order_created = false
trade_created = false
position_or_pnl_updated = false
real_trade_submitted = false
```

## 9. Validation Plan

Contract validation:

```text
JSON parse
schema assertion
GET-only route model assertion
principal scope assertion
allowlist assertion
forbidden source assertion
forbidden wording scan
git diff --check
```

Implementation gate validation target:

```text
targeted tests for dashboard metadata
targeted tests for groups response
targeted tests for projection status
targeted tests for empty states
static scan no N5 outbox source
static scan no mutating message-dashboard route
```

## 10. Next Gate

```text
B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_IMPLEMENTATION_GATE
```
