# N2 Canonical Target Writer Readiness Alignment Report

- source_trade_date: 20260528
- for_trade_date: 20260529
- prev_trade_date: 20260528
- passed: true
- schema_ready: true
- canonical_target_fields_ready: true
- source_ready: true
- writes_performed: false
- will_execute_sql: false
- business_rows_written: false
- backfill_performed: false

## Mapping

- base_price_policy: `MIN_CLOSE_AFTER_LAST_LOWER_UP_SEGMENT_PLUS_TRIGGER_OPEN`
- buy direction: `buy_target_price -> reference_target_price`
- sell direction: `sell_target_price -> reference_target_price`
- condition_basis primary compatibility defaults to buy when buy target exists.
- `clear_sell_ref_period` remains legacy alias and must equal `up_sell_reference_period`.
- `locked_target_price` / `target_lock_status` remain forbidden in N2.

## Coverage

### condition_basis
- stock: rows=5506 reference_target_price=5354 base_price_policy=5354 trace_object=5506 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- index: rows=83 reference_target_price=76 base_price_policy=76 trace_object=83 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- board: rows=428 reference_target_price=418 base_price_policy=418 trace_object=428 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0

### condition_pool
- stock: rows=4271 reference_target_price=4145 base_price_policy=4145 trace_object=4271 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- index: rows=18 reference_target_price=16 base_price_policy=16 trace_object=18 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- board: rows=263 reference_target_price=257 base_price_policy=257 trace_object=263 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0

### minute_target_scope
- stock: rows=4271 reference_target_price=4145 base_price_policy=4145 trace_object=4271 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- index: rows=18 reference_target_price=16 base_price_policy=16 trace_object=18 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- board: rows=263 reference_target_price=257 base_price_policy=257 trace_object=263 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0

### condition_display_basis
- stock: rows=5506 reference_target_price=5354 base_price_policy=5354 trace_object=5506 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- index: rows=83 reference_target_price=76 base_price_policy=76 trace_object=83 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0
- board: rows=428 reference_target_price=418 base_price_policy=418 trace_object=428 invalid_period=0 alias_mismatch=0 forbidden=0 mapping_mismatch=0

## Blockers

[]

## Artifact

- JSON: `docs/N2_canonical_target_writer_readiness_alignment_report.json`
- Preflight JSON: `docs/N2_canonical_target_writer_alignment_preflight.json`
