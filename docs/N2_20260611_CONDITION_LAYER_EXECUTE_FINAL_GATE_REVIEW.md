# N2 20260611 Condition Layer Execute Final Gate Review

Result: `PASS`

- source_trade_date: `20260610`
- for_trade_date: `20260611`
- run_id: `condition_layer_20260610_source_20260610_for_20260611_v1`
- P0/P1/P2: `0/6/3`
- target baseline total: `0`
- refs baseline total: `0`
- rollback_safe: `True`

## Expected Rows

```json
{
  "common_condition_run": 1,
  "common_condition_quality_item": 106,
  "stock_monitor_target": 5510,
  "index_monitor_target": 83,
  "board_monitor_target": 428,
  "stock_condition_basis": 5510,
  "index_condition_basis": 83,
  "board_condition_basis": 428,
  "stock_condition_pool": 4046,
  "index_condition_pool": 185,
  "board_condition_pool": 268,
  "index_minute_target_scope": 185,
  "board_minute_target_scope": 268,
  "stock_minute_target_scope": 4027,
  "stock_condition_display_basis": 1890,
  "index_condition_display_basis": 83,
  "board_condition_display_basis": 127
}
```

## Target Baseline

```json
{
  "common_condition_run": 0,
  "stock_condition_basis": 0,
  "index_condition_basis": 0,
  "board_condition_basis": 0,
  "stock_condition_pool": 0,
  "index_condition_pool": 0,
  "board_condition_pool": 0,
  "stock_minute_target_scope": 0,
  "index_minute_target_scope": 0,
  "board_minute_target_scope": 0,
  "stock_condition_display_basis": 0,
  "index_condition_display_basis": 0,
  "board_condition_display_basis": 0,
  "common_condition_quality_item": 0,
  "stock_monitor_target": 0,
  "index_monitor_target": 0,
  "board_monitor_target": 0
}
```

## Refs Baseline

```json
{
  "common_event_outbox": 0,
  "common_event_inbox": 0,
  "common_event_consumer_checkpoint": 0,
  "N3_common_market_data_run": 0,
  "N4_common_trigger_run": 0,
  "N5_common_action_run": 0,
  "N6_user_projection_run": 0
}
```

## Allowed Execute Command

```bash
PYTHONPATH=src python3 scripts/run_condition_layer_execute.py \
  --source-trade-date 20260610 \
  --policy configs/n2_policy/default_policy_draft.json \
  --run-id condition_layer_20260610_source_20260610_for_20260611_v1 \
  --execute \
  --user-confirmed \
  --operator codex \
  --confirmation-note N2-20260611-condition-layer-final-execute \
  --report-path docs/N2_20260611_condition_layer_execute_report.json
```

## Rollback Proof

```json
{
  "path": "sql/N2_condition_layer_20260611_rollback.sql",
  "exists": true,
  "hard_fail_before_delete": true,
  "no_drop_truncate_cascade": true,
  "no_forbidden_table_dml": true,
  "forbidden_table_dml": [],
  "run_id_scoped": true,
  "guards_event_and_downstream_refs": true,
  "passed": true
}
```
