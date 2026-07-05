# N4 Projection Matcher 20260608 Until 15:00 FULL Repair Retry Execute Report

- result: EXECUTE_PASS
- execute_run_id: `trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry`
- runner_result: `EXECUTED`
- common_trigger_run.status: `passed`
- P0/P1/P2: `0/0/0`

## Row Count Proof

```json
{
  "common_event_consumer_checkpoint": 2155,
  "common_event_inbox": 2155,
  "common_event_outbox": 556,
  "common_trigger_match": 556,
  "common_trigger_quality_item": 10,
  "common_trigger_run": 1,
  "common_trigger_state": 556,
  "n3_delivered": 0,
  "n3_delivering": 0,
  "n3_pending": 2155,
  "old_n4_outbox_rows": 556,
  "old_n4_run_rows": 1
}
```

## Event Proof

```json
{
  "outbox": [
    {
      "event_type": "TriggerMatched",
      "status": "pending",
      "row_count": 556
    }
  ],
  "signal_distribution": {
    "B_BUY": 415,
    "S_SELL": 141
  },
  "trigger_mark_candidate_distribution": {
    "30m_shrink": 6,
    "30m_volume": 116,
    "normal": 434
  },
  "special_condition_distribution": {
    "BUY_HINT": 116,
    "SELL_HINT": 6
  }
}
```

## FULL Proof

```json
{
  "full_candidate_rows": 86,
  "full_distribution": {
    "BUY:FULL": 47,
    "SELL:FULL": 39
  },
  "full_matched_count": 0,
  "full_pending_count": 0,
  "full_no_op_count": 86,
  "full_blocked_count": 0,
  "full_n2_context_proof_missing": 0,
  "note": "FULL proof entered matcher; this run produced no FULL TriggerMatched because D transition did not newly trigger, so no_op is expected."
}
```

## Semantic Proof

```json
{
  "match_fact_semantic_scan": {
    "invalid_signal_type": 0,
    "trigger_price_null": 0,
    "full_trigger_matched": 0,
    "ordinary_trigger_period_30m": 0,
    "formal_period_arrays_contain_30m": 0
  },
  "outbox_payload_semantic_scan": {
    "outbox_invalid_signal_type": 0,
    "outbox_trigger_price_null": 0,
    "outbox_n5_entry_allowed_invalid": 0,
    "outbox_trigger_kind_missing": 0,
    "outbox_action_mark_present": 0
  },
  "state_semantic_scan": {
    "state_trigger_live_false": 0,
    "state_status_not_matched": 0,
    "state_primary_30m": 0,
    "state_all_periods_contains_30m": 0,
    "state_trigger_period_30m": 122,
    "state_hint_30m": 122
  },
  "payload_only_policy_note": "N5 entry proof is canonical common_event_outbox.payload_json; common_trigger_match.raw_json is not used as N5 input proof for this route."
}
```

## Upstream Preservation Proof

```json
{
  "n3_outbox_snapshot": {
    "n3_pending": 2155,
    "n3_delivering": 0,
    "n3_delivered": 0
  },
  "old_n4_lineage": {
    "old_n4_run_rows": 1,
    "old_n4_outbox_rows": 556
  },
  "n3_outbox_status_updated": false,
  "n1_n2_n3_facts_touched": false
}
```

## Downstream Forbidden Proof

```json
{
  "n5_action_run_refs": 0,
  "n5_action_event_refs": 0,
  "user_signal_projection_refs": 0,
  "user_signal_card_refs": 0,
  "user_notification_refs": 0,
  "user_sim_position_refs": 0,
  "user_sim_trade_refs": 0,
  "n6_virtual_order_refs": 0,
  "n6_virtual_position_refs": 0,
  "n6_virtual_trade_refs": 0,
  "n5_execute": false,
  "n6_execute": false,
  "worker_started": false,
  "delivery_push_voice_mobile": false,
  "sim_position_pnl_real_trade": false,
  "proposal_order_trade": false,
  "old_system_touched": false
}
```

## Rollback Proof

```json
{
  "path": "sql/N4_projection_matcher_20260608_until_1500_full_repair_retry_rollback.sql",
  "executed": false,
  "exists": true,
  "hard_fail_before_first_delete_or_update": true,
  "guards_delivered_delivering": true,
  "guards_n5_n6_user_sim_order_trade_position_refs": true,
  "no_cascade_drop_truncate": true
}
```
