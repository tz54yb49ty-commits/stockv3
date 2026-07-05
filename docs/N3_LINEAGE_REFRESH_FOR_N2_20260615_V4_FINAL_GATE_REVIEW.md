# N3 Lineage Refresh For N2 20260615 V4 Final Gate Review

- result: PASS
- layer_role: N3_market_data
- P0/P1/P2: 0/2/0

## Findings
- readiness: READINESS_PASS
- n2_v4_status: passed_active
- n2_v3_status: superseded
- previous_v2_preserved: {'subscription_run': 1, 'preload_run': 1}
- target_v4_baseline_zero: True
- v4_source_scope_rows: {'stock': 4194, 'index': 183, 'board': 307}
- v4_scope_objects: {'stock': 1822, 'index': 83, 'board': 127}
- stock_002831_propagation_present: {'artifact_has_002831': True, 'db_stock_minute_target_scope_rows': 2, 'artifact_proof': {'basis': {'stock_identity_key': 'stock:SZ:002831', 'financial_source_version': 'stock_financial_20260615_v3', 'financial_quality_status': 'warning', 'pe_core': 20.2506996374, 'score': 87.0, 'cash_realization_rate': 1.9254856573, 'revenue_yoy_pct': 2.55, 'core_profit_yoy_pct': 57.1302091953, 'report_core_profit': 341586050.0, 'core_profit_ttm': 1940382164.0, 'financial_metric_version': 'financial_metric_v1', 'financial_warning_json': {'warnings': ['forecast_missing'], 'source_type': 'tdx_financial_package', 'tdx_parity_repair': True, 'interest_expense_used': '19744658'}}, 'pool_rows': 2, 'scope_rows': 2, 'display_rows': 1, 'pool_samples': [{'condition_key': 'BUY:M,D', 'direction': 'buy', 'allowed_signal_types': ['BUY'], 'score': 87.0}, {'condition_key': 'SELL:Y,Q,M,W,D', 'direction': 'sell', 'allowed_signal_types': ['SELL'], 'score': 87.0}]}}
- subscription_counts: {'candidate': 5924, 'dedup_subscription': 3272, 'subscription_objects': 2032, 'pull_plan': 9}
- a1_expected: {'objects': {'stock': 550, 'index': 17, 'board': 53, 'total': 620}, 'minute_rows': {'stock': 132000, 'index': 4080, 'board': 12720, 'total': 148800}}
- downstream_refs_zero: True
- rollback_safe_static: True

## Allowed Execute Command
- stage1_subscription_control_rows: PYTHONPATH=src:scripts python3 scripts/run_market_data_subscription_execute.py --source-condition-run-id condition_layer_20260615_source_20260615_for_20260616_v4 --source-trade-date 20260615 --for-trade-date 20260616 --market-data-run-id market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 --execute --user-confirmed --pre-backup-path docs/N3_lineage_refresh_for_N2_20260615_v4_subscription_execute_backup_before.json --post-backup-path docs/N3_lineage_refresh_for_N2_20260615_v4_subscription_execute_backup_after.json --report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_SUBSCRIPTION_EXECUTE_REPORT.json --markdown-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_SUBSCRIPTION_EXECUTE_REPORT.md
- stage2_a1_previous_day_minute_preload_after_stage1_pass: PYTHONPATH=src:scripts python3 scripts/run_previous_day_minute_preload_execute.py --contract-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_CONTRACT.json --historical-preload --source-subscription-run-id market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 --preload-run-id previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 --data-trade-date 20260615 --execute --user-confirmed --json-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_A1_PRELOAD_EXECUTE_REPORT.json --markdown-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_A1_PRELOAD_EXECUTE_REPORT.md

## Forbidden Scope
- do_not_execute_in_this_gate: True
- do_not_write_outbox_inbox_checkpoint: True
- do_not_enter_n3_b_c_b2: True
- do_not_enter_n4_n5_n6: True
- do_not_start_worker: True
- do_not_touch_voice_mobile_sim_position_order_real_trade: True
- do_not_touch_old_system: True
