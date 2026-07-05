# N4 Projection Matcher 20260608 Until 15:00 FULL Repair Retry Post Review

- result: POST_REVIEW_PASS
- execute_run_id: `trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry`
- old_lineage_reference_only: `trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry`

## Execute Proof Summary

```json
{
  "runner_result": "EXECUTED",
  "execute_report_result": "EXECUTE_PASS",
  "run_row": {
    "status": "passed",
    "p0_count": 0,
    "p1_count": 0,
    "p2_count": 0,
    "worker_started": false,
    "action_layer_touched": false,
    "user_layer_touched": false,
    "voice_touched": false,
    "sim_touched": false,
    "real_trade_touched": false,
    "market_data_pulled": false,
    "trigger_state_row_count": 556,
    "trigger_match_row_count": 556,
    "trigger_event_outbox_count": 556
  },
  "side_effects": {
    "checkpoint_written": true,
    "common_event_inbox_written": true,
    "downstream_layers_touched": false,
    "event_outbox_written": true,
    "market_data_pulled": false,
    "n3_outbox_status_updated": false,
    "read_only_database_checks": true,
    "trigger_match_written": true,
    "trigger_state_written": true,
    "will_execute_sql": true,
    "worker_started": false,
    "writes_performed": true
  }
}
```

## Row Count Proof

```json
{
  "expected": {
    "common_trigger_run": 1,
    "common_trigger_quality_item": 10,
    "common_trigger_state": 556,
    "common_trigger_match": 556,
    "common_event_outbox": 556,
    "common_event_inbox": 2155,
    "common_event_consumer_checkpoint": 2155
  },
  "actual": {
    "common_event_consumer_checkpoint": 2155,
    "common_event_inbox": 2155,
    "common_event_outbox": 556,
    "common_trigger_match": 556,
    "common_trigger_quality_item": 10,
    "common_trigger_run": 1,
    "common_trigger_state": 556
  }
}
```

## Event Proof

```json
{
  "outbox_status": [
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
  "hint_distribution": {
    "BUY_HINT": 116,
    "SELL_HINT": 6
  }
}
```

## FULL Proof

```json
{
  "full_candidate_rows": 86,
  "buy_full": 47,
  "sell_full": 39,
  "full_trigger_matched": 0,
  "full_pending": 0,
  "full_no_op": 86,
  "full_blocked": 0,
  "full_n2_context_proof_missing": 0,
  "negative_guard_violations": {
    "full_trigger_period_30m": 0,
    "full_period_arrays_contain_30m": 0,
    "full_trigger_kind_hint": 0,
    "full_30m_mark_candidate": 0,
    "full_trigger_price_null": 0
  },
  "conclusion": "FULL reached matcher with context proof; no D transition formed a legal FULL TriggerMatched in this run, so no_op is expected."
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
    "invalid_signal_type": 0,
    "trigger_price_null": 0,
    "n5_entry_allowed_invalid": 0,
    "trigger_kind_missing": 0,
    "action_mark_present": 0
  },
  "state_semantic_scan": {
    "state_trigger_live_false": 0,
    "state_status_not_matched": 0,
    "state_primary_30m": 0,
    "state_all_periods_contains_30m": 0,
    "state_trigger_period_30m": 122,
    "state_hint_30m": 122
  },
  "v4_violations": 0,
  "payload_only_policy_note": "N5 entry proof is canonical common_event_outbox.payload_json; common_trigger_match.raw_json is not treated as N5 input proof for this route."
}
```

## Upstream Preservation Proof

```json
{
  "n3_market_snapshot_outbox_status": {
    "pending": 2155
  },
  "n3_snapshot_projection_fact_counts": {
    "board_projection_rows": 127,
    "board_snapshot_rows": 127,
    "index_projection_rows": 83,
    "index_snapshot_rows": 83,
    "stock_projection_rows": 1945,
    "stock_snapshot_rows": 1945
  },
  "n3_outbox_status_updated": false,
  "n1_n2_facts_changed_by_this_gate": false
}
```

## Old Lineage Preservation Proof

```json
{
  "old_n4_run_present": 1,
  "old_n4_outbox_status": [
    {
      "event_type": "TriggerMatched",
      "status": "pending",
      "row_count": 556
    }
  ],
  "old_n5_n6_lineage_mutated_by_this_gate": false
}
```

## Downstream Clean Proof

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
  "n5_n6_outbox_consumption": false,
  "worker_started": false,
  "delivery_push_voice_mobile": false,
  "sim_position_pnl_real_trade": false,
  "proposal_order_trade": false
}
```

## Rollback Proof

```json
{
  "path": "sql/N4_projection_matcher_20260608_until_1500_full_repair_retry_rollback.sql",
  "exists": true,
  "executed": false,
  "hard_fail_before_first_delete_or_update": true,
  "guards_delivered_delivering": true,
  "guards_n5_n6_user_sim_order_trade_position_refs": true,
  "delete_scope_only_retry_n4_rows": true,
  "no_cascade_drop_truncate": true,
  "preserves_old_lineage_and_upstream_facts": true
}
```

## Forbidden Scope Proof

```json
{
  "sql_executed_in_this_gate": false,
  "database_written_in_this_gate": false,
  "outbox_inbox_checkpoint_consumed_or_updated_in_this_gate": false,
  "n5_entered": false,
  "n6_entered": false,
  "worker_started": false,
  "old_system_touched": false
}
```

## Blockers

```json
[]
```
