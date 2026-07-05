# B_TRACK_V2_MONITOR_SCOPED_SIGNALS_CLOSEOUT

Status: `CLOSEOUT_PASS`

Layer role: `runtime_control`

Date: `2026-06-14`

Scope: B轨 V2 “有效监控对象消息展示”完成登记。本 gate 只登记 closeout artifacts，不写数据库、不启动服务、不消费 outbox、不生成交易/持仓/PnL。

## 1. Closeout Summary

```text
implementation_status = IMPLEMENTATION_PASS
post_review_status = POST_REVIEW_PASS
closeout_status = CLOSEOUT_PASS
completion_marker = B_TRACK_V2_MONITOR_SCOPED_SIGNALS_COMPLETE
```

已完成能力：

```text
Signals 页面/API 显示“我的监控消息”。
Signals 列表只返回当前 principal 的有效监控对象消息。
Signals 详情页复用同一 scope，非 scope 消息返回 404。
Watchlist 复用 fetch_app_signals，已同步收口。
Status Monitor 复用 fetch_app_signals，已同步收口。
API 返回 scope metadata，用于解释有效监控数量、失效监控数量、匹配消息数量和排除原因。
```

## 2. Canonical Scope

有效监控对象：

```text
effective_monitor_scope =
  user_monitor_stock
  union user_monitor_index
  union user_monitor_board
```

有效批次规则：

```text
monitor.status = active
monitor.valid_source_trade_date = current_filter_batch.source_trade_date
monitor.valid_for_trade_date = current_filter_batch.for_trade_date
monitor.valid_source_run_id = current_filter_batch.source_run_id
```

消息匹配规则：

```text
message.principal = current principal
message.asset_kind = monitor.asset_kind
message.identity_key = monitor.identity_key
message.direction = monitor.direction
message.trade_date = monitor.valid_for_trade_date
```

消息日期规则：

```text
source_trade_date = 筛选条件来源日
for_trade_date = 监控对象生效交易日
N5/N6 message trade_date = for_trade_date
```

缺少 `trade_date` 的消息：

```text
excluded_reason = message_trade_date_missing
effective_monitor_message = false
```

## 3. API Closeout

GET-only routes retained:

```text
GET /api/n6/app/v1/signals
GET /api/n6/app/v1/signals/{user_signal_projection_id}
GET /api/n6/app/v1/watchlist
GET /api/n6/app/v1/status-monitor
```

Signals metadata:

```json
{
  "scope_mode": "effective_monitor",
  "current_filter_batch": {},
  "effective_monitor_count": 0,
  "expired_monitor_count": 0,
  "matched_signal_count": 0,
  "excluded_reason_counts": {
    "message_trade_date_missing": 0,
    "message_trade_date_mismatch": 0,
    "monitor_expired": 0
  }
}
```

Route scan proof:

```text
/api/n6/app/v1/watchlist = GET
/api/n6/app/v1/signals = GET
/api/n6/app/v1/signals/{user_signal_projection_id} = GET
/api/n6/app/v1/status-monitor = GET
```

## 4. UI Closeout

Signals 用户文案：

```text
我的监控消息
```

Empty states:

```text
当前没有有效监控对象，请先从筛选中心加入监控
当前有效监控对象暂无 N6 用户消息
存在消息缺少 trade_date，已从有效监控消息中排除
```

安全边界文案保持：

```text
只读模式
不下单
不构成投资建议
principal scoped
```

## 5. Source Boundary Closeout

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

Forbidden reads:

```text
common_event_outbox
condition_basis
condition_pool
minute_target_scope
stock_condition_pool
index_condition_pool
board_condition_pool
stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
raw K
direct live market
N4 raw bypass
N5 raw bypass
v_n6_index_membership_fact
v_n6_board_membership_fact
```

说明：

```text
筛选中心仍可使用 membership views 展示“查看关联个股”。
Signals 消息 scope 不使用 membership views，避免把关系桥误当作消息过滤事实。
```

## 6. Validation Closeout

Verified commands:

```bash
PYTHONPATH=src python3 -m unittest tests.test_n6_user_app

PYTHONPATH=src python3 -m compileall \
  src/ashare_v3/web/n6_user_app.py \
  src/ashare_v3/web/n6_app_v1.py \
  tests/test_n6_user_app.py

git diff --check -- \
  src/ashare_v3/web/n6_user_app.py \
  src/ashare_v3/web/n6_app_v1.py \
  tests/test_n6_user_app.py \
  docs/B_TRACK_V2_MONITOR_SCOPED_SIGNALS_POST_REVIEW.md \
  docs/B_TRACK_V2_MONITOR_SCOPED_SIGNALS_POST_REVIEW.json \
  docs/B_TRACK_V2_MONITOR_SCOPED_SIGNALS_CLOSEOUT.md \
  docs/B_TRACK_V2_MONITOR_SCOPED_SIGNALS_CLOSEOUT.json
```

Current proof:

```text
test_n6_user_app = 118 tests OK
compileall = PASS
git_diff_check = PASS
json_parse = PASS
source_boundary_scan = PASS
route_scan = PASS
forbidden_wording_scan = PASS
whitespace_scan = PASS
```

## 7. Forbidden Scope Closeout

No side effects:

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

## 8. Completion Marker

```text
B_TRACK_V2_MONITOR_SCOPED_SIGNALS_COMPLETE = true
```

Recommended next product gate:

```text
B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_PRODUCT_DESIGN_GATE
```

目标：在当前有效监控消息 scope 已固化后，设计“我的监控消息总览 / 未读状态 / 消息分组 / 投影运行状态提示”，仍只读、principal scoped、N6 projection-only。

