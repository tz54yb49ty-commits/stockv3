# N2 Context Enrichment Row-Level Materialization Dry-Run Report

- materialization_result: MATERIALIZATION_DRY_RUN_PASS
- source_condition_run_id: condition_layer_20260602_source_20260602_v1
- target_run_id: condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1
- for_trade_date: 20260603
- spec_version: N2-context-enrichment-row-materialization-v1
- policy_hash: 22b892190d9c271265f4f544aa455dec43aad710744deaf763df8bb09ab67434
- target_rows: {"board": 890, "index": 168, "stock": 4164, "total": 5222}
- payload_artifact: docs/N2_20260603_context_enrichment_row_level_payload.jsonl
- P0/P1/P2: 0/1/1

## Coverage
- previous_transition_rows: 5222
- previous_entity_bound_rows: 5172
- previous_amount_baseline_rows: 5172
- context_enrichment_hash_rows: 5222
- FULL_trace_rows: 5222
- HINT_trace_rows: 5222
- period_baseline_ready_distribution: {"all_ready": 5172, "partial_or_not_ready": 50}
- required_period_baseline_missing_rows: 0

## DB Materialization Plan
- current_gate_write_tables: []
- future_execute_write_tables: ["common_condition_context_enrichment_run", "stock_condition_context_enrichment", "index_condition_context_enrichment", "board_condition_context_enrichment"]
- rollback_sql_path: sql/N2_20260603_context_enrichment_row_level_materialization_rollback.sql
- execute_final_gate_ready: True

## Execute Gate
```bash
PYTHONPATH=src:scripts python3 scripts/run_n2_context_enrichment_materialization_execute.py --payload-path docs/N2_20260603_context_enrichment_row_level_payload.jsonl --contract-path docs/N2_20260603_context_enrichment_row_level_materialization_contract.json --execute --user-confirmed
```
- missing_execute_gate: {"blocked_reasons": ["missing_execute_flag"], "gate_result": "BLOCKED", "writes_allowed": false}
- missing_user_confirmed_gate: {"blocked_reasons": ["missing_user_confirmed_flag"], "gate_result": "BLOCKED", "writes_allowed": false}

## Rollback Hard-Fail Guard
- event_infra: ["common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint"]
- downstream_refs: ["common_market_data_run", "common_trigger_run", "common_trigger_state", "common_trigger_match", "common_action_run", "common_action_event", "user_projection_run", "user_signal_projection", "user_signal_card", "user_notification_queue"]
- runtime_flags: ["downstream_layers_touched", "worker_started"]
- guard_before_first_delete: True
- delete_before_guard: False

## Boundary
- writes_performed: false
- will_execute_sql: false
- N3/N4/N5/N6: not entered
- outbox_consumed: false
- worker_started: false
