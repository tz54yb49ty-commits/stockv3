# N2 20260609 Condition Layer Execute Report

Result: `EXECUTE_PASS`

Executed command:

```bash
PYTHONPATH=src python3 scripts/run_condition_layer_execute.py \
  --source-trade-date 20260608 \
  --policy configs/n2_policy/default_policy_draft.json \
  --run-id condition_layer_20260608_source_20260608_for_20260609_v1 \
  --execute \
  --user-confirmed \
  --operator codex \
  --confirmation-note N2-20260609-condition-layer-final-execute \
  --report-path docs/N2_20260609_condition_layer_execute_report.json
```

## Run

```text
run_id = condition_layer_20260608_source_20260608_for_20260609_v1
source_trade_date = 20260608
for_trade_date = 20260609
prev_trade_date = 20260608
status = passed_active
active_passed_count = 1
policy_hash = 5161cc7743480ccbbf2bf7b413417946870ccb8ffdd468f47f430385b1b6542c
```

## Rows

| table | rows |
|---|---:|
| common_condition_run | 1 |
| common_condition_quality_item | 106 |
| stock_monitor_target | 5514 |
| index_monitor_target | 83 |
| board_monitor_target | 428 |
| stock_condition_basis | 5514 |
| index_condition_basis | 83 |
| board_condition_basis | 428 |
| stock_condition_pool | 4063 |
| index_condition_pool | 216 |
| board_condition_pool | 265 |
| stock_minute_target_scope | 4043 |
| index_minute_target_scope | 216 |
| board_minute_target_scope | 265 |
| stock_condition_display_basis | 1880 |
| index_condition_display_basis | 83 |
| board_condition_display_basis | 127 |

## Boundary

```text
migration_performed = false
minute_kline_pulled = false
downstream_layers_touched = false
outbox/inbox/checkpoint refs = 0/0/0
N3/N4/N5/N6 refs = 0/0/0/0
```

Rollback SQL:

```text
sql/N2_condition_layer_20260609_rollback.sql
```
