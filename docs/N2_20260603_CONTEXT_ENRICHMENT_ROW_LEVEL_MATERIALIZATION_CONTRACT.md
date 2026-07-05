# N2 Context Enrichment Row-Level Materialization Contract

- contract_result: CONTRACT_READY
- source_condition_run_id: condition_layer_20260602_source_20260602_v1
- target_run_id: condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1
- for_trade_date: 20260603
- spec_version: N2-context-enrichment-row-materialization-v1
- policy_hash: 22b892190d9c271265f4f544aa455dec43aad710744deaf763df8bb09ab67434
- expected_context_rows: 5222
- row_level_source: stock/index/board_minute_target_scope
- payload_format: jsonl
- payload_path: docs/N2_20260603_context_enrichment_row_level_payload.jsonl
- contract_path: docs/N2_20260603_context_enrichment_row_level_materialization_contract.json

## Execute Command Candidate
```bash
PYTHONPATH=src:scripts python3 scripts/run_n2_context_enrichment_materialization_execute.py --payload-path docs/N2_20260603_context_enrichment_row_level_payload.jsonl --contract-path docs/N2_20260603_context_enrichment_row_level_materialization_contract.json --execute --user-confirmed
```
- requires_execute: True
- requires_user_confirmed: True
- missing_execute_gate: {"blocked_reasons": ["missing_execute_flag"], "gate_result": "BLOCKED", "writes_allowed": false}
- missing_user_confirmed_gate: {"blocked_reasons": ["missing_user_confirmed_flag"], "gate_result": "BLOCKED", "writes_allowed": false}
- blocked_before_database_write: True

## Write Scope
- current_gate: []
- future_execute_gate: ["common_condition_context_enrichment_run", "stock_condition_context_enrichment", "index_condition_context_enrichment", "board_condition_context_enrichment"]

## Boundary
- N3/N4/N5/N6: not entered
- outbox/inbox/checkpoint: not written or consumed
- n4_can_recompute_context: false
- n3_lineage_auto_switch: false
- rollback_sql_path: sql/N2_20260603_context_enrichment_row_level_materialization_rollback.sql
