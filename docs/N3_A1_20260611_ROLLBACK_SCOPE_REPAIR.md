# N3-A1 20260611 Rollback Scope Repair

Result: `REPAIR_PASS`

```json
{
  "gate": "N3_A1_20260611_ROLLBACK_SCOPE_REPAIR_GATE",
  "result": "REPAIR_PASS",
  "generated_at": "2026-06-10T13:22:31.061782+00:00",
  "rollback_proof": {
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
  },
  "stage1_persisted_rows": {
    "common_market_data_run": 1,
    "common_market_data_quality_item": 34,
    "common_market_data_subscription_candidate": 5046,
    "common_market_data_subscription": 2666,
    "common_market_data_pull_plan": 9
  },
  "stage2_baseline": {
    "common_market_data_run": 0,
    "common_market_data_quality_item": 0,
    "stock_minute_bar_1m": 0,
    "index_minute_bar_1m": 0,
    "board_minute_bar_1m": 0,
    "stock_previous_day_minute_preload_status": 0,
    "index_previous_day_minute_preload_status": 0,
    "board_previous_day_minute_preload_status": 0
  },
  "forbidden_scope_proof": {
    "execute_stage2": false,
    "rollback_executed": false,
    "n3_b_c_b2_n4_n5_n6_touched": false,
    "worker_started": false
  }
}
```
