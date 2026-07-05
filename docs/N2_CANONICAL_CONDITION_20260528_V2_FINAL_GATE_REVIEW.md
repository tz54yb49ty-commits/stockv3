# N2 Canonical Condition 20260528 V2 Final Gate Review

- result: PASS
- source_trade_date: 20260528
- for_trade_date: 20260529
- target_run_id: condition_layer_20260528_source_20260528_v2
- existing_active_run_id: condition_layer_20260528_source_20260528_v1
- preflight_execute_allowed: true
- blocked_reasons: []
- activation_strategy: active_lineage_supersede_only
- shadow_or_passed_candidate_supported: false
- writes_performed: false
- will_execute_sql: false

## Expected Rows

- common_condition_run: 1
- common_condition_quality_item: 75
- stock_monitor_target: 5506
- index_monitor_target: 83
- board_monitor_target: 428
- stock_condition_basis: 5506
- index_condition_basis: 83
- board_condition_basis: 428
- stock_condition_pool: 4271
- index_condition_pool: 18
- board_condition_pool: 263
- index_minute_target_scope: 18
- board_minute_target_scope: 263
- stock_minute_target_scope: 4271
- stock_condition_display_basis: 5506
- index_condition_display_basis: 83
- board_condition_display_basis: 428

## Canonical Target Coverage

### condition_basis
- stock: rows=5506 reference_target_price=5354 base_price_policy=5354 trace=5506 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- index: rows=83 reference_target_price=76 base_price_policy=76 trace=83 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- board: rows=428 reference_target_price=418 base_price_policy=418 trace=428 alias_mismatch=0 forbidden=0 mapping_mismatch=0

### condition_pool
- stock: rows=4271 reference_target_price=4145 base_price_policy=4145 trace=4271 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- index: rows=18 reference_target_price=16 base_price_policy=16 trace=18 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- board: rows=263 reference_target_price=257 base_price_policy=257 trace=263 alias_mismatch=0 forbidden=0 mapping_mismatch=0

### minute_target_scope
- stock: rows=4271 reference_target_price=4145 base_price_policy=4145 trace=4271 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- index: rows=18 reference_target_price=16 base_price_policy=16 trace=18 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- board: rows=263 reference_target_price=257 base_price_policy=257 trace=263 alias_mismatch=0 forbidden=0 mapping_mismatch=0

### condition_display_basis
- stock: rows=5506 reference_target_price=5354 base_price_policy=5354 trace=5506 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- index: rows=83 reference_target_price=76 base_price_policy=76 trace=83 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- board: rows=428 reference_target_price=418 base_price_policy=418 trace=428 alias_mismatch=0 forbidden=0 mapping_mismatch=0

## Lineage

- v1_total_rows: 27262
- v2_total_rows: 0
- v1_downstream_refs: {"common_market_data_run": 5, "common_trigger_run": 3, "common_action_run": 2}
- v2_downstream_refs: {"common_market_data_run": 0, "common_trigger_run": 0, "common_action_run": 0}
- N3/N4/N5/N6 auto switch: false

## Rollback

- SQL: `sql/N2_condition_layer_20260528_v2_canonical_target_rollback.sql`
- Deletes only v2 rows and restores v1.status=passed_active.
- Blocks if v2 already has downstream refs.

## Gate Decision

- PASS for explicit active lineage supersede execute confirmation point.
- BLOCKED for shadow / passed_candidate execute because current `common_condition_run.status` and runner do not support non-active candidate status.
