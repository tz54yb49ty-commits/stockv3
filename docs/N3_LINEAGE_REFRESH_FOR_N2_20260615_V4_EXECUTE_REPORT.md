# N3 Lineage Refresh For N2 20260615 V4 Execute Report

- result: `EXECUTE_PASS`
- layer_role: `N3_market_data`
- source_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v4`
- subscription_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`

## Stage 1 Proof

- command_exit_code: `0`
- run_status: `passed`
- common_market_data_run: `1`
- common_market_data_quality_item: `34`
- common_market_data_subscription_candidate: `5924`
- common_market_data_subscription: `3272`
- common_market_data_pull_plan: `9`
- subscription_objects: `2032`
- market_facts_written: `0`
- outbox_rows_written: `0`
- P0/P1/P2: `0/0/0`
- pass: `True`

## Stage 2 Proof

- command_exit_code: `0`
- run_status: `passed`
- common_market_data_run: `1`
- common_market_data_quality_item: `12`
- objects stock/index/board/total: `550/17/53/620`
- minute rows stock/index/board/total: `132000/4080/12720/148800`
- preload status rows stock/index/board/total: `550/17/53/620`
- outbox_rows_written: `0`
- P0/P1/P2: `0/1/0`
- pass: `True`

## Prior Lineage Preservation

- v2 subscription run passed rows: `1`
- v2 preload run passed rows: `1`
- v2 subscription candidate rows: `5924`
- v2 preload minute rows stock/index/board: `132000/4080/12720`
- preserved: `True`

## Boundary Proof

- scoped common_event_outbox/inbox/checkpoint refs: `0/0/0`
- common_trigger_run refs: `0`
- common_action_run refs: `0`
- N3-B/C/B2 executed: `False`
- downstream_layers_touched: `False`
- worker_started: `False`

## Rollback Proof

- rollback SQL: `sql/N3_lineage_refresh_for_N2_20260615_v4_rollback.sql`
- rollback executed: `False`
- hard-fail before DELETE/UPDATE: `True`
- scoped to new v4 subscription/preload: `True`
- preserves prior lineage by exclusion: `True`
- no DROP/TRUNCATE/CASCADE: `True`

## Recommendation

`N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_POST_REVIEW_GATE`
