# N4 Worker Bounded Smoke 20260608 Unified Output Probe

Smoke run: `n4_worker_bounded_smoke_20260608_unified_output_probe`
Consumer: `n4_trigger_worker_v1_bounded_smoke_probe`

Result: `PASS`

Preflight: `PREFLIGHT_PASS`; P0/P1/P2: `0/0/0`.

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_n4_worker_bounded_smoke_once.py \
  --contract-path docs/N4_WORKER_BOUNDED_SMOKE_20260608_UNIFIED_OUTPUT_PROBE_CONTRACT.json \
  --smoke-run-id n4_worker_bounded_smoke_20260608_unified_output_probe \
  --consumer-name n4_trigger_worker_v1_bounded_smoke_probe \
  --source-run-id realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --source-event-type MarketSnapshotUpdated \
  --source-trade-date 20260608 \
  --max-events 5 \
  --max-runtime-seconds 60 \
  --heartbeat-interval-seconds 10 \
  --stop-file tmp/n4_worker_bounded_smoke_20260608_unified_output_probe.stop \
  --status-json docs/N4_WORKER_BOUNDED_SMOKE_20260608_UNIFIED_OUTPUT_PROBE_STATUS.json \
  --json-report-path docs/N4_WORKER_BOUNDED_SMOKE_20260608_UNIFIED_OUTPUT_PROBE_EXECUTE_REPORT.json \
  --markdown-report-path docs/N4_WORKER_BOUNDED_SMOKE_20260608_UNIFIED_OUTPUT_PROBE_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_worker_bounded_smoke_20260608_unified_output_probe_rollback.sql \
  --execute \
  --user-confirmed
```

## Rollback

Rollback SQL: `sql/N4_worker_bounded_smoke_20260608_unified_output_probe_rollback.sql`; hard-fail before first DELETE/UPDATE: `True`.
