# N3 Action Confirmation Metric 20260608 Trigger-Time Aligned Until 15:00

- metric_run_id: `action_confirmation_metric_20260608_trigger_time_aligned_until_1500__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry`
- trigger_run_id: `trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry`
- expected rows: stock=113 index=6 board=3 total=122
- metric_ready: 122
- trigger minute distribution: `{'09:43': 28, '09:44': 81, '09:45': 10, '14:59': 3}`
- result: `PREFLIGHT_PASS`
- rollback SQL: `sql/N3_action_confirmation_metric_20260608_trigger_time_aligned_until_1500_rollback.sql`

## Boundary

This artifact is N3-only. It does not write N4/N5/N6, does not consume outbox/inbox/checkpoint, does not start worker, and does not touch delivery/push/voice/mobile/sim/order/trade/position/PnL.

## Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_n3_action_confirmation_metric_materialization_execute.py --payload-path docs/N3_action_confirmation_metric_20260608_trigger_time_aligned_until_1500_payload.json --contract-path docs/N3_ACTION_CONFIRMATION_METRIC_20260608_TRIGGER_TIME_ALIGNED_UNTIL_1500_CONTRACT.json --execute --user-confirmed --report-path docs/N3_ACTION_CONFIRMATION_METRIC_20260608_TRIGGER_TIME_ALIGNED_UNTIL_1500_EXECUTE_REPORT.json --markdown-report-path docs/N3_ACTION_CONFIRMATION_METRIC_20260608_TRIGGER_TIME_ALIGNED_UNTIL_1500_EXECUTE_REPORT.md
```

## Contract

Contract is payload-driven and requires `--execute --user-confirmed` at runner time.
