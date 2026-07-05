# B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_IMPLEMENTATION

result: IMPLEMENTATION_PASS

## Scope

Implemented B track V2 readonly "我的监控消息总览" for principal-scoped effective monitor messages.

New page:

- `/n6/app/messages`

New GET-only APIs:

- `GET /api/n6/app/v2/message-dashboard`
- `GET /api/n6/app/v2/message-dashboard/groups`
- `GET /api/n6/app/v2/message-dashboard/projection-status`

## Effective Monitor Boundary

The dashboard reuses the existing B track effective monitor scoped signal path:

- `user_monitor_stock`
- `user_monitor_index`
- `user_monitor_board`
- `user_signal_projection`
- `user_signal_card`
- `user_projection_run`
- `v_n6_stock_condition_display_basis`
- `v_n6_index_condition_display_basis`
- `v_n6_board_condition_display_basis`

Messages remain principal scoped and require effective monitor alignment by `asset_kind`, `identity_key`, `direction`, and monitor `valid_for_trade_date`.

## UI Summary

The page shows:

- safety banner: `只读模式 · 不下单 · 不更新持仓 · 不构成投资建议 · principal scoped`
- current effective monitor trade date
- source trade date
- effective / expired monitor counts
- message counts for confirmed, blocked, eligible, skipped, pending market data, state changes, and excluded messages
- projection status
- message groups
- message preview cards with detail entry
- contract empty states

## Forbidden Scope

This implementation does not add database writes, notification queue reads, worker starts, proposal/order/trade generation, position/PnL updates, real trade submission, or A-track API reuse.

It does not read:

- `common_event_outbox`
- `condition_basis`
- `condition_pool`
- `minute_target_scope`
- raw K
- direct live market
- N4/N5 raw facts bypass
- `user_notification_queue`

## Validation

- `python3 -m unittest tests.test_n6_user_app` PASS, 122 tests
- `python3 -m compileall src tests scripts` PASS
- JSON parse PASS for contract, dry-run, and implementation artifacts
- `git diff --check` PASS
- New message dashboard route/mutation scan PASS
- New principal scope test PASS
- Dashboard metadata test PASS
- Groups response test PASS
- Projection status test PASS
- Empty state/page render test PASS
