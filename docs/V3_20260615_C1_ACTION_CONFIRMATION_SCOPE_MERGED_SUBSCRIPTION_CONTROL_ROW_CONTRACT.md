# V3 20260615 C1 Action-Confirmation Merged Subscription Control-Row Contract

- result: `MERGED_CONTROL_ROW_PREFLIGHT_PASS`
- stage: `V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_MERGED_SUBSCRIPTION_CONTROL_ROW_CONTRACT`
- market_data_run_id: `market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1`
- source_n4_trigger_run_id: `n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- planned_c1_run_id: `today_minute_bar_1m_20260615_until_1005_action_confirmation_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1`
- objects stock/index/board/total: `{'stock': 805, 'index': 1, 'board': 0, 'total': 806}`
- candidate/subscription/pull_plan: `806/806/2`
- source composition: `{'current_subscription': 112, 'scoped_gap_subscription': 694}`
- expected C1 rows: `{'stock': 28175, 'index': 35, 'board': 0, 'total': 28210}`
- P0/P1/P2: `0/0/0`

## Boundary

- market_data_pulled=false
- market_data_fact_written=false
- event_outbox_written=false
- downstream_layers_touched=false
- worker_started=false
- metric/N4/N5/N6 not executed

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_v3_20260615_c1_action_confirmation_scope_merged_subscription_execute.py \
  --dry-run-path docs/V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_MERGED_SUBSCRIPTION_CONTROL_ROW_DRY_RUN.json \
  --json-report-path docs/V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_MERGED_SUBSCRIPTION_CONTROL_ROW_EXECUTE_REPORT.json \
  --markdown-report-path docs/V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_MERGED_SUBSCRIPTION_CONTROL_ROW_EXECUTE_REPORT.md \
  --execute --user-confirmed
```
