# N2 Context Enrichment Schema/Contract Dry-Run Report

- gate_result: DRY_RUN_PASS
- refresh_result: REFRESH_PASS
- run_id: condition_layer_20260602_source_20260602_v1
- source_trade_date: 20260602
- for_trade_date: 20260603
- rows: {"board": 890, "index": 168, "stock": 4164}
- context_source: scope
- expected_context_candidates: 5222
- P0/P1/P2: 0/1/1

## Refresh Summary
- context_row_count: 5222
- context_enrichment_rows: 5222
- previous_transition_rows: 5222
- previous_entity_bound_rows: 5172
- previous_amount_baseline_rows: 5172
- period_baseline_ready_distribution: {"all_ready": 5172, "partial_or_not_ready": 50}
- required_period_baseline_missing_rows: 0
- FULL_trace_rows: 5222
- HINT_trace_rows: 5222

## Coverage
- context_hash_missing: 0
- amount_chain_missing: 0
- formula_hash_missing: 0
- full_trace_missing: 0
- hint_trace_missing: 0
- previous_transition_missing: 0
- previous_amount_baseline_missing: 79
- period_baseline_not_ready_entries: 79

## Boundary
- writes_performed: false
- will_execute_sql: false
- N3/N4/N5/N6 implementation: not entered
- outbox consumption: false
- worker_started: false

## Next Gate
- implementation_allowed: True
- next_gate: N2_CONTEXT_ENRICHMENT_IMPLEMENTATION_GATE
