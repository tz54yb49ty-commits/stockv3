# N3 C1 Today Minute 20260608 Until 15:00 Post Review

Result: `POST_REVIEW_PASS`

- today_minute_run_id: `today_minute_bar_1m_20260608_until_1500__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- latest_closed_minute: `2026-06-08T15:00:00+08:00`
- rows stock/index/board/total: `84720/1440/3120/89280`
- objects stock/index/board/total: `353/6/13/372`
- duplicate minute key groups stock/index/board: `0/0/0`
- P0/P1/P2: `0/0/0`
- event outbox rows written: `0`
- outbox/inbox/checkpoint refs: `0/0/0`
- downstream refs realtime_projection/N4/N5/N6: `0/0/0/0`

Rollback SQL: `sql/N3_C1_today_minute_bar_1m_20260608_until_1500_rollback.sql`

Decision: allow `N3_B2_REALTIME_PROJECTION_20260608_UNTIL_1500_READINESS_GATE`.
