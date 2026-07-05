# N3-A1 20260611 Stage 2 Execute Final Gate Review

Result: `PASS`

- subscription_run_id: `market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- preload_run_id: `previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- contract stage: `N3-A1-preflight`
- Stage 2 baseline total: `0`
- refs total: `0`
- rollback_safe: `True`

## Expected Rows

```json
{
  "objects": {
    "stock": 250,
    "index": 19,
    "board": 14,
    "total": 283
  },
  "minute_rows": {
    "stock": 60000,
    "index": 4560,
    "board": 3360,
    "total": 67920
  }
}
```

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_previous_day_minute_preload_execute.py \
  --contract-path docs/N3_A1_20260611_PREVIOUS_DAY_MINUTE_PRELOAD_EXECUTE_CONTRACT.json \
  --historical-preload \
  --source-subscription-run-id market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1 \
  --preload-run-id previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1 \
  --data-trade-date 20260610 \
  --execute \
  --user-confirmed \
  --json-report-path docs/fastlane/20260611/04_n3_a1_bundle_execute_report.json \
  --markdown-report-path docs/fastlane/20260611/04_n3_a1_bundle_execute_report.md
```

## Rollback Proof

```json
{
  "path": "sql/N3_A1_previous_day_minute_20260611_rollback.sql",
  "hard_fail_before_delete": true,
  "covers_stage1_subscription_control": true,
  "covers_stage2_preload": true,
  "no_event_infra_dml": true,
  "forbidden_event_dml": [],
  "no_drop_truncate_cascade": true,
  "subscription_run_id_scoped": true,
  "preload_run_id_scoped": true,
  "source_condition_run_id_scoped": true,
  "guards_downstream_refs": true,
  "passed": true
}
```
