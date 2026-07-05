# N4 20260605 V4 Corrected Execute Contract

- result: CONTRACT_PASS
- execute_run_id: trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
- dry_run_artifact_path: docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_DRY_RUN.json
- rollback_sql_path: sql/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_ROLLBACK.sql

## Planned Writes

- common_trigger_run: 1
- common_trigger_quality_item: 4
- common_trigger_state: 605
- common_trigger_match: 605
- common_event_outbox: 605
- TriggerMatched: 605
- TriggerPendingMarketData: 0
- TriggerStateChanged: 0

## Blocked Candidates

- total: 291
- by_reason: {'missing trigger_price': 275, 'missing trigger_kind': 0, 'missing triggered_periods': 275, 'missing n5_entry_allowed': 0, 'future event_time': 0, 'future trigger_time': 0, 'FULL forbidden': 23, 'invalid signal_type': 0, 'invalid N5 entry': 0}
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
- baseline_source_trigger_baseline

## N5 Entry Contract

- required: TriggerMatched + B_BUY/S_SELL + current_status=matched + trigger_live=true + n5_entry_allowed=true
- invalid_n5_entry_count: 0

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_n4_20260605_v4_corrected_execute_once.py \
  --execute-run-id trigger_execute_20260605_condition_layer_20260604_source_20260604_v1 \
  --dry-run-json-path docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_DRY_RUN.json \
  --contract-path docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_CONTRACT.json \
  --preflight-path docs/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_PREFLIGHT.json \
  --rollback-sql-path sql/N4_20260605_V4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_ROLLBACK.sql \
  --execute \
  --user-confirmed
```

## Post Review Checks

- {'actual_rows_equal_planned_rows': True, 'strict_required_field_compliance': '605/605', 'trigger_price_null': 0, 'future_event_time': 0, 'future_trigger_time': 0, 'FULL_TriggerMatched': 0, 'trigger_kind_missing': 0, 'triggered_periods_missing': 0, 'n5_entry_allowed_missing': 0, 'baseline_source_not_trigger_baseline': 0, 'outbox_pending': 605, 'outbox_delivered': 0, 'outbox_delivering': 0, 'N5_N6_refs': 0}
