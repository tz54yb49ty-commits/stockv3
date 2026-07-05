# N2 Context Enrichment Schema/Contract Dry-Run Report

- gate_result: DRY_RUN_PASS
- run_id: condition_layer_20260602_source_20260602_v1
- source_trade_date: 20260602
- for_trade_date: 20260603
- rows: {"board": 428, "index": 83, "stock": 5507}
- P0/P1/P2: 0/1/1

## Coverage
- context_hash_missing: 0
- amount_chain_missing: 0
- formula_hash_missing: 0
- full_trace_missing: 0
- hint_trace_missing: 0
- previous_transition_missing: 0
- previous_amount_baseline_missing: 102
- period_baseline_not_ready_entries: 102

## Boundary
- writes_performed: false
- will_execute_sql: false
- N3/N4/N5/N6 implementation: not entered
- outbox consumption: false
- worker_started: false

## Next Gate
- implementation_allowed: True
- next_gate: N2_CONTEXT_ENRICHMENT_IMPLEMENTATION_GATE
