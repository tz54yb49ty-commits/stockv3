# N3 Lineage Refresh For N2 20260615 V2 Preflight

Result: `PREFLIGHT_PASS`

## Prerequisites

- readiness: `READINESS_PASS`
- N2 v2 status: `passed_active`
- N2 v1 status: `superseded`
- active N2 run count: `1`

## Baseline

- target v2 subscription rows: `{'common_market_data_run': 0, 'common_market_data_quality_item': 0, 'common_market_data_subscription_candidate': 0, 'common_market_data_subscription': 0, 'common_market_data_pull_plan': 0, 'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- target v2 preload rows: `{'common_market_data_run': 0, 'common_market_data_quality_item': 0, 'stock_minute_bar_1m': 0, 'index_minute_bar_1m': 0, 'board_minute_bar_1m': 0, 'stock_previous_day_minute_preload_status': 0, 'index_previous_day_minute_preload_status': 0, 'board_previous_day_minute_preload_status': 0, 'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- downstream refs: `{'n4': {'common_trigger_match': 0, 'common_trigger_state': 0}, 'n5': {'common_action_event': 0}, 'n6': {'user_projection_run': 0, 'user_signal_projection': 0, 'user_signal_card': 0, 'user_notification_queue': 0, 'user_sim_order': 0, 'user_sim_trade': 0, 'user_sim_position': 0, 'n6_virtual_account': 0, 'n6_virtual_order': 0, 'n6_virtual_trade': 0, 'n6_virtual_position': 0, 'n6_virtual_position_event': 0, 'n6_virtual_pnl_snapshot': 0}}`

## Execute Commands

Stage 1:

```bash
PYTHONPATH=src:scripts python3 scripts/run_market_data_subscription_execute.py --source-condition-run-id condition_layer_20260615_source_20260615_for_20260616_v2 --source-trade-date 20260615 --for-trade-date 20260616 --market-data-run-id market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2 --execute --user-confirmed --pre-backup-path docs/N3_lineage_refresh_for_N2_20260615_v2_subscription_execute_backup_before.json --post-backup-path docs/N3_lineage_refresh_for_N2_20260615_v2_subscription_execute_backup_after.json --report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_SUBSCRIPTION_EXECUTE_REPORT.json --markdown-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_SUBSCRIPTION_EXECUTE_REPORT.md
```

Stage 2, only after Stage 1 post-check PASS:

```bash
PYTHONPATH=src:scripts python3 scripts/run_previous_day_minute_preload_execute.py --contract-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_CONTRACT.json --historical-preload --source-subscription-run-id market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2 --preload-run-id previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2 --data-trade-date 20260615 --execute --user-confirmed --json-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_A1_PRELOAD_EXECUTE_REPORT.json --markdown-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_A1_PRELOAD_EXECUTE_REPORT.md
```

## Quality

- P0/P1/P2: `0/2/0`
