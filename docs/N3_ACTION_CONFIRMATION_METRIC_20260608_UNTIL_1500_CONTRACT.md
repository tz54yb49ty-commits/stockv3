# N3 Action-Confirmation Metric 20260608 Until 15:00 Contract

Status: CONTRACT_PASS

```text
metric_run_id=action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry
latest_closed_minute=2026-06-08T15:00:00+08:00
planned_rows stock/index/board/total=113/6/3/122
metric_ready_expected=122
N4 TriggerMatched coverage=122/122
writes_outbox=false
consumes_outbox=false
enters_n4_n5_n6=false
```

Allowed execute command:

```bash
PYTHONPATH=src:scripts python3 scripts/run_n3_action_confirmation_metric_materialization_execute.py --payload-path docs/N3_action_confirmation_metric_20260608_until_1500_payload.json --contract-path docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_CONTRACT.json --execute --user-confirmed --report-path docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_EXECUTE_REPORT.json --markdown-report-path docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_EXECUTE_REPORT.md
```
