# N3 Lineage Refresh For N2 20260615 V4 Preflight

- result: PREFLIGHT_PASS
- layer_role: N3_market_data
- new_subscription_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- new_preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- P0/P1/P2: 0/2/0

## Baseline From Readiness
- common_market_data_run: 0
- common_market_data_quality_item: 0
- common_market_data_subscription_candidate: 0
- common_market_data_subscription: 0
- common_market_data_pull_plan: 0
- stock_previous_day_minute_preload_status: 0
- index_previous_day_minute_preload_status: 0
- board_previous_day_minute_preload_status: 0
- stock_minute_bar_1m_previous_day_scoped: 0
- index_minute_bar_1m_previous_day_scoped: 0
- board_minute_bar_1m_previous_day_scoped: 0
- previous_day_minute_preload_status_total: 0
- previous_day_minute_bar_1m_scoped_total: 0

## Event Refs From Readiness
- outbox: 0
- inbox: 0
- checkpoint: 0

## Downstream Refs From Readiness
- N4: {'total': 0}
- N5: {'total': 0}
- N6: {'total': 0}

## Execute Commands
- stage1_subscription: PYTHONPATH=src:scripts python3 scripts/run_market_data_subscription_execute.py --source-condition-run-id condition_layer_20260615_source_20260615_for_20260616_v4 --source-trade-date 20260615 --for-trade-date 20260616 --market-data-run-id market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 --execute --user-confirmed --pre-backup-path docs/N3_lineage_refresh_for_N2_20260615_v4_subscription_execute_backup_before.json --post-backup-path docs/N3_lineage_refresh_for_N2_20260615_v4_subscription_execute_backup_after.json --report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_SUBSCRIPTION_EXECUTE_REPORT.json --markdown-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_SUBSCRIPTION_EXECUTE_REPORT.md
- stage2_a1_preload_after_stage1_pass: PYTHONPATH=src:scripts python3 scripts/run_previous_day_minute_preload_execute.py --contract-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_CONTRACT.json --historical-preload --source-subscription-run-id market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 --preload-run-id previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 --data-trade-date 20260615 --execute --user-confirmed --json-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_A1_PRELOAD_EXECUTE_REPORT.json --markdown-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_A1_PRELOAD_EXECUTE_REPORT.md
