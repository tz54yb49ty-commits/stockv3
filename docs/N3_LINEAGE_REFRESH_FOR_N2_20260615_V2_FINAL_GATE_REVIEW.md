# N3 Lineage Refresh For N2 20260615 V2 Final Gate Review

Result: `PASS`

## Findings

- readiness: `READINESS_PASS`
- N2 v2 status: `passed_active`
- old v1 preserved subscription/preload: `{'subscription_run': 1, 'preload_run': 1}`
- target v2 baseline zero: `True`
- v2 source scope rows stock/index/board: `4194/183/307`
- candidate/subscription/pull_plan: `5924/3272/9`
- A1 objects stock/index/board/total: `550/17/53/620`
- A1 expected rows stock/index/board/total: `132000/4080/12720/148800`
- downstream refs zero: `True`

## Allowed Execute Commands

Stage 1:

```bash
PYTHONPATH=src:scripts python3 scripts/run_market_data_subscription_execute.py --source-condition-run-id condition_layer_20260615_source_20260615_for_20260616_v2 --source-trade-date 20260615 --for-trade-date 20260616 --market-data-run-id market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2 --execute --user-confirmed --pre-backup-path docs/N3_lineage_refresh_for_N2_20260615_v2_subscription_execute_backup_before.json --post-backup-path docs/N3_lineage_refresh_for_N2_20260615_v2_subscription_execute_backup_after.json --report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_SUBSCRIPTION_EXECUTE_REPORT.json --markdown-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_SUBSCRIPTION_EXECUTE_REPORT.md
```

Stage 2, only after Stage 1 PASS:

```bash
PYTHONPATH=src:scripts python3 scripts/run_previous_day_minute_preload_execute.py --contract-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_CONTRACT.json --historical-preload --source-subscription-run-id market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2 --preload-run-id previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2 --data-trade-date 20260615 --execute --user-confirmed --json-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_A1_PRELOAD_EXECUTE_REPORT.json --markdown-report-path docs/N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_A1_PRELOAD_EXECUTE_REPORT.md
```

## Boundary

- execute_user_confirmation_allowed: `true`
- writes_outbox: `false`
- N4/N5/N6 execute: `false`
- worker_started: `false`
- rollback_not_executed: `true`

## Quality

- P0/P1/P2: `0/2/0`
