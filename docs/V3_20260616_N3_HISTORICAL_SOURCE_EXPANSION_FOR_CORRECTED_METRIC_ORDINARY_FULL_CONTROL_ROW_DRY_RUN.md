# V3_20260616_N3_HISTORICAL_SOURCE_EXPANSION_FOR_CORRECTED_METRIC_ORDINARY_FULL_CONTROL_ROW DRY_RUN

- result: `CONTROL_ROW_PREFLIGHT_PASS`
- control_run_id: `market_data_subscription_20260616_corrected_metric_ordinary_full_source_expansion__condition_layer_20260615_source_20260615_for_20260616_v4`
- candidate/subscription/pull_plan rows: `5648/2824/6`
- source_scope_row_count: `5648`
- required_data_kind_counts: `{'previous_day_minute_bar_1m': 1412, 'minute_bar_1m': 1412}`
- candidate_direction_normalization: `{'applied': True, 'source_mixed_candidate_rows': 2824, 'candidate_rows_before': 2824, 'candidate_rows_after': 5648, 'policy': 'expand_mixed_candidate_rows_to_canonical_buy_sell_v1', 'subscription_rows_preserved': 2824}`
- source_expansion_execute_final_gate_allowed: `False`
- control_row_execute_gate_recommendation: `V3_20260616_N3_HISTORICAL_SOURCE_EXPANSION_FOR_CORRECTED_METRIC_ORDINARY_FULL_CONTROL_ROW_EXECUTE_FINAL_GATE_REVIEW`

## Boundary

- database_written=false
- source_expansion_executed=false
- corrected_metric_executed=false
- outbox/inbox/checkpoint untouched
- N4/N5/N6 not entered

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts \
  python3 \
  scripts/run_v3_scoped_subscription_control_rows_execute.py \
  --dry-run-path \
  docs/V3_20260616_N3_HISTORICAL_SOURCE_EXPANSION_FOR_CORRECTED_METRIC_ORDINARY_FULL_CONTROL_ROW_DRY_RUN.json \
  --expected-run-id \
  market_data_subscription_20260616_corrected_metric_ordinary_full_source_expansion__condition_layer_20260615_source_20260615_for_20260616_v4 \
  --rollback-sql-path \
  sql/V3_20260616_n3_historical_source_expansion_for_corrected_metric_ordinary_full_control_rows_rollback.sql \
  --json-report-path \
  docs/V3_20260616_N3_HISTORICAL_SOURCE_EXPANSION_FOR_CORRECTED_METRIC_ORDINARY_FULL_CONTROL_ROW_EXECUTE_REPORT.json \
  --markdown-report-path \
  docs/V3_20260616_N3_HISTORICAL_SOURCE_EXPANSION_FOR_CORRECTED_METRIC_ORDINARY_FULL_CONTROL_ROW_EXECUTE_REPORT.md \
  --execute \
  --user-confirmed
```
