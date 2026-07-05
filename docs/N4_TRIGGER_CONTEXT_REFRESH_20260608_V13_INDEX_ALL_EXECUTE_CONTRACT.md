# N4 Trigger Context Refresh 20260608 v13 Index-All Execute Contract

- result: `CONTRACT_PASS`
- trigger_context_run_id: `trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`

## Approved Scope

| key | value |
|---|---|
| stock | `4241` |
| index | `169` |
| board | `267` |
| total | `4677` |

## Allowed Writes

| key | value |
|---|---|
| tables | `["common_trigger_run", "common_trigger_quality_item", "stock_trigger_context_snapshot", "index_trigger_context_snapshot", "board_trigger_context_snapshot"]` |

## Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_context_snapshot_execute.py --condition-run-id condition_layer_20260605_to_20260608_v13_index_all_execute --for-trade-date 20260608 --execute --user-confirmed --json-report-path docs/N4_TRIGGER_CONTEXT_REFRESH_20260608_V13_INDEX_ALL_EXECUTE_REPORT.json --markdown-report-path docs/N4_TRIGGER_CONTEXT_REFRESH_20260608_V13_INDEX_ALL_EXECUTE_REPORT.md --rollback-sql-path sql/N4_trigger_context_refresh_20260608_v13_index_all_rollback.sql
```
