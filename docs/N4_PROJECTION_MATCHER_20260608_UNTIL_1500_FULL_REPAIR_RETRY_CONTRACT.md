# N4 Projection Matcher 20260608 Until 15:00 FULL Repair Retry Contract

- result: CONTRACT_PASS
- layer_role: N4_trigger
- execute_run_id: `trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry`
- trigger_context_run_id: `trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- snapshot_run_id: `realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- projection_run_id: `realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`

## Source Readiness Proof

```json
{
  "full_semantic_repair_post_review": "POST_REVIEW_PASS",
  "full_context_proof_alignment": "ALIGNMENT_PASS",
  "n4_context_run_status": "passed",
  "n3_snapshot_run": {
    "status": "passed",
    "p0_count": 0,
    "p1_count": 0,
    "p2_count": 0
  },
  "n3_projection_run": {
    "status": "passed",
    "p0_count": 0,
    "p1_count": 4,
    "p2_count": 0
  },
  "n3_projection_fact_rows": {
    "board": 127,
    "index": 83,
    "stock": 1945
  },
  "n3_market_snapshot_outbox_status": {
    "pending": 2155
  }
}
```

## Dry-run Summary

```json
{
  "result": "DRY_RUN_PASS",
  "candidate_count": 4677,
  "matched_count": 556,
  "pending_count": 0,
  "not_matched_signal_count": 4121,
  "matched_by_signal_type": {
    "B_BUY": 415,
    "S_SELL": 141
  },
  "matched_by_trigger_mark_candidate": {
    "30m_shrink": 6,
    "30m_volume": 116,
    "normal": 434
  },
  "matched_by_trigger_kind": {
    "trigger": 434,
    "hint": 122
  },
  "trigger_period_distribution": {
    "D": 74,
    "W": 84,
    "Q": 117,
    "30m": 122,
    "M": 47,
    "Y": 112
  },
  "primary_trigger_period_distribution": {
    "D": 74,
    "W": 84,
    "Q": 117,
    "null": 122,
    "M": 47,
    "Y": 112
  },
  "ordinary_buy_sell_matched_count": 434,
  "hint_matched_count": 122,
  "hint_matched_distribution": {
    "BUY_HINT": 116,
    "SELL_HINT": 6
  },
  "p0_count": 0,
  "p1_count": 0,
  "p2_count": 0
}
```

