# V3_20260616_N3_HISTORICAL_SOURCE_EXPANSION_FOR_CORRECTED_METRIC_ORDINARY_FULL CONTRACT

- result: `CONTRACT_PASS`
- target_expansion_run_id: `historical_source_expansion_20260616_until_1401_corrected_metric_ordinary_full__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- records_planned: `621303`
- missing_candidates: `2973`
- quality_visible_excluded_candidates: `4`
- P0/P1/P2: `{'P0': 0, 'P1': 1, 'P2': 0}`
- execute_ready: `true`

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts \
  python3 \
  scripts/run_v3_historical_closed_minute_source_expansion_once.py \
  --payload-path \
  docs/V3_20260616_n3_historical_source_expansion_for_corrected_metric_ordinary_full_payload.json \
  --json-report-path \
  docs/V3_20260616_N3_HISTORICAL_SOURCE_EXPANSION_FOR_CORRECTED_METRIC_ORDINARY_FULL_EXECUTE_REPORT.json \
  --markdown-report-path \
  docs/V3_20260616_N3_HISTORICAL_SOURCE_EXPANSION_FOR_CORRECTED_METRIC_ORDINARY_FULL_EXECUTE_REPORT.md \
  --progress-every \
  100 \
  --execute \
  --user-confirmed \
  --json
```
