# 20260611 N1 -> N3-A1 Fast Lane Catch-up Closeout

Result: `FAST_LANE_CATCHUP_PASS`

- for_trade_date: `20260611`
- source_trade_date: `20260610`
- route: `manual_layer_sequence_with_fastlane_artifacts`
- Fast Lane wrapper real orchestration: `not_complete_report_only_gap`

## N1 Baseline

```json
{
  "20260609": {
    "combined_rows": 86853,
    "official_rows": 6024,
    "condition_source_rows": 80829,
    "p0_failed": 0,
    "event_refs_total": 0,
    "downstream_refs_total": 0,
    "rollback_safe": true
  },
  "20260610": {
    "combined_rows": 86844,
    "official_rows": 6021,
    "condition_source_rows": 80823,
    "p0_failed": 0,
    "event_refs_total": 0,
    "downstream_refs_total_at_n1_post_review": 0,
    "rollback_safe": true
  }
}
```

## N2 Baseline

```json
{
  "run_id": "condition_layer_20260610_source_20260610_for_20260611_v1",
  "status": {
    "run_status": "passed_active",
    "p0_count": 0,
    "p1_count": 6,
    "p2_count": 3
  },
  "row_counts": {
    "common_condition_run": 1,
    "common_condition_quality_item": 106,
    "stock_monitor_target": 5510,
    "stock_condition_basis": 5510,
    "index_monitor_target": 83,
    "index_condition_basis": 83,
    "board_monitor_target": 428,
    "board_condition_basis": 428,
    "stock_condition_pool": 4046,
    "index_condition_pool": 185,
    "board_condition_pool": 268,
    "index_minute_target_scope": 185,
    "board_minute_target_scope": 268,
    "stock_minute_target_scope": 4027,
    "stock_condition_display_basis": 1890,
    "index_condition_display_basis": 83,
    "board_condition_display_basis": 127
  },
  "row_counts_matched": true,
  "quality": {
    "p0_count": 0,
    "p1_count": 6,
    "p2_count": 3
  },
  "refs_total_at_post_review": 0,
  "rollback_safe": true
}
```

## N3-A1 Baseline

```json
{
  "subscription_run_id": "market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1",
  "preload_run_id": "previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1",
  "stage1": {
    "common_market_data_run": 1,
    "quality": 34,
    "candidate": 5046,
    "subscription": 2666,
    "pull_plan": 9
  },
  "stage2": {
    "common_market_data_run": 1,
    "quality": 12,
    "stock_minute_rows": 60000,
    "index_minute_rows": 4560,
    "board_minute_rows": 3360,
    "stock_status": 250,
    "index_status": 19,
    "board_status": 14
  },
  "duplicate_minute_key_groups": {
    "stock": 0,
    "index": 0,
    "board": 0
  },
  "refs_total": 0,
  "rollback_safe": true
}
```

## Rollback Registry

```json
{
  "n1_20260609": "sql/N1_20260609_source_facts_guarded_runner_rollback.sql",
  "n1_20260610": "sql/N1_20260610_source_facts_guarded_runner_rollback.sql",
  "n2_20260611": "sql/N2_condition_layer_20260611_rollback.sql",
  "n3_a1_20260611": "sql/N3_A1_previous_day_minute_20260611_rollback.sql"
}
```

## Side-effect Proof

```json
{
  "outbox_inbox_checkpoint_consumed_or_updated": false,
  "n3_b_c_b2_executed": false,
  "n4_n5_n6_executed": false,
  "worker_started": false,
  "old_system_touched": false,
  "delivery_push_voice_mobile": false,
  "proposal_order_trade_sim_position_pnl_real_trade": false
}
```

## Next Recommended Gate

N3_20260611_BC_B2_SCOPE_PLANNING_GATE or FAST_LANE_REAL_SAME_LAYER_ORCHESTRATION_IMPLEMENTATION_GATE; do not auto-enter N3-B/C/B2/N4/N5/N6
