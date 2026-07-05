# N4 20260602 Trigger Context Snapshot Execute Post Review

- run_id: trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1
- status: passed
- row_counts: {'stock': 4715, 'index': 220, 'board': 1006, 'total': 5941}
- expected_row_counts: {'stock': 4715, 'index': 220, 'board': 1006, 'total': 5941}
- direction_distribution: {'sell': 2867, 'buy': 3074}
- quality: {'quality_rows': 53, 'p0_failed': 0, 'p1_rows': 0, 'p2_rows': 0, 'execute_report_p0': 0, 'execute_report_p1': 0, 'execute_report_p2': 0}
- boundary: {'trigger_state_rows': 0, 'trigger_match_rows': 0, 'outbox_refs': 0, 'inbox_refs': 0, 'n5_refs': 0, 'n6_refs': 0, 'total_outbox': 153828, 'total_inbox': 56170, 'total_checkpoint': 4368, 'market_data_pulled': False, 'n3_event_consumed': False, 'worker_started': False, 'downstream_layers_touched': False}
- rollback_safe: True
- rollback_sql: sql/N4_20260602_trigger_context_snapshot_rollback.sql
- next_gate: N4 projection matcher execute preflight/final confirmation
