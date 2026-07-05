# N3-C2 Closed 30m Replay Execute Report

- result: `EXECUTED`
- c2_run_id: `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- minute_delta_rows: `107333`
- summary_rows: `17504`
- summary_status: `{'closed': 17432, 'partial': 0, 'missing': 72, 'failed': 0}`
- quality P0/P1/P2: `0/1/0`
- outbox_rows_for_c2_run: `0`
- rollback_sql_path: `sql/N3_C2_closed_30m_business_rollback.sql`

Boundary: no common_event_outbox write, no inbox/checkpoint consumption, no N4/N5/N6, no worker.