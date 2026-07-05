# N3-B2 20260602 Live3 Execute Post Review

- projection_run_id: realtime_projection_metric_20260602_live3__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
- status: passed
- row_counts: {'stock': 1976, 'index': 83, 'board': 428, 'total': 2487}
- expected_row_counts: {'stock': 1976, 'index': 83, 'board': 428, 'total': 2487}
- quality: {'quality_rows': 6, 'p0_failed': 0, 'p1_rows': 3, 'p2_rows': 0, 'execute_report_p0': 0, 'execute_report_p1': 3, 'execute_report_p2': 0}
- projection_quality_distribution: {'stock': {'blocked': 1211, 'passed': 765}, 'index': {'blocked': 29, 'passed': 54}, 'board': {'blocked': 428}}
- projection_signal_distribution: {'stock': {'down_volume_expanding': 55, 'down_volume_flat': 91, 'down_volume_shrinking': 217, 'flat': 114, 'unknown': 1211, 'up_volume_expanding': 83, 'up_volume_flat': 88, 'up_volume_shrinking': 117}, 'index': {'down_volume_flat': 2, 'down_volume_shrinking': 1, 'flat': 13, 'unknown': 29, 'up_volume_flat': 37, 'up_volume_shrinking': 1}, 'board': {'unknown': 428}}
- boundary: {'outbox_refs': 0, 'inbox_refs': 0, 'total_outbox': 153828, 'total_inbox': 56170, 'total_checkpoint': 4368, 'n4_trigger_refs': 0, 'n5_action_refs': 0, 'user_projection_refs': 0, 'user_signal_refs': 0, 'downstream_layers_touched': False, 'worker_started': False, 'market_snapshot_payload_updated': False, 'outbox_consumed': False}
- rollback_safe: True
- rollback_sql: sql/N3_B2_realtime_projection_20260602_live3_rollback.sql
- next_gate: N4 trigger context snapshot execute final confirmation/post-review
