# V3 20260616 N3 B1/C1 Refresh For V4 Lineage Preflight

- result: `BLOCKED`
- P0: `n3_b1_current_date_after_for_trade_date`
- current_date: `20260617`
- for_trade_date: `20260616`
- B1 readiness blocked_reason: `current_date_after_for_trade_date`

## V4 Lineage
- source_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v4`
- subscription_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`

## Planned B1
- snapshot_run_id: `realtime_daily_snapshot_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- expected rows stock/index/board/total: `1822/83/127/2032`
- writes_outbox: `false`
- allowed execute command: `none while readiness is blocked`

## Planned C1
- today_minute_run_id: `today_minute_bar_1m_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- latest_closed_minute: `2026-06-16T14:01:00+08:00`
- expected rows stock/index/board/total: `99550/3077/9593/112220`
- allowed execute command: `none; C1 waits for B1 PASS`

## Rollback
- B1 rollback: `sql/N3_B1_realtime_snapshot_20260616_until_1401_v4_lineage_rollback.sql`
- C1 rollback: `sql/N3_C1_today_minute_bar_1m_20260616_until_1401_v4_lineage_rollback.sql`
- rollback not executed; no DROP/TRUNCATE/CASCADE expected.

## Forbidden Scope
- No metric execute, no N4/N5/N6, no outbox/inbox/checkpoint mutation, no worker, no old system, no trade path.

