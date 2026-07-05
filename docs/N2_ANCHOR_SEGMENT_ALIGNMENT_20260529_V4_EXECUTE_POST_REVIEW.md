# N2 Anchor Segment Alignment 20260529 V4 Execute Post-Review

Status: **POST_REVIEW_PASS**

## Run Status

- new_run_id: `condition_layer_20260529_source_20260529_v4`
- new_status: `passed_active`
- previous_active_run_id: `condition_layer_20260529_source_20260529_v3`
- previous_status: `superseded`
- active_passed_active_count: `1`
- source_trade_date: `20260529`
- for_trade_date: `20260601`

## Row Counts

- common_condition_run: 1
- common_condition_quality_item: 106
- stock_monitor_target: 5506
- index_monitor_target: 83
- board_monitor_target: 428
- stock_condition_basis: 5506
- index_condition_basis: 83
- board_condition_basis: 428
- stock_condition_pool: 4106
- index_condition_pool: 187
- board_condition_pool: 942
- stock_minute_target_scope: 4087
- index_minute_target_scope: 187
- board_minute_target_scope: 942
- stock_condition_display_basis: 1862
- index_condition_display_basis: 83
- board_condition_display_basis: 428

## Quality

- common_condition_run P0/P1/P2: `0/6/3`
- quality_item rows: `106`
- quality_item status distribution: `[{'severity': 'P0', 'status': 'passed', 'count': 91}, {'severity': 'P1', 'status': 'passed', 'count': 3}, {'severity': 'P1', 'status': 'warning', 'count': 8}, {'severity': 'P2', 'status': 'warning', 'count': 4}]`

## Golden Verification

- 000600 建投能源: target `12.93`, A segment `20260518 -> 20260529`, base `10.13`, amplitude `2.8`
- 000543 皖能电力: target `10.82`, A segment `20260506 -> 20260529`, base `9.11`, amplitude `1.71`
- 000027 深圳能源: target `8.45`, A segment `20260506 -> 20260529`, base `7.25`, amplitude `1.2`

## Boundary Proof

- common_market_data_run refs: `0`
- common_trigger_run refs: `0`
- common_action_run refs: `0`
- common_event_outbox refs: `0`
- common_event_inbox refs: `0`
- common_event_consumer_checkpoint refs: `0`
- N3/N4/N5/N6 auto switch: `false`
- market data pulled: `false`
- worker started: `false`

## Rollback

- rollback_sql: `sql/N2_anchor_segment_alignment_20260529_v4_rollback.sql`
- rollback_safe: `True`
- guard: rollback must be blocked if v4 has N3/N4/N5/N6 downstream refs.
