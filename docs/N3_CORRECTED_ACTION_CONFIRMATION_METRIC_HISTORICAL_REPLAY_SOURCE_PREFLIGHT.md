# N3 Corrected Metric Historical Replay Source Preflight

- result: `PREFLIGHT_PASS`
- target_run_id: `action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_unit_proof__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- planned rows stock/index/board/total: `550/17/53/620`
- metric_ready / metric_not_ready: `620/0`
- signal distribution: `{'S_SELL': 574, 'B_BUY': 46}`
- current source coverage rows: `112220`
- previous-day source coverage rows: `148800`
- formal unit policy: `formal_amount_chain_thousand_yuan_to_yuan_v1`
- rollback_sql: `sql/N3_corrected_action_confirmation_metric_historical_replay_source_rollback.sql`

## Blockers
- none

## Boundary
- metric executed: `false`
- database written: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- N4/N5/N6 entered: `false`

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_v3_realtime_virtual_metric_writer_once.py --contract-path docs/N3_CORRECTED_ACTION_CONFIRMATION_METRIC_HISTORICAL_REPLAY_SOURCE_CONTRACT.json --preflight-path docs/N3_CORRECTED_ACTION_CONFIRMATION_METRIC_HISTORICAL_REPLAY_SOURCE_PREFLIGHT.json --source-payload-path docs/N3_corrected_action_confirmation_metric_historical_replay_source_payload.json --json-report-path docs/N3_CORRECTED_ACTION_CONFIRMATION_METRIC_HISTORICAL_REPLAY_SOURCE_EXECUTE_REPORT.json --markdown-report-path docs/N3_CORRECTED_ACTION_CONFIRMATION_METRIC_HISTORICAL_REPLAY_SOURCE_EXECUTE_REPORT.md --execute --user-confirmed
```
