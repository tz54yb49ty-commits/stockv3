# N3 C1 20260603 Full-Context Scope Expansion Dry-Run / Preflight

- result: BLOCKED
- layer_role: N3_market_data
- generated_at: 2026-06-03T20:37:44.660986+08:00
- source_condition_run_id: `condition_layer_20260602_source_20260602_v1`
- subscription_run_id: `market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- current_c1_run_id: `today_minute_bar_1m_20260603_until_1500__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- proposed_expansion_run_id: `today_minute_bar_1m_20260603_until_1500_full_context_expansion__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`

## Current Coverage

- context rows: 5222
- complete lineage rows: 831
- missing source minute rows: 4391
- current C1 objects: stock=241 index=2 board=34 total=277

## Expansion Scope

- new objects: stock=1722 index=81 board=394 total=2197
- estimated new minute rows: stock=413280 index=19440 board=94560 total=527280
- expected full-context C1 rows after expansion: stock=471120 index=19920 board=102720 total=593760

## Source Adapter Readiness

- adapter routes: stock=StockMarketDataAdapter/bars, index=IndexMarketDataAdapter/index_bars, board=BoardMarketDataAdapter/index_bars
- persisted minute subscription coverage for expansion objects: stock=0 index=0 board=0
- execute runner readiness: blocked

## Quality

- P0/P1/P2: 2/1/0
- P0 blocker: `n3_c1_full_context_expansion_minute_subscription_coverage` when persisted minute subscription rows do not cover expansion objects.
- P0 blocker: `n3_c1_full_context_expansion_execute_runner_readiness` because the current C1 runner enforces persisted subscription counts matching the C0 plan.

## Rollback

- rollback_sql: `sql/N3_C1_full_context_scope_expansion_20260603_rollback.sql`
- hard_fail_before_delete: true
- deletes only C1 expansion minute/status-quality/run scope.
- does not touch current C1, subscription, B1, A1, projection, outbox/inbox/checkpoint, N4/N5/N6.

## Boundary

No database writes, no market-data pull, no outbox/inbox/checkpoint writes, no N4/N5/N6, no worker.
