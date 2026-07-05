# N3 Lineage Refresh For N2 20260615 V2 Post Review

Result: `POST_REVIEW_PASS`

## Stage 1 Proof

- run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2`
- command_exit_code: `0`
- run_status: `passed`
- candidate/subscription/pull_plan: `5924/3272/9`
- subscription_objects: `2032`
- market facts written: `0`
- outbox rows written: `0`
- P0/P1/P2: `0/0/0`

## Stage 2 Proof

- run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2`
- command_exit_code: `0`
- run_status: `passed`
- objects stock/index/board/total: `550/17/53/620`
- minute rows stock/index/board/total: `132000/4080/12720/148800`
- preload status rows stock/index/board/total: `550/17/53/620`
- outbox rows written: `0`
- P0/P1/P2: `0/1/0`

## Old V1 Lineage Preservation

- old subscription run passed rows: `1`
- old preload run passed rows: `1`
- old subscription candidate rows: `5966`
- old preload minute rows stock/index/board: `135360/4080/12720`

## Boundary Proof

- scoped outbox/inbox/checkpoint refs: `0/0/0`
- N4/N5/N6 refs: `0/0/0`
- N3-B/C/B2 executed: `false`
- worker_started: `false`
- rollback_executed: `false`
- voice/mobile/sim/position/order/real_trade touched: `false`
- old_system_touched: `false`

## Rollback Proof

- rollback_sql_path: `sql/N3_lineage_refresh_for_N2_20260615_v2_rollback.sql`
- hard_fail_before_delete_update: `true`
- scoped_to_new_v2_runs: `true`
- preserves_old_v1_lineage: `true`
- no DROP/TRUNCATE/CASCADE: `true`

## Decision

- can_mark_complete: `true`
- recommended_next_gate: `N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_CLOSEOUT_OR_DOWNSTREAM_READINESS_GATE`
