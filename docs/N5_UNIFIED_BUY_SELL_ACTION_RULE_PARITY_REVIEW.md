# N5 Unified Buy/Sell Action Rule Parity Review

- classification: `NOT_ACCEPTED_AS_FINAL_ACTION_RESULT`
- blocker: `unified_buy_sell_action_rule_and_metric_time_alignment_not_proven`
- generated_at: `2026-06-09T03:10:40.239904+00:00`

## Old Excel Reference

- file: `/Users/chuanfuchen/Desktop/普通买卖动作_20260608.xlsx`
- detail rows: `734`
- unique code+direction+condition: `164`
- signal types: `{'B_BUY': 207, 'S_SELL': 527}`
- trigger periods: `{'D': 466, 'M': 96, 'W': 135, 'Y': 37}`
- actual flag distribution: `{'1': 734}`
- hint flag distribution: `{'0': 734}`
- detail primary periods: `{}`

## V3 N4 Evidence

- run_id: `trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry`
- ordinary pending with `trigger_period=30m`, `primary_trigger_period=null`, `all_trigger_periods=[]`: `3770`

### N4 TriggerMatched Distribution

|asset_kind|condition_key|signal_type|trigger_period|trigger_mark_candidate|row_count|
|---|---|---|---|---|---|
|board|SELL_HINT|S_SELL|30m|30m_shrink|3|
|index|BUY_HINT|B_BUY|30m|30m_volume|6|
|stock|BUY_HINT|B_BUY|30m|30m_volume|110|
|stock|SELL_HINT|S_SELL|30m|30m_shrink|3|

## V3 N5 Evidence

### N5 Action Event Distribution

|asset_kind|event_type|action_state|confirmation_status|blocked_reason|condition_key|signal_type|trigger_period|trigger_mark_candidate|action_mark|row_count|
|---|---|---|---|---|---|---|---|---|---|---|
|board|ActionBlocked|blocked|failed|price_confirmation_failed|SELL_HINT|S_SELL|30m|30m_shrink||3|
|index|ActionBlocked|blocked|failed|price_confirmation_failed|BUY_HINT|B_BUY|30m|30m_volume||6|
|stock|ActionBlocked|blocked|failed|price_confirmation_failed|BUY_HINT|B_BUY|30m|30m_volume||110|
|stock|ActionBlocked|blocked|failed|price_confirmation_failed|SELL_HINT|S_SELL|30m|30m_shrink||3|

## N3 Metric Alignment Evidence

- metric rows: `122`
- metric minute labels: `{'15:00': 122}`

### Object-Level Join Time Mismatch Samples

|asset_kind|condition_key|signal_type|trigger_time|metric_time|metric_minute_label|row_count|
|---|---|---|---|---|---|---|
|stock|BUY_HINT|B_BUY|2026-06-08T09:44:00+08:00|2026-06-08T15:00:00+08:00|15:00|79|
|stock|BUY_HINT|B_BUY|2026-06-08T09:43:00+08:00|2026-06-08T15:00:00+08:00|15:00|21|
|stock|BUY_HINT|B_BUY|2026-06-08T09:45:00+08:00|2026-06-08T15:00:00+08:00|15:00|10|
|stock|SELL_HINT|S_SELL|2026-06-08T09:44:00+08:00|2026-06-08T15:00:00+08:00|15:00|2|
|stock|SELL_HINT|S_SELL|2026-06-08T09:43:00+08:00|2026-06-08T15:00:00+08:00|15:00|1|
|index|BUY_HINT|B_BUY|2026-06-08T09:43:00+08:00|2026-06-08T15:00:00+08:00|15:00|6|
|board|SELL_HINT|S_SELL|2026-06-08T14:59:00+08:00|2026-06-08T15:00:00+08:00|15:00|3|

## Root Cause Classification

- RC1 N4 ordinary formal trigger path missing/bypassed: `PROVEN`
- RC2 N5 direct HINT special-case: `NOT_PROVEN`; current issue is upstream N4 matched-input starvation, while N5 still needs trigger-time metric guard.
- RC3 N3/N5 metric join object-level, not trigger-time aligned: `PROVEN`

## Forbidden Scope Proof

- old Excel read-only: `true`
- old monitor.db read: `false`
- old services touched: `false`
- long worker started: `false`
- delivery/push/voice/mobile executed: `false`
- sim/order/trade/position/PnL executed: `false`
- real trade executed: `false`
- scoped forbidden DB counts: `{'n5_position_events_for_run': 0, 'n6_notification_queue_for_projection_run': 0, 'n6_sim_orders_for_projection_run': 0, 'n6_sim_trades_for_projection_run': 0, 'n6_sim_positions_for_projection_run': 0}`

## Required Next Step

Write failing regression tests, then repair N4 formal ordinary semantics and N5 trigger-row/time-aligned metric confirmation before any rerun can be accepted.
