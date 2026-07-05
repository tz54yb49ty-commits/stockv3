# N2 Condition Layer 20260528 V2 Canonical Target Post Review

- result: POST_REVIEW_PASS
- run_id: condition_layer_20260528_source_20260528_v2
- v2.status: passed_active
- v1.status: superseded
- P0/P1/P2: 0/3/3
- quality_rows: 103
- row_counts_match_expected: true
- alias_mismatch_total: 0
- negative_numeric_total: 0
- forbidden_column_total: 0
- outbox/inbox/checkpoint delta: 0/0/0
- v2 downstream refs total: 0
- rollback_safe: true
- rollback_sql: `sql/N2_condition_layer_20260528_v2_canonical_target_rollback.sql`

## Row Counts

- condition_basis: stock=5506 index=83 board=428
- condition_pool: stock=4271 index=18 board=263
- minute_target_scope: stock=4271 index=18 board=263
- condition_display_basis: stock=5506 index=83 board=428
- monitor_target: stock=5506 index=83 board=428

## Canonical Target Non-null Counts

### condition_basis
- stock: reference_target_price=5312 secondary_target_price=1075 base_price_policy=5354 trace=5506
- index: reference_target_price=76 secondary_target_price=4 base_price_policy=76 trace=83
- board: reference_target_price=418 secondary_target_price=105 base_price_policy=418 trace=428

### condition_pool
- stock: reference_target_price=4140 secondary_target_price=1025 base_price_policy=4145 trace=4271
- index: reference_target_price=16 secondary_target_price=2 base_price_policy=16 trace=18
- board: reference_target_price=257 secondary_target_price=66 base_price_policy=257 trace=263

### minute_target_scope
- stock: reference_target_price=4140 secondary_target_price=1025 base_price_policy=4145 trace=4271
- index: reference_target_price=16 secondary_target_price=2 base_price_policy=16 trace=18
- board: reference_target_price=257 secondary_target_price=66 base_price_policy=257 trace=263

### condition_display_basis
- stock: reference_target_price=5312 secondary_target_price=1075 base_price_policy=5354 trace=5506
- index: reference_target_price=76 secondary_target_price=4 base_price_policy=76 trace=83
- board: reference_target_price=418 secondary_target_price=105 base_price_policy=418 trace=428
