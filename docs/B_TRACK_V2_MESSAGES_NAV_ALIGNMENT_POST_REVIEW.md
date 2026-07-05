# B Track V2 Messages Navigation Alignment Post Review

## Result

`POST_REVIEW_PASS`

This runtime_control post-review verifies that the B Track V2 signal/message navigation alignment implementation matches the approved contract and dry-run. This gate is read-only except for this post-review artifact. It does not authorize database writes, worker execution, projection runs, outbox consumption, N6 delivery, proposals, orders, trades, positions, PnL, or real trading.

## Reviewed Inputs

- `docs/B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_CONTRACT.md`
- `docs/B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_CONTRACT.json`
- `docs/B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_DRY_RUN.md`
- `docs/B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_DRY_RUN.json`
- `docs/B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_IMPLEMENTATION.md`
- `docs/B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_IMPLEMENTATION.json`
- `src/ashare_v3/web/n6_app_v1.py`
- `src/ashare_v3/web/n6_user_app.py`
- `src/ashare_v3/web/templates/n6_app_shell.html`
- `tests/test_n6_user_app.py`

## Navigation Proof

Current user-visible navigation labels are aligned:

- `/n6/app/messages`: `消息总览`
- `/n6/app/signals`: `消息列表`
- `/n6/app/my-monitor`: `监控对象`
- `/n6/app/status-monitor`: `状态监控`

The implementation keeps `signals` as a compatibility route/API term while removing it as the ordinary user-facing navigation concept.

## Page Title Proof

Current page titles are aligned:

- `/n6/app/messages`: `我的监控消息总览`
- `/n6/app/signals`: `我的监控消息列表`
- `/n6/app/my-monitor`: `我的监控对象`
- `/n6/app/status-monitor`: `状态监控`

The signal-detail component label is now user-facing as `消息详情`.

## Dashboard Wording Proof

The dashboard message summary wording is aligned:

- `我的监控消息`
- `查看消息总览`
- `查看消息列表`

The dashboard links remain route-compatible:

- `查看消息总览` -> `/n6/app/messages`
- `查看消息列表` -> `/n6/app/signals`

## Route Compatibility Proof

The route paths are preserved:

- `/n6/app/messages`
- `/n6/app/signals`
- `/n6/app/my-monitor`
- `/n6/app/status-monitor`

The app uses dynamic page routes for these N6 app pages, and each reviewed page returned HTTP 200 in the verification scan.

## API Compatibility Proof

The reviewed API paths are preserved and GET-only:

- `GET /api/n6/app/v1/signals`
- `GET /api/n6/app/v1/signals/{user_signal_projection_id}`
- `GET /api/n6/app/v2/message-dashboard`
- `GET /api/n6/app/v2/message-dashboard/groups`
- `GET /api/n6/app/v2/message-dashboard/projection-status`

POST/PATCH/DELETE against `/api/n6/app/v2/message-dashboard` continue to return 404 or 405.

## Internal Field Unchanged Proof

The reviewed API payload still exposes the expected internal/API fields:

- `signal_type`
- `user_signal_projection_id`
- `user_signal_card_id`
- `user_projection_run_id`
- `action_state`
- `action_mark`
- `event_type`
- `projection_run_id`
- `source_run_id`
- `identity_key`
- `condition_key`
- `principal_id`
- `principal_type`

No database schema, internal enum, canonical runtime field, event type, action state, trigger state, or route path change is registered by this post-review.

## Scope Unchanged Proof

The message dashboard payload remains:

- `scope_mode=effective_monitor`
- principal scoped
- effective-monitor scoped
- N6 projection/card/run only
- current filter batch based on reviewed display-basis views
- `message.trade_date = monitor.valid_for_trade_date`

The implementation report explicitly records:

- `effective_monitor_scope_changed=false`
- `message_query_logic_changed=false`
- `db_fields_changed=false`
- `internal_enums_changed=false`
- `n4_n5_n6_facts_changed=false`

## Forbidden Source Proof

The relevant message-dashboard, message-group, projection-status, and app signal repository paths were scanned. No new read was introduced from:

- `common_event_outbox`
- `condition_basis`
- `condition_pool`
- `minute_target_scope`
- raw K
- direct live market
- N4/N5 raw facts bypass
- `user_notification_queue`

The dashboard source policy also reports these sources as not read.

## Forbidden Scope Proof

This post-review did not:

- modify code
- write database business facts
- consume or update outbox/inbox/checkpoint
- start a worker or scheduler
- start a projection run
- generate proposal/order/trade
- update position/PnL
- submit real trade
- enter voice/mobile/sim/position/order/trade paths

## Validation Summary

Fresh validation commands passed:

- Existing JSON parse for contract/dry-run/implementation artifacts: PASS
- UI wording scan: PASS
- route/API compatibility scan: PASS
- internal field unchanged assertion: PASS
- scope unchanged assertion: PASS
- forbidden source scan: PASS
- forbidden wording scan: PASS
- `PYTHONPATH=src:scripts python3 -m unittest tests.test_n6_user_app`: PASS, 126 tests OK
- `python3 -m compileall src/ashare_v3/web tests/test_n6_user_app.py`: PASS
- `git diff --check`: PASS

## Decision

`POST_REVIEW_PASS`

This implementation is ready for closeout registration.

Allowed next gate:

`B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_CLOSEOUT_GATE`

