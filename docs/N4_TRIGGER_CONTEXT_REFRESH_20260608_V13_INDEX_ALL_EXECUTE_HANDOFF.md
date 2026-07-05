# N4 Trigger Context Refresh 20260608 v13 Index-All Execute Handoff

- handoff_result: `WAIT_N4_TRIGGER_CONTEXT_EXECUTE_USER_CONFIRMATION`
- layer_role: `runtime_control`
- next_layer_role: `N4_trigger`
- next_required_gate: `N4_TRIGGER_CONTEXT_REFRESH_20260608_V13_INDEX_ALL_EXECUTE_USER_CONFIRMATION_GATE`
- trigger_context_run_id: `trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`

## Current State

N4 context refresh execute has not run yet.

| item | value |
|---|---:|
| common_trigger_run | 0 |
| common_trigger_quality_item | 0 |
| stock_trigger_context_snapshot | 0 |
| index_trigger_context_snapshot | 0 |
| board_trigger_context_snapshot | 0 |
| common_trigger_state | 0 |
| common_trigger_match | 0 |
| common_event_outbox | 0 |
| common_event_inbox | 0 |
| common_event_consumer_checkpoint | 0 |

## Approved Execute Scope

Expected context rows: `4677`

Expected objects:

| asset | objects |
|---|---:|
| stock | 1945 |
| index | 83 |
| board | 127 |
| total | 2155 |

Allowed write scope is limited to:

- `common_trigger_run`
- `common_trigger_quality_item`
- `stock_trigger_context_snapshot`
- `index_trigger_context_snapshot`
- `board_trigger_context_snapshot`

## Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_context_snapshot_execute.py \
  --condition-run-id condition_layer_20260605_to_20260608_v13_index_all_execute \
  --for-trade-date 20260608 \
  --execute --user-confirmed \
  --json-report-path docs/N4_TRIGGER_CONTEXT_REFRESH_20260608_V13_INDEX_ALL_EXECUTE_REPORT.json \
  --markdown-report-path docs/N4_TRIGGER_CONTEXT_REFRESH_20260608_V13_INDEX_ALL_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_trigger_context_refresh_20260608_v13_index_all_rollback.sql
```

## Forbidden Scope

- runtime_control did not execute N4 context refresh.
- rollback SQL was not executed.
- no outbox/inbox/checkpoint was consumed or updated.
- no worker was started.
- no N4 TriggerMatched / N5 / N6 facts were written.
