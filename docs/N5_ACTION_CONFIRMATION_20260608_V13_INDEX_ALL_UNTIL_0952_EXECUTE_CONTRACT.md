# N5 Action Confirmation 20260608 v13 Index-All Until 09:52 Execute Contract

Result: `CONTRACT_PASS`

This runtime-control contract is read-only. It does not execute N5 and does not write DB rows.

## Input

- source trigger run: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- action run: `action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- consumer: `n5_action_consumer_v1`
- expected N4 outbox rows: `3920`
- `TriggerMatched`: `320`
- `TriggerPendingMarketData`: `3600`
- `TriggerStateChanged`: `0`

N5 action entry is only `TriggerMatched`. `TriggerPendingMarketData` must remain quality-only/state-gate and must not create action facts or N5 outbox rows.

## Planned Writes

- common_action_run: `1`
- common_event_inbox: `3920`
- common_event_consumer_checkpoint: `1997`
- stock_action_fact: `195`
- index_action_fact: `6`
- board_action_fact: `0`
- common_action_event: `201`
- common_event_outbox: `201`
- common_position_state: `0`
- common_position_event: `0`

Planned output events:

- `ActionEligible=201`
- `ActionBlocked=0`
- `ActionExecuted=0`
- `ActionSkipped=0`

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_action_consumer_once.py \
  --source-run-id trigger_projection_matcher_execute_20260608_v13_index_all_until_0952 \
  --action-run-id action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952 \
  --allow-source-run-id trigger_projection_matcher_execute_20260608_v13_index_all_until_0952 \
  --baseline-report-path docs/N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_DRY_RUN.json \
  --expected-read-event-count 3920 \
  --rollback-sql-path sql/N5_action_confirmation_20260608_v13_index_all_until_0952_rollback.sql \
  --json-report-path docs/N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.json \
  --markdown-report-path docs/N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.md \
  --execute --user-confirmed
```

## Rollback

Rollback SQL:

`sql/N5_action_confirmation_20260608_v13_index_all_until_0952_rollback.sql`

- hard-fail before first `DELETE`: pass
- scope only action run and source trigger run: pass
- does not delete N3/N4 facts: pass
- blocks N5 delivered/delivering/downstream refs: pass
- no `CASCADE/DROP/TRUNCATE`: pass

## Boundary

- runtime_control does not execute command
- rollback not executed
- N4 outbox not consumed or updated in this gate
- N6 not entered
- worker not started
- no delivery/push/voice/mobile
- no sim/position/pnl/real_trade
- no proposal/order/trade
- old system untouched

Next gate:

`N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_FINAL_GATE_REVIEW`
