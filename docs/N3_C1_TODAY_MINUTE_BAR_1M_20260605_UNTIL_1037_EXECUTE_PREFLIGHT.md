# N3-C1 Today Minute 20260605 Until 10:37 Execute Preflight

- result: PREFLIGHT_PASS
- blocked: false
- P0/P1/P2: 0/0/0
- scoped baseline stock/index/board minute rows: 0/0/0
- run/quality baseline: 0/0
- scoped outbox/inbox/checkpoint refs: 0/0/0
- rollback_sql: `sql/N3_C1_today_minute_bar_1m_20260605_until_1037_rollback.sql`
- writes_outbox: false
- downstream_layers_touched: false
- worker_started: false
## Rollback Guard Hardening

- result: FIX_PASS
- added guards: common_trigger_state
- hard-fail before first DELETE: true
- delete scope unchanged: minute/quality/run rows only
