# N5 Action 20260616 After N4 Trigger Price Repair Preflight

- result: `PREFLIGHT_PASS`
- layer_role: `N5_action`
- source_trigger_run_id: `v3_n4_trigger_replay_20260616_until_1401_v1`
- action_run_id: `v3_n5_action_replay_20260616_after_n4_trigger_price_repair_v1`
- consumer_name: `n5_action_consumer_v1_20260616_trigger_price_repair_replay`
- metric_run_id: `action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- execute_authorized: `false`
- execute source event filter: `TriggerMatched`

## Source N4 Proof

- N4 outbox visibility: `TriggerMatched=540`, `TriggerPendingMarketData=4158`, `TriggerStateChanged=0`
- N4 delivered/delivering: `0/0`
- common_trigger_match.trigger_price null: `0`
- N4 outbox payload trigger_price_source_ok: `540/540`

## TriggerMatched-only Entry Proof

- execute consume scope: `TriggerMatched=540`
- pending non-entry rows: `TriggerPendingMarketData=4158`
- pending consumed in execute scope: `false`
- pending action fact/event/outbox: `0`

## Metric Join Proof

- coverage: `540/540`
- metric_missing: `0`

## Planned N5 Writes

```json
{
  "common_action_run": 1,
  "common_action_quality_item": 0,
  "stock_action_fact": 478,
  "index_action_fact": 18,
  "board_action_fact": 44,
  "common_action_event": 540,
  "common_event_outbox": 540,
  "common_event_inbox": 540,
  "common_event_consumer_checkpoint": 452,
  "accepted_event_count": 540,
  "common_position_state": 0,
  "common_position_event": 0
}
```

## Planned Event Distribution

```json
{
  "ActionEligible": 0,
  "ActionBlocked": 522,
  "ActionExecuted": 18,
  "ActionSkipped": 0
}
```

## Rollback

- rollback_sql_path: `sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql`
- hard-fail before DELETE/UPDATE: required
- guard N5 outbox delivered/delivering: required
- guard downstream inbox/checkpoint and N6/user refs: required
- does not delete N4/N3 facts

## Allowed Execute Command For Final Gate

```bash
PYTHONPATH=src:scripts python3 scripts/run_action_consumer_once.py --source-trigger-run-id v3_n4_trigger_replay_20260616_until_1401_v1 --action-run-id v3_n5_action_replay_20260616_after_n4_trigger_price_repair_v1 --consumer-name n5_action_consumer_v1_20260616_trigger_price_repair_replay --baseline-report-path docs/V3_20260616_N5_ACTION_AFTER_N4_TRIGGER_PRICE_REPAIR_CONTRACT.json --expected-read-event-count 540 --allow-source-run-id v3_n4_trigger_replay_20260616_until_1401_v1 --source-event-type TriggerMatched --json-report-path docs/V3_20260616_N5_ACTION_AFTER_N4_TRIGGER_PRICE_REPAIR_EXECUTE_REPORT.json --markdown-report-path docs/V3_20260616_N5_ACTION_AFTER_N4_TRIGGER_PRICE_REPAIR_EXECUTE_REPORT.md  --rollback-sql-path sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql --execute --user-confirmed
```
