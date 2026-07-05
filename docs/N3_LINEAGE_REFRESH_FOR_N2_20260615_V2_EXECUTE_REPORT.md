# N3 Lineage Refresh For N2 20260615 V2 Execute Report

Result: `EXECUTE_PASS`

## Stage 1 Proof

- command_exit_code: `0`
- report: `docs/N3_6_market_data_subscription_execute_report.json`
- run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2`
- run_status: `passed`
- candidate/subscription/pull_plan: `5924/3272/9`
- subscription_objects: `2032`
- market_data_fact_rows_written: `0`
- event_outbox_rows_written: `0`
- P0/P1/P2: `0/0/0`

## Stage 2 Proof

- command_exit_code: `0`
- report: `docs/N3_A1_previous_day_minute_preload_execute_report.json`
- run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2`
- run_status: `passed`
- objects stock/index/board/total: `550/17/53/620`
- minute rows stock/index/board/total: `132000/4080/12720/148800`
- status rows stock/index/board/total: `550/17/53/620`
- event_outbox_rows_written: `0`
- P0/P1/P2: `0/1/0`

## Boundary Proof

- scoped outbox/inbox/checkpoint refs: `0/0/0`
- N4/N5/N6 refs: `0/0/0`
- N3-B/C/B2 executed: `false`
- worker_started: `false`
- voice/mobile/sim/position/order/real_trade touched: `false`
- old_system_touched: `false`

## Old V1 Preservation

- old subscription run passed rows: `1`
- old preload run passed rows: `1`
- old subscription candidate rows: `5966`
- old preload minute rows stock/index/board: `135360/4080/12720`

## Rollback Registry

- rollback_sql_path: `sql/N3_lineage_refresh_for_N2_20260615_v2_rollback.sql`
- rollback_not_executed: `true`
- scope: `new v2 subscription/preload rows only`
- preserves_old_v1_lineage: `true`
- no DROP/TRUNCATE/CASCADE: `true`

## Next Gate

`N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_POST_REVIEW_GATE`
