# B_TRACK_V2_MONITOR_SCOPED_SIGNALS_POST_REVIEW

Status: `POST_REVIEW_PASS`

Layer role: `runtime_control`

Date: `2026-06-14`

Scope: B轨 V2 “有效监控对象消息展示”实现复核。本 gate 不写数据库、不消费 outbox、不启动 worker、不生成交易/持仓/PnL，仅复核 B轨 Signals / Watchlist / Status Monitor 是否按当前有效监控对象和 `for_trade_date` 收口。

## 1. Review Summary

```text
implementation_gate = B_TRACK_V2_MONITOR_SCOPED_SIGNALS_IMPLEMENTATION
post_review_status = POST_REVIEW_PASS
scope_mode = effective_monitor
message_source_boundary = N6 projection/card/run only
route_scan = PASS
source_boundary_scan = PASS
forbidden_wording_scan = PASS
targeted_tests = PASS
```

结论：

```text
B轨消息列表已从“全量 N6 用户消息”收口为“当前 principal 的有效监控对象消息”。
消息必须满足 asset_kind / identity_key / direction / valid_for_trade_date 同时匹配。
详情接口复用同一 scope，非当前有效监控范围的消息返回 404。
Watchlist / Status Monitor 复用 fetch_app_signals，因此同步收口。
```

## 2. Scope Rule Proof

有效监控对象 scope：

```text
effective_monitor_scope =
  user_monitor_stock
  union user_monitor_index
  union user_monitor_board
  joined with current_filter_batch
```

有效性判断：

```text
status = active
valid_source_trade_date = current_filter_batch.source_trade_date
valid_for_trade_date = current_filter_batch.for_trade_date
valid_source_run_id = current_filter_batch.source_run_id
```

消息匹配：

```text
message.asset_kind = monitor.asset_kind
message.identity_key = monitor.identity_key
message.direction = monitor.direction
message.trade_date = monitor.valid_for_trade_date
```

消息 trade_date 解析优先级：

```text
p.display_payload_json->>'trade_date'
p.source_payload_json->>'trade_date'
c.card_payload_json->>'trade_date'
p.trace_json->>'trade_date'
```

缺少 trade_date 的消息：

```text
excluded_reason = message_trade_date_missing
included_in_effective_monitor_signals = false
```

## 3. API Proof

保留 GET-only routes：

```text
GET /api/n6/app/v1/signals
GET /api/n6/app/v1/signals/{user_signal_projection_id}
GET /api/n6/app/v1/watchlist
GET /api/n6/app/v1/status-monitor
```

Route scan result：

```text
/api/n6/app/v1/watchlist = GET
/api/n6/app/v1/signals = GET
/api/n6/app/v1/signals/{user_signal_projection_id} = GET
/api/n6/app/v1/status-monitor = GET
```

Signals response metadata：

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

详情页 scope：

```text
in_scope signal detail -> 200
out_of_scope signal detail -> 404
```

## 4. UI Proof

Signals 用户层命名：

```text
component_label = 我的监控消息
```

空状态：

```text
无有效监控对象 -> 当前没有有效监控对象，请先从筛选中心加入监控
有监控但无消息 -> 当前有效监控对象暂无 N6 用户消息
消息日期缺失 -> 存在消息缺少 trade_date，已从有效监控消息中排除
```

安全文案保持：

```text
只读模式
不下单
不构成投资建议
principal scoped
```

## 5. Allowed Source Proof

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

## 6. Forbidden Source Proof

静态扫描确认 effective monitor scoped signals 路径未读取：

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
membership views 仍可用于筛选中心“查看关联个股”和监控对象来源解释。
Signals scope 不直接依赖 membership views，避免把关系桥误当消息过滤来源。
```

## 7. Validation Summary

Commands executed:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_n6_user_app.N6UserAppTest.test_b_track_signals_are_scoped_to_effective_monitor_and_for_trade_date \
  tests.test_n6_user_app.N6UserAppTest.test_b_track_postgres_signals_adapter_uses_effective_monitor_scope_and_for_trade_date \
  tests.test_n6_user_app.N6UserAppTest.test_b_track_watchlist_api_is_readonly_projection_from_reviewed_signals \
  tests.test_n6_user_app.N6UserAppTest.test_b_track_status_monitor_api_is_readonly_from_reviewed_signals

PYTHONPATH=src python3 -m unittest tests.test_n6_user_app

PYTHONPATH=src python3 -m compileall \
  src/ashare_v3/web/n6_user_app.py \
  src/ashare_v3/web/n6_app_v1.py \
  tests/test_n6_user_app.py

git diff --check -- \
  src/ashare_v3/web/n6_user_app.py \
  src/ashare_v3/web/n6_app_v1.py \
  tests/test_n6_user_app.py
```

Observed:

```text
targeted_tests = 4 tests OK
full_test_n6_user_app = 118 tests OK
compileall = PASS
git_diff_check = PASS for tracked diff
source_boundary_scan = PASS
forbidden_wording_scan = PASS
whitespace_scan = PASS
```

## 8. Forbidden Scope Proof

No execution or write performed:

```text
database_write = false
outbox_consume_or_update = false
worker_started = false
proposal_created = false
order_created = false
trade_created = false
position_or_pnl_updated = false
real_trade_submitted = false
```

## 9. Next Gate Recommendation

```text
B_TRACK_V2_MONITOR_SCOPED_SIGNALS_CLOSEOUT_GATE
```

