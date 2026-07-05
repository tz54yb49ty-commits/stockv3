# N4 20260605 V4 Corrected Execute Contract

- result: CONTRACT_PASS
- execute_run_id: trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
- dry_run_artifact_path: docs/N4_20260605_V4_CORRECTED_DRY_RUN.json
- rollback_sql_path: sql/N4_20260605_V4_CORRECTED_EXECUTE_ROLLBACK.sql

## Planned Writes

- common_trigger_run: 1
- common_trigger_quality_item: 4
- common_trigger_state: 1240
- common_trigger_match: 1240
- common_event_outbox: 1240
- TriggerMatched: 1240
- TriggerPendingMarketData: 0
- TriggerStateChanged: 0

## Blocked Candidates

- total: 297
- by_reason: {'missing trigger_price': 275, 'missing trigger_kind': 0, 'missing triggered_periods': 275, 'missing n5_entry_allowed': 0, 'future event_time': 0, 'future trigger_time': 0, 'FULL forbidden': 29, 'invalid signal_type': 0, 'invalid N5 entry': 0}
- reason_counts_are_non_exclusive: True

## P0 Guards

- trigger_price
- trigger_kind
- triggered_periods
- all_trigger_periods
- primary_trigger_period
- n5_entry_allowed
- event_time_not_future
- trigger_time_not_future
- FULL_forbidden_by_default
- runtime_signal_type_B_BUY_or_S_SELL

## N5 Entry Contract

- required: TriggerMatched + B_BUY/S_SELL + current_status=matched + trigger_live=true + n5_entry_allowed=true
- invalid_n5_entry_count: 0

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_n4_20260605_v4_corrected_execute_once.py \
  --execute-run-id trigger_execute_20260605_condition_layer_20260604_source_20260604_v1 \
  --dry-run-json-path docs/N4_20260605_V4_CORRECTED_DRY_RUN.json \
  --contract-path docs/N4_20260605_V4_CORRECTED_EXECUTE_CONTRACT.json \
  --preflight-path docs/N4_20260605_V4_CORRECTED_EXECUTE_PREFLIGHT.json \
  --rollback-sql-path sql/N4_20260605_V4_CORRECTED_EXECUTE_ROLLBACK.sql \
  --execute \
  --user-confirmed
```

## Post Review Checks

- {'actual_rows_equal_planned_rows': True, 'strict_required_field_compliance': '1240/1240', 'trigger_price_null': 0, 'future_event_time': 0, 'future_trigger_time': 0, 'FULL_TriggerMatched': 0, 'outbox_pending': 1240, 'outbox_delivered': 0, 'outbox_delivering': 0, 'N5_N6_refs': 0}
