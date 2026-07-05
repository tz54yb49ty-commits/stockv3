# N3-C1 20260602 Until 10:50 Execute Final Gate

```text
status = PASS_WAIT_USER_CONFIRMATION
today_minute_run_id = today_minute_bar_1m_20260602_until_1050__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
latest_closed_minute = 2026-06-02T10:50:00+08:00
expected objects stock/index/board = 765 / 54 / 150
expected rows stock/index/board/total = 61200 / 4320 / 12000 / 77520
P0/P1/P2 = 0 / 0 / 0
blocked_reasons = []
execute_authorized = false
will_modify_production_data = true
```

Allowed writes: common_market_data_run, common_market_data_quality_item, stock/index/board_minute_bar_1m.

Forbidden: outbox/inbox/checkpoint, B2 projection, N4/N5/N6, worker, old system, real trading.
