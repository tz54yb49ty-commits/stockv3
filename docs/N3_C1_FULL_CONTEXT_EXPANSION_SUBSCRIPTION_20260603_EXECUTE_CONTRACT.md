# N3 C1 Full-Context Expansion Subscription Execute Contract

- execute_authorized: false
- runner_readiness: ready
- market_data_run_id: `market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1`
- candidate rows: 4391
- subscription rows: 2197
- pull_plan rows: 3
- objects: {'stock': 1722, 'index': 81, 'board': 394}
- rollback_sql: `sql/N3_C1_full_context_expansion_subscription_20260603_rollback.sql`

## Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_full_context_expansion_subscription_execute.py --dry-run-path docs/N3_C1_full_context_expansion_subscription_20260603_dry_run_report.json --json-report-path docs/N3_C1_full_context_expansion_subscription_20260603_execute_report.json --markdown-report-path docs/N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_20260603_EXECUTE_REPORT.md --execute --user-confirmed
```
