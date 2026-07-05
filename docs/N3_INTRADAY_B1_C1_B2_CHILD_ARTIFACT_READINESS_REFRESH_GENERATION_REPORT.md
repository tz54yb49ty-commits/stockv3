# N3 Intraday B1/C1/B2 Dynamic Child Artifact Generation Report

- result: `ARTIFACT_WRITE_PASS`
- for_trade_date: `20260611`
- latest_closed_minute_hhmm: `0931`
- subscription_run_id: `market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- preload_run_id: `previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`

## Generated Artifacts
### B1
- `execute_contract_json`: `docs/N3_B1_realtime_snapshot_20260611_until_0931_execute_contract.json`
- `execute_contract_md`: `docs/N3_B1_realtime_snapshot_20260611_until_0931_execute_contract.md`
- `execute_readiness_json`: `docs/N3_B1_realtime_snapshot_20260611_until_0931_execute_readiness.json`
- `execute_readiness_md`: `docs/N3_B1_realtime_snapshot_20260611_until_0931_execute_readiness.md`
- `rollback_sql`: `sql/N3_B1_realtime_snapshot_20260611_until_0931_rollback.sql`
- `json_report_path`: `docs/N3_B1_realtime_snapshot_20260611_until_0931_execute_report.json`
- `markdown_report_path`: `docs/N3_B1_REALTIME_SNAPSHOT_20260611_until_0931_EXECUTE_REPORT.md`
- `pre_backup_path`: `docs/N3_B1_realtime_snapshot_20260611_until_0931_backup_before.json`
- `post_backup_path`: `docs/N3_B1_realtime_snapshot_20260611_until_0931_backup_after.json`
### C1
- `c0_dry_run_json`: `docs/N3_C0_today_minute_bar_1m_20260611_until_0931_dry_run.json`
- `c0_dry_run_md`: `docs/N3_C0_today_minute_bar_1m_20260611_until_0931_dry_run.md`
- `rollback_sql`: `sql/N3_C1_today_minute_bar_1m_20260611_until_0931_rollback.sql`
- `json_report_path`: `docs/N3_C1_today_minute_bar_1m_20260611_until_0931_execute_report.json`
- `markdown_report_path`: `docs/N3_C1_TODAY_MINUTE_BAR_1M_20260611_until_0931_EXECUTE_REPORT.md`
- `pre_backup_path`: `docs/N3_C1_today_minute_bar_1m_20260611_until_0931_backup_before.json`
- `post_backup_path`: `docs/N3_C1_today_minute_bar_1m_20260611_until_0931_backup_after.json`
### B2
- `dry_run_json`: `docs/N3_B2_realtime_projection_20260611_until_0931_dry_run.json`
- `dry_run_md`: `docs/N3_B2_realtime_projection_20260611_until_0931_dry_run.md`
- `execute_contract_json`: `docs/N3_B2_realtime_projection_20260611_until_0931_execute_contract.json`
- `execute_contract_md`: `docs/N3_B2_realtime_projection_20260611_until_0931_execute_contract.md`
- `execute_preflight_json`: `docs/N3_B2_realtime_projection_20260611_until_0931_execute_preflight.json`
- `execute_preflight_md`: `docs/N3_B2_realtime_projection_20260611_until_0931_execute_preflight.md`
- `rollback_sql`: `sql/N3_B2_realtime_projection_20260611_until_0931_rollback.sql`
- `json_report_path`: `docs/N3_B2_realtime_projection_20260611_until_0931_execute_report.json`
- `markdown_report_path`: `docs/N3_B2_REALTIME_PROJECTION_20260611_until_0931_EXECUTE_REPORT.md`

## Forbidden Scope

```text
database_connected=false
subprocess_executed=false
supervisor_executed=false
b1_c1_b2_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
worker_started=false
old_system_touched=false
```
