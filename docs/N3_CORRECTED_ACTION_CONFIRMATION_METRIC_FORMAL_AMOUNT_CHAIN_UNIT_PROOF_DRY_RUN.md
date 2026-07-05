# N3 Corrected Action Confirmation Metric Formal Amount Chain Unit Proof Dry Run

- target_run_id: `action_confirmation_projection_metric_20260616_until_1401_formal_amount_chain_unit_proof_corrected__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- result: `BLOCKED`
- source_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v4`
- source_subscription_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- source_preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- required B1/C1 v4: `realtime_daily_snapshot_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4` / `today_minute_bar_1m_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- planned rows after v4 source refresh stock/index/board/total: `564/17/53/634`
- blockers: `source_b1_v4_realtime_snapshot_missing, source_c1_v4_today_minute_missing, source_payload_not_materialized_for_current_v4_lineage`

## Formal Amount Chain Unit Proof

{
  "amount_unit": "yuan",
  "source_amount_unit": "thousand_yuan",
  "unit_conversion_factor": 1000,
  "unit_conversion_policy": "formal_amount_chain_thousand_yuan_to_yuan_v1",
  "metric_policy": "previous_day_same_window_elapsed_ratio_v1",
  "current_period_amount_source_kind": "N3_standard_period_metric",
  "amount_rule": "attachment_dwmqy_avg_chain",
  "required_trace_fields": [
    "amount_unit",
    "metric_policy",
    "current_period_amount_source_kind",
    "today_virt_amount",
    "weekly_avg_with_today",
    "monthly_avg_with_today",
    "quarterly_avg_with_today",
    "yearly_avg_with_today",
    "prev_weekly_avg",
    "prev_monthly_avg",
    "prev_quarterly_avg",
    "prev_yearly_avg",
    "current_5m_virtual_amount",
    "current_30m_virtual_amount",
    "previous_day_same_5m_full_amount",
    "previous_day_same_30m_full_amount",
    "current_elapsed_amount",
    "previous_day_same_elapsed_amount",
    "previous_day_same_full_amount"
  ],
  "fail_closed": {
    "missing_source_metric": "quality_visible_not_ready_no_fallback",
    "zero_previous_day_same_elapsed_denominator": "quality_visible_not_ready_no_fallback",
    "missing_previous_day_same_window_full_amount": "quality_visible_not_ready_no_fallback",
    "linear_extrapolation_allowed": false,
    "fallback_allowed": false
  }
}
