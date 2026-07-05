# N2 Context Enrichment Row-Level Materialization Preflight

- preflight_result: PASS
- execute_final_gate_ready: True
- blocked_reasons: []
- source_condition_run_id: condition_layer_20260602_source_20260602_v1
- target_run_id: condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1
- P0/P1/P2: 0/1/1

## DB Materialization Plan
- schema_ready: True
- missing_tables: []
- target_run_baseline_zero: True
- requires_schema_migration_before_execute: False
- future_execute_write_tables: ["common_condition_context_enrichment_run", "stock_condition_context_enrichment", "index_condition_context_enrichment", "board_condition_context_enrichment"]

## Execute Flag Gate
```bash
PYTHONPATH=src:scripts python3 scripts/run_n2_context_enrichment_materialization_execute.py --payload-path docs/N2_20260603_context_enrichment_row_level_payload.jsonl --contract-path docs/N2_20260603_context_enrichment_row_level_materialization_contract.json --execute --user-confirmed
```
- requires_execute: True
- requires_user_confirmed: True
- missing_execute_gate: {"blocked_reasons": ["missing_execute_flag"], "gate_result": "BLOCKED", "writes_allowed": false}
- missing_user_confirmed_gate: {"blocked_reasons": ["missing_user_confirmed_flag"], "gate_result": "BLOCKED", "writes_allowed": false}
- blocked_before_database_write: True

## Boundary
- writes_performed: false
- will_execute_sql: false
- worker_started: false
