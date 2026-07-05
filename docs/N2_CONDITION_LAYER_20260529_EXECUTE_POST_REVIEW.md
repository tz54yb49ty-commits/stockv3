# N2 Condition Layer 20260529 Execute Post Review

Result: POST_REVIEW_PASS

## Run Status
- run_id: `condition_layer_20260529_source_20260529_v1`
- status: `passed_active`
- source_trade_date / for_trade_date / prev_trade_date: `20260529` / `20260601` / `20260529`
- active passed_active count: `1`
- P0/P1/P2: `0` / `9` / `3`

## Row Counts
- condition_basis: stock=5506 index=83 board=428
- condition_pool: stock=4342 index=187 board=942
- minute_target_scope: stock=4323 index=187 board=942
- condition_display_basis: stock=1973 index=83 board=428
- monitor_target: stock=5506 index=83 board=428
- common_condition_quality_item: 109
- row_count_matches_expected: `True`

## Audits
- canonical_signal_audit_passed: `True`
- deprecated_signal_rows: `0`
- noncanonical_signal_rows: `0`
- clear_sell_ref_period alias mismatch total: `0`
- negative target numeric total: `0`
- forbidden locked target columns: `0`

## Boundary Proof
- event ledger delta: `{'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- scoped outbox/inbox/checkpoint refs: `0` / `0` / `0`
- downstream refs: `{'common_market_data_run': 0, 'common_trigger_run': 0, 'common_action_run': 0, 'user_projection_run': None, 'user_signal_projection': None, 'common_user_projection_run': None, 'passed': True}`

## Rollback
- rollback_sql: `sql/N2_condition_layer_20260529_rollback.sql`
- rollback_safe: `True`
