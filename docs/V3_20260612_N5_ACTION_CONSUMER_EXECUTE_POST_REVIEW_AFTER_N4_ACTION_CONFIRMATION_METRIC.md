# V3 20260612 N5 Action Consumer Execute Post Review

- result: `POST_REVIEW_PASS`
- for_trade_date: `20260612`
- N3 metric rows stock/index/board: `62/0/38`
- N3 signal distribution: `{'B_BUY': 76, 'S_SELL': 24}`
- N4 outbox: `[{'event_type': 'TriggerMatched', 'status': 'pending', 'count': 49}, {'event_type': 'TriggerPendingMarketData', 'status': 'pending', 'count': 4405}]`
- N4 trigger state counts: `{'trigger_live_true': 49, 'pending_market_data': 4405}`
- N5 action run: `('passed', 0, 0, 0, 4454, 43, 43)`
- N5 facts stock/index/board: `33/0/10`
- N5 action events: `{'ActionExecuted': 43}`
- N5 scoped inbox/checkpoint: `{'inbox': 4454, 'partitions': 2082, 'checkpoint': 2082}`
- N4 outbox status unchanged: `{'pending': 4454, 'delivered': 0, 'delivering': 0}`
- N5 payload checks: `{'missing_trigger_price': 0, 'ordinary_trigger_period_30m_violations': 0}`
- downstream refs: `[{'table': 'user_projection_run', 'refs': 0}, {'table': 'user_signal_projection', 'refs': 0}, {'table': 'user_signal_decision', 'refs': 0}, {'table': 'user_notification_queue', 'refs': 0}, {'table': 'user_sim_order', 'refs': 0}, {'table': 'user_sim_trade', 'refs': 0}, {'table': 'user_sim_position', 'refs': 0}, {'table': 'common_position_state', 'refs': 0}, {'table': 'common_position_event', 'refs': 0}]`

## Rollback Registry

- N3 writer: `sql/V3_20260612_realtime_virtual_metric_writer_runner_rollback.sql`
- N4: `sql/V3_20260612_n4_action_confirmation_metric_business_execute_after_n3_writer_rollback.sql`
- N5: `sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql`

## Boundary

- N6/user projection: not touched
- voice/mobile/sim/real trade: not touched
- worker/scheduler: not started by this closeout
