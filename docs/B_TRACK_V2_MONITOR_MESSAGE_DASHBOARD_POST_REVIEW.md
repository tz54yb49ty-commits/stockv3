# B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_POST_REVIEW

Result: `POST_REVIEW_PASS`

Layer role: `runtime_control`

This gate only reviewed the B track V2 readonly "我的监控消息总览" implementation. It did not modify code, write database business facts, start a worker, consume/update outbox, trigger a projection run, generate proposal/order/trade, update position/PnL, or submit real trade.

## Route Proof

- `/n6/app/messages` is externally reachable by the app page router `GET /n6/app/{page_key}` with `page_key=messages`.
- Implemented GET APIs:
  - `GET /api/n6/app/v2/message-dashboard`
  - `GET /api/n6/app/v2/message-dashboard/groups`
  - `GET /api/n6/app/v2/message-dashboard/projection-status`
- Route scan confirmed the three message-dashboard API routes are GET-only.
- POST/PATCH/DELETE against `/api/n6/app/v2/message-dashboard` return `404` or `405`; no mutating message-dashboard route is registered.

## API Proof

The dashboard response includes:

- `scope_mode=effective_monitor`
- `current_filter_batch`
- `summary.effective_monitor_count`
- `summary.expired_monitor_count`
- `summary.matched_signal_count`
- `summary.excluded_reason_counts`
- `projection_status`
- `groups`
- `items_preview`
- `source_policy`
- `side_effects`

The groups and projection-status endpoints return `b_track_monitor_message_groups_v2` and `b_track_monitor_projection_status_v2` respectively.

## UI Proof

The page is rendered through `src/ashare_v3/web/templates/n6_app_shell.html` under `page.page_key == "messages"` and contains:

- 我的监控消息总览
- 当前有效监控交易日
- 条件来源日
- 有效监控对象数量
- 今日消息数量
- projection 状态
- 消息分组
- 查看详情
- 只读模式 · 不下单 · 不更新持仓 · 不构成投资建议 · principal scoped

## Effective Monitor Scope Proof

The message dashboard reuses the effective monitor scope and is principal scoped. The reviewed path reads:

- `user_monitor_stock`
- `user_monitor_index`
- `user_monitor_board`
- `user_signal_projection`
- `user_signal_card`
- `user_projection_run`

The match rule requires:

- monitor is active/effective for the current filter batch
- principal scope matches
- `asset_kind` matches
- `identity_key` matches
- `direction` matches
- message `trade_date` equals monitor `valid_for_trade_date`

Current filter batch reads are limited to:

- `v_n6_stock_condition_display_basis`
- `v_n6_index_condition_display_basis`
- `v_n6_board_condition_display_basis`

## Projection-Only Proof

The execution path uses N6 user projection/card/run data. It does not consume N4/N5 raw facts, direct outbox, raw K, or live market data. The code exposes `NULL::bigint AS user_notification_queue_id` only as a compatibility field in the projection select list; it does not read `user_notification_queue`.

## Empty State Proof

Supported empty states:

- 当前没有有效监控对象，请先从筛选中心加入监控
- 当前有效监控对象暂无 N6 用户消息
- 等待 N6 projection 生成用户消息
- 存在消息缺少 trade_date，已从有效监控消息中排除
- 当前筛选批次尚未准备完成

## Forbidden Source Proof

Focused execution-path source scan confirmed no SQL `FROM`/`JOIN` against:

- `common_event_outbox`
- `condition_basis`
- `condition_pool`
- `minute_target_scope`
- raw K tables
- direct live market
- N4/N5 raw facts bypass
- `user_notification_queue`

The source policy intentionally displays these names as forbidden labels; that display text is not a data read.

## Forbidden Scope Proof

- Database business fact write: `false`
- Outbox consume/update: `false`
- Worker started: `false`
- Projection run started: `false`
- Proposal/order/trade generated: `false`
- Position/PnL updated: `false`
- Real trade submitted: `false`

## Validation

- JSON parse: `PASS`
- route scan GET-only: `PASS`
- no mutating message-dashboard route scan: `PASS`
- principal scope test: `PASS`
- dashboard metadata test: `PASS`
- groups response test: `PASS`
- projection status test: `PASS`
- empty state test: `PASS`
- forbidden source scan: `PASS`
- `PYTHONPATH=src:scripts python3 -m unittest tests.test_n6_user_app`: `PASS`, 122 tests OK
- `python3 -m compileall src tests`: `PASS`
- `git diff --check`: `PASS`

## Decision

`POST_REVIEW_PASS`.

Allowed next gate: `B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_CLOSEOUT_GATE`.