## FULL Semantic Proof

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
  "full_outcome_distribution": {
    "no_op": 86
  },
  "full_d_reason_distribution": {
    "transition_or_chain_not_triggered": 86
  },
  "full_d_current_transition_distribution": {
    "volume_up": 30,
    "other": 53,
    "low_volume_down": 3
  },
  "full_d_trigger_amount_chain_pass_distribution": {
    "True": 86
  },
  "source_context_missing": {
    "original_condition_key_missing": 0,
    "original_condition_key_mismatch": 0,
    "source_condition_pool_id_missing": 0,
    "source_condition_basis_id_missing": 0,
    "source_minute_target_scope_id_missing": 0,
    "context_snapshot_id_missing": 0,
    "period_trigger_baseline_trace_missing": 0
  }
}
```

## Negative Guard Proof

```json
{
  "full_n2_context_missing": 0,
  "full_trigger_period_30m": 0,
  "full_period_arrays_contain_30m": 0,
  "full_trigger_kind_hint": 0,
  "full_30m_mark_candidate": 0,
  "full_trigger_price_null": 0,
  "ordinary_self_derived_full": 0,
  "matched_invalid_signal_type": 0,
  "matched_30m_in_formal_period_arrays": 0,
  "ordinary_trigger_period_30m": 0,
  "trigger_matched_missing_n5_entry_allowed": 0,
  "trigger_matched_missing_price": 0,
  "trigger_matched_action_mark_present": 0
}
```

## Baseline Proof

```json
{
  "context_run_status": "passed",
  "old_n4_outbox_rows": "556",
  "old_n4_run_rows": "1",
  "target_common_trigger_match": "0",
  "target_common_trigger_quality_item": "0",
  "target_common_trigger_run": "0",
  "target_common_trigger_state": "0",
  "target_n4_common_event_consumer_checkpoint": "0",
  "target_n4_common_event_inbox": "0",
  "target_n4_common_event_outbox": "0",
  "target_n5_common_action_event_refs": "0",
  "target_n5_common_action_run_refs": "0",
  "target_n6_virtual_order_refs": "0",
  "target_n6_virtual_position_refs": "0",
  "target_n6_virtual_trade_refs": "0",
  "target_user_notification_refs": "0",
  "target_user_signal_card_refs": "0",
  "target_user_signal_projection_refs": "0",
  "target_user_sim_position_refs": "0",
  "target_user_sim_trade_refs": "0"
}
```

## Contract / Preflight Proof

```json
{
  "preflight": {
    "result": "PREFLIGHT_PASS",
    "accepted_source_event_count": 2155,
    "matched_output_count": 556,
    "pending_output_count": 0,
    "inbox_write_plan_count": 2155,
    "checkpoint_write_plan_count": 2155,
    "n3_outbox_status_update_count": 0,
    "planned_event_types": [
      "TriggerMatched"
    ],
    "p0_count": 0,
    "p1_count": 0,
    "p2_count": 0,
    "quality_item_count": 10,
    "execute_contract_lineage": {
      "consumer_name": "n4_projection_matcher_consumer_v1_until_1500_full_repair_retry",
      "trigger_context_run_id": "trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute",
      "projection_run_id": "realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute",
      "snapshot_run_id": "realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"
    }
  },
  "planned_writes_if_executed": {
    "common_trigger_run": 1,
    "common_trigger_quality_item": 10,
    "common_trigger_state": 556,
    "common_trigger_match": 556,
    "common_event_outbox": 556,
    "common_event_inbox": 2155,
    "common_event_consumer_checkpoint": 2155,
    "TriggerMatched": 556,
    "TriggerPendingMarketData": 0,
    "TriggerStateChanged": 0
  }
}
```

## Rollback Proof

```json
{
  "path": "sql/N4_projection_matcher_20260608_until_1500_full_repair_retry_rollback.sql",
  "raise_exception_before_first_delete_or_update": true,
  "first_raise_index": 760,
  "first_mutation_index": 5398,
  "contains_drop_truncate_cascade": false,
  "guards": {
    "delivered_or_delivering_outbox": true,
    "n5_action_run": true,
    "n5_action_event": true,
    "user_signal_projection": true,
    "user_signal_card": true,
    "user_notification_queue": true,
    "user_sim": true,
    "n6_virtual": true
  },
  "delete_scope": [
    "common_event_outbox source_layer=N4_trigger source_run_id=retry run",
    "common_trigger_match run_id=retry run",
    "common_trigger_state run_id=retry run",
    "common_trigger_quality_item run_id=retry run",
    "common_event_inbox consumer+execute_run_id scoped",
    "common_event_consumer_checkpoint consumer+execute_run_id scoped",
    "common_trigger_run run_id=retry run"
  ]
}
```

## Forbidden Scope Proof

```json
{
  "n4_matcher_executed": false,
  "business_db_write": false,
  "n3_outbox_status_updated": false,
  "outbox_inbox_checkpoint_consumed_or_updated": false,
  "n5_entered": false,
  "n6_entered": false,
  "worker_started": false,
  "delivery_push_voice_mobile": false,
  "sim_position_pnl_real_trade": false,
  "proposal_order_trade": false,
  "old_system_touched": false
}
```

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_projection_matcher_once.py \
  --execute --user-confirmed \
  --execute-run-id trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry \
  --trigger-context-run-id trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --snapshot-run-id realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --projection-run-id realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --consumer-name n4_projection_matcher_consumer_v1_until_1500_full_repair_retry \
  --dry-run-report-path docs/N4_PROJECTION_MATCHER_20260608_UNTIL_1500_FULL_REPAIR_RETRY_DRY_RUN.json \
  --json-report-path docs/N4_PROJECTION_MATCHER_20260608_UNTIL_1500_FULL_REPAIR_RETRY_EXECUTE_REPORT.json \
  --markdown-report-path docs/N4_PROJECTION_MATCHER_20260608_UNTIL_1500_FULL_REPAIR_RETRY_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_projection_matcher_20260608_until_1500_full_repair_retry_rollback.sql
```

## Blockers

```json
[]
```
