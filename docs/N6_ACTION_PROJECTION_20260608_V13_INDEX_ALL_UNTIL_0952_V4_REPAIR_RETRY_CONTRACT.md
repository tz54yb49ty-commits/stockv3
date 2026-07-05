# N6 Action Projection 20260608 v13 Index-All Until 09:52 v4 Repair Retry Contract

Status: `CONTRACT_PASS`

Layer role for future execute: `N6_user`. Runtime control is not authorized to execute.

## Input Policy

Only consume pending `ActionEligible` from N5 outbox for:

`action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry`

No N4/N3/N2/N1 naked fact substitution. No legacy action event consumption.

## Planned Writes

Allowed tables only: `user_projection_run`, `user_signal_projection`, `user_signal_card`.

```json
{
  "user_projection_run": 1,
  "user_signal_projection": 119,
  "user_signal_card": 119,
  "user_notification_queue": 0,
  "user_signal_decision": 0,
  "user_session": 0,
  "user_watchlist": 0,
  "user_watchlist_item": 0,
  "user_sim_order": 0,
  "user_sim_trade": 0,
  "user_sim_position": 0,
  "n5_outbox_status_updates": 0,
  "n6_inbox_checkpoint": 0
}
```

## HINT 30m Trace

```json
{
  "condition_key": "BUY_HINT/SELL_HINT",
  "original_condition_key": "BUY_HINT/SELL_HINT",
  "trigger_period": "30m",
  "primary_trigger_period": null,
  "triggered_periods": [],
  "all_trigger_periods": [],
  "action_state": "eligible",
  "action_mark": "none_or_null",
  "trigger_mark_candidate": "30m_volume/30m_shrink",
  "required_trace_fields": [
    "source_action_event_id",
    "source_trigger_event_id",
    "source_trigger_match_id"
  ]
}
```

## Rollback

- SQL: `sql/N6_projection_20260608_v13_index_all_until_0952_v4_repair_retry_rollback.sql`
- delete order: `user_notification_queue -> user_signal_card -> user_signal_projection -> user_projection_run`
- no N5/N4/N3/N2/N1 mutation

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_n6_projection_once.py --projection-run-id user_projection_shadow_20260608_v13_index_all_until_0952_v4_repair_retry__action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry --source-action-run-id action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry --contract-json-path docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_CONTRACT.json --preflight-json-path docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_PREFLIGHT.json --expected-n5-outbox-count ActionEligible:pending=119 --execute --user-confirmed --json > docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_EXECUTE_REPORT.json
```
